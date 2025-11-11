"""
智能配票算法 - 得分计算模块
"""
import math
import random
from dataclasses import dataclass, field
from typing import Dict, Tuple

from .models import (
    AllocationConfig,
    AmountLabel,
    AmountStrategy,
    AmountSubStrategy,
    MaturityStrategy,
    AcceptorClassStrategy,
    OrganizationStrategy,
    Ticket,
    PaymentOrder,
    TicketScore,
)


@dataclass
class ScoringContext:
    maturity_range: Tuple[int, int]
    amount_range_by_label: Dict[AmountLabel, Tuple[float, float]]
    inventory_distribution: Dict[AmountLabel, float]
    randomness: random.Random = field(default_factory=random.Random)


def score_ticket(
    ticket: Ticket,
    order: PaymentOrder,
    config: AllocationConfig,
    ctx: ScoringContext,
) -> TicketScore:
    weight = config.weight_config
    maturity_score = _score_maturity(ticket, weight, ctx)
    acceptor_score = _score_acceptor(ticket, weight)
    amount_score = _score_amount(ticket, order, config, ctx)
    organization_score = _score_organization(ticket, order, weight)
    total_score = (
        weight.w_maturity * maturity_score
        + weight.w_acceptor * acceptor_score
        + weight.w_amount * amount_score
        + weight.w_organization * organization_score
    )
    return TicketScore(
        ticket=ticket,
        total_score=total_score,
        maturity_score=maturity_score,
        acceptor_score=acceptor_score,
        amount_score=amount_score,
        organization_score=organization_score,
    )


def _score_maturity(ticket: Ticket, weight, ctx: ScoringContext) -> float:
    d_min, d_max = ctx.maturity_range
    threshold = weight.maturity_threshold
    days = ticket.maturity_days
    if weight.maturity_strategy == MaturityStrategy.FAR_FIRST:
        if days >= threshold:
            return 1.0
        if days <= d_min:
            return 0.0
        span = max(threshold - d_min, 1)
        return (days - d_min) / span
    if weight.maturity_strategy == MaturityStrategy.NEAR_FIRST:
        if days <= threshold:
            return 1.0
        if days >= d_max:
            return 0.0
        span = max(d_max - threshold, 1)
        return (d_max - days) / span
    return 0.5


def _score_acceptor(ticket: Ticket, weight) -> float:
    total = max(weight.acceptor_class_count, 1)
    if weight.acceptor_strategy == AcceptorClassStrategy.GOOD_FIRST:
        return (total + 1 - ticket.acceptor_class) / total
    return ticket.acceptor_class / total


def _score_amount(
    ticket: Ticket,
    order: PaymentOrder,
    config: AllocationConfig,
    ctx: ScoringContext,
) -> float:
    strategy = config.weight_config.amount_strategy
    if strategy == AmountStrategy.LARGE_FIRST:
        return _score_large_first(ticket, config, ctx)
    if strategy == AmountStrategy.SMALL_FIRST:
        return _score_small_first(ticket, config, ctx)
    if strategy == AmountStrategy.RANDOM:
        return ctx.randomness.random()
    if strategy == AmountStrategy.LESS_THAN_ORDER:
        return 1.0 if ticket.amount <= order.amount else 0.5
    if strategy == AmountStrategy.GREATER_THAN_ORDER:
        return 1.0 if ticket.amount >= order.amount else 0.2
    if strategy == AmountStrategy.OPTIMIZE_INVENTORY:
        return _score_optimize_inventory(ticket, config, ctx)
    return 0.5


def _score_large_first(ticket: Ticket, config: AllocationConfig, ctx: ScoringContext) -> float:
    sub = config.weight_config.amount_sub_strategy
    if ticket.amount_label == AmountLabel.LARGE:
        if sub == AmountSubStrategy.SORTED:
            low, high = ctx.amount_range_by_label.get(AmountLabel.LARGE, (ticket.amount, ticket.amount))
            span = max(high - low, 1)
            return min(1.0, max(0.0, (ticket.amount - low) / span))
        return 0.7 + ctx.randomness.random() * 0.3
    if ticket.amount_label == AmountLabel.MEDIUM:
        return 0.5
    return 0.2


def _score_small_first(ticket: Ticket, config: AllocationConfig, ctx: ScoringContext) -> float:
    sub = config.weight_config.amount_sub_strategy
    if ticket.amount_label == AmountLabel.SMALL:
        if sub == AmountSubStrategy.SORTED:
            low, high = ctx.amount_range_by_label.get(AmountLabel.SMALL, (ticket.amount, ticket.amount))
            span = max(high - low, 1)
            return min(1.0, max(0.0, (high - ticket.amount) / span))
        return 0.7 + ctx.randomness.random() * 0.3
    if ticket.amount_label == AmountLabel.MEDIUM:
        return 0.5
    return 0.2


def _score_optimize_inventory(ticket: Ticket, config: AllocationConfig, ctx: ScoringContext) -> float:
    expected = {
        AmountLabel.LARGE: config.amount_label_config.large_ratio,
        AmountLabel.MEDIUM: config.amount_label_config.medium_ratio,
        AmountLabel.SMALL: config.amount_label_config.small_ratio,
    }
    current = ctx.inventory_distribution
    deltas = {label: max(0.0, current.get(label, 0.0) - expected[label]) for label in AmountLabel}
    total_delta = sum(deltas.values())
    if total_delta == 0:
        return 1.0 / len(AmountLabel)
    return deltas[ticket.amount_label] / total_delta if total_delta else 0.0


def _score_organization(ticket: Ticket, order: PaymentOrder, weight) -> float:
    if weight.organization_strategy == OrganizationStrategy.SAME_ORG:
        return 1.0 if ticket.organization == order.organization else 0.0
    return 0.0 if ticket.organization == order.organization else 1.0
