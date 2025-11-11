"""
智能配票算法 - 约束校验模块
"""
import math
from typing import List, Tuple

from .models import AllocationConfig, Ticket, AmountLabel


def validate_ticket_filter(ticket: Ticket, config: AllocationConfig) -> bool:
    c = config.constraint_config
    if c.allowed_maturity_days is not None:
        low, high = c.allowed_maturity_days
        if not (low <= ticket.maturity_days <= high):
            return False
    if c.allowed_amount_range is not None:
        low, high = c.allowed_amount_range
        if not (low <= ticket.amount <= high):
            return False
    if c.allowed_acceptor_classes is not None:
        if ticket.acceptor_class not in c.allowed_acceptor_classes:
            return False
    return True


def validate_ticket_count(selected: List[Ticket], config: AllocationConfig) -> bool:
    return len(selected) <= config.constraint_config.max_ticket_count


def validate_small_ticket_constraint(
    selected_tickets: List[Tuple[Ticket, float]],
    order_amount: float,
    config: AllocationConfig,
) -> Tuple[bool, str]:
    if not config.constraint_config.small_ticket_limited:
        return True, ""
    small = [
        (t, amt)
        for t, amt in selected_tickets
        if t.amount_label == AmountLabel.SMALL
    ]
    if not small:
        return True, ""
    small_sorted = sorted(small, key=lambda x: x[0].amount)
    idx_80 = max(1, math.ceil(len(small_sorted) * 0.8))
    top_80_amount = sum(amt for _, amt in small_sorted[:idx_80])
    threshold = config.constraint_config.small_ticket_80pct_amount_coverage
    required = order_amount * threshold
    if top_80_amount < required:
        return False, f"小额票前80%累计金额{top_80_amount}未达到{required}的要求"
    return True, ""


def validate_split_constraints(
    ticket_amount: float,
    split_ratio: float,
    config: AllocationConfig,
) -> Tuple[bool, str]:
    sc = config.split_config
    used = split_ratio * ticket_amount
    remain = (1 - split_ratio) * ticket_amount
    if used < sc.min_use:
        return False, f"拆票使用金额{used}小于最小值{sc.min_use}"
    if remain < sc.min_remain:
        return False, f"拆票留存金额{remain}小于最小值{sc.min_remain}"
    if split_ratio < sc.min_ratio:
        return False, f"拆票比例{split_ratio}小于最小值{sc.min_ratio}"
    return True, ""
