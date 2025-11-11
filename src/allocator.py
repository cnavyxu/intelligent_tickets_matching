"""
智能配票算法 - 核心分配引擎
"""
import random
from typing import List, Dict, Tuple

from .models import (
    AllocationConfig,
    AllocationResult,
    AmountLabel,
    Ticket,
    PaymentOrder,
    TicketUsage,
)
from .scoring import score_ticket, ScoringContext
from .constraints import (
    validate_ticket_filter,
    validate_ticket_count,
    validate_small_ticket_constraint,
)
from .splitter import adjust_with_split


class AllocationEngine:
    def __init__(self, config: AllocationConfig, seed: int = None):
        self.config = config
        self.rng = random.Random(seed)

    def allocate(
        self, order: PaymentOrder, ticket_pool: List[Ticket]
    ) -> AllocationResult:
        warnings: List[str] = []
        filtered = [
            t for t in ticket_pool if validate_ticket_filter(t, self.config) and t.available_amount > 0
        ]
        if not filtered:
            return AllocationResult(
                order_id=order.id,
                selected_tickets=[],
                total_amount=0.0,
                bias_amount=order.amount,
                ticket_count=0,
                total_score=0.0,
                constraints_met=False,
                warnings=["无可用票据"],
            )
        ctx = self._build_context(filtered)
        if self.config.equal_amount_first:
            equal_result = self._try_equal_match(order, filtered, ctx)
            if equal_result:
                return equal_result
        scored = [score_ticket(t, order, self.config, ctx) for t in filtered]
        scored.sort(key=lambda x: x.total_score, reverse=True)
        selected, remaining = self._build_combination(order, scored, ctx)
        selected, split_warnings = adjust_with_split(
            selected, remaining, order, self.config, ctx
        )
        warnings.extend(split_warnings)
        total_used = sum(tu.used_amount for tu in selected)
        bias = order.amount - total_used
        for tu in selected:
            tu.ticket.available_amount -= tu.used_amount
        constraints_ok, constraint_msg = self._validate_constraints(selected, order.amount)
        if not constraints_ok:
            warnings.append(constraint_msg)
        result = AllocationResult(
            order_id=order.id,
            selected_tickets=selected,
            total_amount=total_used,
            bias_amount=bias,
            ticket_count=len(selected),
            total_score=sum(tu.score.total_score * tu.split_ratio for tu in selected),
            constraints_met=constraints_ok,
            warnings=warnings,
        )
        return result

    def allocate_batch(
        self, orders: List[PaymentOrder], ticket_pool: List[Ticket]
    ) -> List[AllocationResult]:
        orders_sorted = sorted(orders, key=lambda o: o.priority, reverse=True)
        results = []
        for order in orders_sorted:
            result = self.allocate(order, ticket_pool)
            results.append(result)
        return results

    def _build_context(self, tickets: List[Ticket]) -> ScoringContext:
        if not tickets:
            maturity_range = (0, 365)
            amount_range_by_label = {
                AmountLabel.LARGE: (1000000, 10000000),
                AmountLabel.MEDIUM: (100000, 1000000),
                AmountLabel.SMALL: (10000, 100000),
            }
            inventory_distribution = {
                AmountLabel.LARGE: 0.33,
                AmountLabel.MEDIUM: 0.33,
                AmountLabel.SMALL: 0.34,
            }
        else:
            maturity_range = (
                min(t.maturity_days for t in tickets),
                max(t.maturity_days for t in tickets),
            )
            amount_range_by_label = {}
            for label in AmountLabel:
                subset = [t.amount for t in tickets if t.amount_label == label]
                if subset:
                    amount_range_by_label[label] = (min(subset), max(subset))
            total_amount = sum(t.amount for t in tickets)
            inventory_distribution = {}
            if total_amount > 0:
                for label in AmountLabel:
                    label_sum = sum(
                        t.amount for t in tickets if t.amount_label == label
                    )
                    inventory_distribution[label] = label_sum / total_amount
            else:
                inventory_distribution = {label: 1.0 / len(AmountLabel) for label in AmountLabel}
        return ScoringContext(
            maturity_range=maturity_range,
            amount_range_by_label=amount_range_by_label,
            inventory_distribution=inventory_distribution,
            randomness=self.rng,
        )

    def _try_equal_match(
        self, order: PaymentOrder, tickets: List[Ticket], ctx: ScoringContext
    ) -> AllocationResult:
        threshold = self.config.equal_amount_threshold
        equal_tickets = [
            t for t in tickets if abs(t.amount - order.amount) <= threshold
        ]
        if not equal_tickets:
            return None
        scored = [score_ticket(t, order, self.config, ctx) for t in equal_tickets]
        best = max(scored, key=lambda x: x.total_score)
        best.ticket.available_amount -= best.ticket.amount
        tu = TicketUsage(
            ticket=best.ticket,
            used_amount=best.ticket.amount,
            split_ratio=1.0,
            score=best,
            order_index=0,
        )
        bias = order.amount - tu.used_amount
        return AllocationResult(
            order_id=order.id,
            selected_tickets=[tu],
            total_amount=tu.used_amount,
            bias_amount=bias,
            ticket_count=1,
            total_score=best.total_score,
            constraints_met=True,
            warnings=["等额配票成功"],
        )

    def _build_combination(
        self, order: PaymentOrder, scored_tickets: List, ctx: ScoringContext
    ) -> Tuple[List[TicketUsage], List[Ticket]]:
        selected: List[TicketUsage] = []
        used_ids = set()
        accumulated = 0.0
        max_count = self.config.constraint_config.max_ticket_count
        for idx, ts in enumerate(scored_tickets):
            if len(selected) >= max_count:
                break
            if ts.ticket.id in used_ids:
                continue
            if ts.ticket.available_amount <= 0:
                continue
            to_use = min(ts.ticket.available_amount, ts.ticket.amount)
            tu = TicketUsage(
                ticket=ts.ticket,
                used_amount=to_use,
                split_ratio=to_use / ts.ticket.amount,
                score=ts,
                order_index=len(selected),
            )
            selected.append(tu)
            used_ids.add(ts.ticket.id)
            accumulated += to_use
            if accumulated >= order.amount:
                break
        remaining = [t.ticket for t in scored_tickets if t.ticket.id not in used_ids]
        return selected, remaining

    def _validate_constraints(
        self, selected: List[TicketUsage], order_amount: float
    ) -> Tuple[bool, str]:
        if not validate_ticket_count([tu.ticket for tu in selected], self.config):
            return False, "票据张数超过限制"
        ok, msg = validate_small_ticket_constraint(
            [(tu.ticket, tu.used_amount) for tu in selected],
            order_amount,
            self.config,
        )
        if not ok:
            return False, msg
        return True, ""
