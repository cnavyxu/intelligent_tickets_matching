"""
智能配票算法 - 得分计算模块

本模块实现票据的多维度评分，所有连续值维度均采用归一化处理以增大得分差异。
"""
import random
from dataclasses import dataclass, field
from typing import Dict, Tuple
from decimal import Decimal

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
    """
    评分上下文
    
    存储票据池的统计信息，用于归一化计算
    """
    maturity_range: Tuple[int, int]  # 到期期限范围 (最小天数, 最大天数)
    amount_range_by_label: Dict[AmountLabel, Tuple[Decimal, Decimal]]  # 各标签的金额范围
    inventory_distribution: Dict[AmountLabel, Decimal]  # 当前库存分布
    randomness: random.Random = field(default_factory=random.Random)  # 随机数生成器


def score_ticket(
    ticket: Ticket,
    order: PaymentOrder,
    config: AllocationConfig,
    ctx: ScoringContext,
) -> TicketScore:
    """
    计算单张票据的综合得分
    
    参数:
        ticket: 待评分的票据
        order: 付款单信息
        config: 配票配置
        ctx: 评分上下文
        
    返回:
        TicketScore: 包含各维度得分和总分的票据得分对象
    """
    weight = config.weight_config
    
    # 计算各维度得分
    maturity_score = _score_maturity(ticket, weight, ctx)
    acceptor_score = _score_acceptor(ticket, weight, ctx)
    amount_score = _score_amount(ticket, order, config, ctx)
    organization_score = _score_organization(ticket, order, weight)
    
    # 加权求和得到总分
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
    """
    计算到期期限得分（归一化）
    
    根据策略优先选择期限远或近的票据，使用票据池的实际期限范围进行归一化
    
    参数:
        ticket: 票据对象
        weight: 权重配置
        ctx: 评分上下文
        
    返回:
        float: 归一化后的期限得分 [0, 1]
    """
    d_min, d_max = ctx.maturity_range
    threshold = weight.maturity_threshold
    days = ticket.maturity_days
    
    # 期限范围归一化处理
    if d_max == d_min:
        return 1.0
    
    if weight.maturity_strategy == MaturityStrategy.FAR_FIRST:
        # 优先远期：期限越长得分越高
        if days >= threshold:
            # 超过阈值的部分，在阈值到最大值之间归一化
            if d_max == threshold:
                return 1.0
            normalized = (days - threshold) / (d_max - threshold)
            return 0.7 + 0.3 * min(1.0, normalized)  # [0.7, 1.0]
        else:
            # 未达阈值的部分，在最小值到阈值之间归一化
            if threshold == d_min:
                return 0.0
            normalized = (days - d_min) / (threshold - d_min)
            return 0.7 * max(0.0, normalized)  # [0, 0.7]
    
    elif weight.maturity_strategy == MaturityStrategy.NEAR_FIRST:
        # 优先近期：期限越短得分越高
        if days <= threshold:
            # 小于阈值的部分，在最小值到阈值之间归一化
            if threshold == d_min:
                return 1.0
            normalized = (threshold - days) / (threshold - d_min)
            return 0.7 + 0.3 * min(1.0, normalized)  # [0.7, 1.0]
        else:
            # 超过阈值的部分，在阈值到最大值之间归一化
            if d_max == threshold:
                return 0.0
            normalized = (d_max - days) / (d_max - threshold)
            return 0.7 * max(0.0, normalized)  # [0, 0.7]
    
    return 0.5


def _score_acceptor(ticket: Ticket, weight, ctx: ScoringContext) -> float:
    """
    计算承兑人分类得分（归一化）
    
    根据承兑人等级评分，使用线性归一化
    
    参数:
        ticket: 票据对象
        weight: 权重配置
        ctx: 评分上下文
        
    返回:
        float: 归一化后的承兑人得分 [0, 1]
    """
    total = max(weight.acceptor_class_count, 1)
    acceptor_class = ticket.acceptor_class
    
    # 确保承兑人分类在有效范围内
    acceptor_class = max(1, min(acceptor_class, total))
    
    if weight.acceptor_strategy == AcceptorClassStrategy.GOOD_FIRST:
        # 优先好的：等级数字越小（1最好）得分越高
        return (total + 1 - acceptor_class) / total
    else:
        # 优先差的：等级数字越大得分越高
        return acceptor_class / total


def _score_amount(
    ticket: Ticket,
    order: PaymentOrder,
    config: AllocationConfig,
    ctx: ScoringContext,
) -> float:
    """
    计算金额得分
    
    根据不同的金额策略进行评分
    
    参数:
        ticket: 票据对象
        order: 付款单
        config: 配置对象
        ctx: 评分上下文
        
    返回:
        float: 金额得分 [0, 1]
    """
    strategy = config.weight_config.amount_strategy
    
    if strategy == AmountStrategy.LARGE_FIRST:
        return _score_large_first(ticket, config, ctx)
    elif strategy == AmountStrategy.SMALL_FIRST:
        return _score_small_first(ticket, config, ctx)
    elif strategy == AmountStrategy.RANDOM:
        return ctx.randomness.random()
    elif strategy == AmountStrategy.LESS_THAN_ORDER:
        return 1.0 if ticket.amount <= order.amount else 0.5
    elif strategy == AmountStrategy.GREATER_THAN_ORDER:
        return 1.0 if ticket.amount >= order.amount else 0.2
    elif strategy == AmountStrategy.OPTIMIZE_INVENTORY:
        return _score_optimize_inventory(ticket, config, ctx)
    
    return 0.5


