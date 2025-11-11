"""
智能配票算法 - 拆票模块
"""
from typing import List, Optional, Tuple

from .models import (
    AllocationConfig,
    Ticket,
    TicketUsage,
    SplitStrategy,
    PaymentOrder,
)
from .constraints import validate_split_constraints
from .scoring import score_ticket, ScoringContext


def adjust_with_split(
    selected: List[TicketUsage],
    remaining_tickets: List[Ticket],
    order: PaymentOrder,
    config: AllocationConfig,
    ctx: ScoringContext,
) -> Tuple[List[TicketUsage], List[str]]:
    warnings: List[str] = []
    tail_diff = _calculate_tail_diff(order.amount, config)

    def current_bias() -> float:
        return order.amount - sum(tu.used_amount for tu in selected)

    loop_guard = 0
    while loop_guard < 5:
        loop_guard += 1
        bias = current_bias()
        if 0 < bias <= tail_diff and not config.split_config.split_condition_unlimited:
            warnings.append(f"差额{bias:.2f}在尾差阈值内，采用电汇补齐")
            break
        if abs(bias) <= tail_diff:
            break

        if bias > tail_diff:
            if not config.split_config.allow_split:
                warnings.append(f"尾差{bias:.2f}超阈值且未允许拆票")
                break
            result = _add_split_ticket(selected, remaining_tickets, bias, config, ctx, order)
            if result:
                selected, msg = result
                warnings.append(f"补票拆分: {msg}")
                continue
            warnings.append(f"无法补票，尾差{bias:.2f}")
            break

        if bias < -tail_diff:
            if not config.split_config.allow_split:
                warnings.append(f"尾差{bias:.2f}超阈值且未允许拆票")
                break
            result = _split_from_selected(selected, abs(bias), config, ctx, order)
            if result:
                selected, msg = result
                warnings.append(f"超额拆分: {msg}")
                continue
            warnings.append(f"无法从组合中拆票，尾差{bias:.2f}")
            break
    return selected, warnings


def _calculate_tail_diff(order_amount: float, config: AllocationConfig) -> float:
    return max(
        config.split_config.tail_diff_abs,
        order_amount * config.split_config.tail_diff_ratio,
    )


def _add_split_ticket(
    selected: List[TicketUsage],
    remaining: List[Ticket],
    bias: float,
    config: AllocationConfig,
    ctx: ScoringContext,
    order: PaymentOrder,
) -> Optional[Tuple[List[TicketUsage], str]]:
    available = [t for t in remaining if t.available_amount >= bias]
    if not available:
        available = [t for t in remaining if t.available_amount > 0]
    if not available:
        return None
    candidate = _select_split_ticket(available, config, ctx, order, bias)
    if candidate is None:
        return None
    usable_amount = min(bias, candidate.available_amount)
    split_ratio = usable_amount / candidate.amount
    if split_ratio <= 0:
        return None
    ok, msg = validate_split_constraints(candidate.amount, split_ratio, config)
    if not ok:
        split_ratio = max(config.split_config.min_ratio, split_ratio)
        ok, _ = validate_split_constraints(candidate.amount, split_ratio, config)
        if not ok:
            return None
        usable_amount = split_ratio * candidate.amount
    score_obj = score_ticket(candidate, order, config, ctx)
    tu = TicketUsage(
        ticket=candidate,
        used_amount=usable_amount,
        split_ratio=split_ratio,
        score=score_obj,
        order_index=len(selected),
    )
    selected.append(tu)
    return selected, f"新增拆票{candidate.id}，拆分比例{split_ratio:.2%}"


def _split_from_selected(
    selected: List[TicketUsage],
    bias: float,
    config: AllocationConfig,
    ctx: ScoringContext,
    order: PaymentOrder,
) -> Optional[Tuple[List[TicketUsage], str]]:
    if not selected:
        return None
    candidates = [tu for tu in selected if tu.used_amount >= bias]
    if not candidates:
        candidates = selected
    strict_candidates = [tu for tu in candidates if tu.split_ratio == 1.0 and tu.used_amount >= bias]
    if strict_candidates:
        candidates = strict_candidates
    tu_to_split = _select_split_ticket([tu.ticket for tu in candidates], config, ctx, order, bias)
    if tu_to_split is None:
        return None
    for tu in selected:
        if tu.ticket.id == tu_to_split.id:
            new_used = tu.used_amount - bias
            new_ratio = new_used / tu.ticket.amount
            if new_ratio < 0:
                return None
            ok, _ = validate_split_constraints(tu.ticket.amount, new_ratio, config)
            if not ok:
                return None
            tu.used_amount = new_used
            tu.split_ratio = new_ratio
            return selected, f"调整票据{tu.ticket.id}使用金额至{new_used}"
    return None


def _select_split_ticket(
    tickets: List[Ticket],
    config: AllocationConfig,
    ctx: ScoringContext,
    order: PaymentOrder,
    bias: float = 0.0,
) -> Optional[Ticket]:
    if not tickets:
        return None
    strategy = config.split_config.split_strategy
    if strategy == SplitStrategy.BY_MATURITY:
        scored = [score_ticket(t, order, config, ctx) for t in tickets]
        scored.sort(key=lambda x: x.maturity_score, reverse=True)
        return scored[0].ticket
    if strategy == SplitStrategy.BY_ACCEPTOR_CLASS:
        scored = [score_ticket(t, order, config, ctx) for t in tickets]
        scored.sort(key=lambda x: x.acceptor_score, reverse=True)
        return scored[0].ticket
    if strategy == SplitStrategy.BY_AMOUNT_LARGE:
        return max(tickets, key=lambda x: x.amount)
    if strategy == SplitStrategy.BY_AMOUNT_CLOSE:
        return min(tickets, key=lambda x: abs(x.amount - bias))
    return tickets[0]