def _score_large_first(ticket: Ticket, config: AllocationConfig, ctx: ScoringContext) -> float:
    """
    大额优先策略得分（归一化）
    
    大额票得分高，且支持在同标签内按金额排序
    
    参数:
        ticket: 票据对象
        config: 配置对象
        ctx: 评分上下文
        
    返回:
        float: 金额得分 [0, 1]
    """
    sub = config.weight_config.amount_sub_strategy
    
    if ticket.amount_label == AmountLabel.LARGE:
        if sub == AmountSubStrategy.SORTED:
            # 在大额票内部按金额归一化排序
            low, high = ctx.amount_range_by_label.get(AmountLabel.LARGE, (ticket.amount, ticket.amount))
            if high > low:
                # 金额越大得分越高
                normalized = float((ticket.amount - low) / (high - low))
                return 0.7 + 0.3 * normalized  # [0.7, 1.0]
            return 0.85
        # 随机模式：大额票得分在 [0.7, 1.0]
        return 0.7 + ctx.randomness.random() * 0.3
    
    elif ticket.amount_label == AmountLabel.MEDIUM:
        return 0.5
    
    else:  # SMALL
        return 0.2


def _score_small_first(ticket: Ticket, config: AllocationConfig, ctx: ScoringContext) -> float:
    """
    小额优先策略得分（归一化）
    
    小额票得分高，且支持在同标签内按金额排序
    
    参数:
        ticket: 票据对象
        config: 配置对象
        ctx: 评分上下文
        
    返回:
        float: 金额得分 [0, 1]
    """
    sub = config.weight_config.amount_sub_strategy
    
    if ticket.amount_label == AmountLabel.SMALL:
        if sub == AmountSubStrategy.SORTED:
            # 在小额票内部按金额归一化排序
            low, high = ctx.amount_range_by_label.get(AmountLabel.SMALL, (ticket.amount, ticket.amount))
            if high > low:
                # 金额越小得分越高
                normalized = float((high - ticket.amount) / (high - low))
                return 0.7 + 0.3 * normalized  # [0.7, 1.0]
            return 0.85
        # 随机模式：小额票得分在 [0.7, 1.0]
        return 0.7 + ctx.randomness.random() * 0.3
    
    elif ticket.amount_label == AmountLabel.MEDIUM:
        return 0.5
    
    else:  # LARGE
        return 0.2


def _score_optimize_inventory(ticket: Ticket, config: AllocationConfig, ctx: ScoringContext) -> float:
    """
    优化库存占比策略得分（归一化）
    
    优先选择超过期望占比的标签，使库存趋向期望分布
    
    注意：库存分布按票据张数占比计算，而非金额占比
    
    计算公式：
    - 如果当前占比 > 期望占比：原始权重 = 2 * 当前占比 - 期望占比
    - 否则：原始权重 = 0
    - 最终得分 = 原始权重 / 所有标签原始权重之和
    
    示例（按张数占比）：
    - 期望分布：大额0.5（50%张数）, 中额0.4（40%张数）, 小额0.1（10%张数）
    - 实际分布：大额0.3（30%张数）, 中额0.5（50%张数）, 小额0.2（20%张数）
    - 原始权重：大额0(因为0.3<0.5), 中额0.6(2*0.5-0.4), 小额0.3(2*0.2-0.1)
    - 归一化得分：大额0, 中额0.6/0.9≈0.67, 小额0.3/0.9≈0.33
    - 优先消耗顺序：中额 > 小额 > 大额
    
    参数:
        ticket: 票据对象
        config: 配置对象
        ctx: 评分上下文
        
    返回:
        float: 金额得分 [0, 1]
    """
    # 期望库存占比
    expected = {
        AmountLabel.LARGE: config.amount_label_config.large_ratio,
        AmountLabel.MEDIUM: config.amount_label_config.medium_ratio,
        AmountLabel.SMALL: config.amount_label_config.small_ratio,
    }
    
    # 当前库存占比
    current = ctx.inventory_distribution
    
    # 计算各标签的原始权重
    # 公式：如果当前占比 > 期望占比，则权重 = 当前占比 + (当前占比 - 期望占比) = 2 * 当前占比 - 期望占比
    # 否则权重为0（不优先消耗）
    raw_weights = {}
    for label in AmountLabel:
        current_ratio = current.get(label, Decimal('0.0'))
        expected_ratio = expected[label]
        if current_ratio > expected_ratio:
            # 超出期望：优先消耗，权重考虑当前总量和超出量
            raw_weights[label] = Decimal('2') * current_ratio - expected_ratio
        else:
            # 低于或等于期望：不优先消耗
            raw_weights[label] = Decimal('0.0')
    
    total_weight = sum(raw_weights.values())
    
    if total_weight == 0:
        # 如果所有标签都未超配，所有标签得分相同
        return 1.0 / len(AmountLabel)
    
    # 归一化到 [0, 1]
    score = float(raw_weights[ticket.amount_label] / total_weight)
    return score


def _score_organization(ticket: Ticket, order: PaymentOrder, weight) -> float:
    """
    计算组织匹配得分
    
    根据票据和订单的组织关系评分
    
    参数:
        ticket: 票据对象
        order: 付款单
        weight: 权重配置
        
    返回:
        float: 组织得分 [0, 1]
    """
    if weight.organization_strategy == OrganizationStrategy.SAME_ORG:
        # 优先同组织
        return 1.0 if ticket.organization == order.organization else 0.0
    else:
        # 优先不同组织
        return 0.0 if ticket.organization == order.organization else 1.0
