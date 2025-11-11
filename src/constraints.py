"""
智能配票算法 - 约束校验模块

本模块实现各种业务约束的校验逻辑
"""
import math
from typing import List, Tuple

from .models import AllocationConfig, Ticket, AmountLabel


def validate_ticket_filter(ticket: Ticket, config: AllocationConfig) -> bool:
    """
    验证票据是否符合过滤条件
    
    检查票据的到期期限、金额范围、承兑人分类等是否在允许范围内
    
    参数:
        ticket: 待验证的票据
        config: 配置对象
        
    返回:
        bool: True表示符合条件，False表示不符合
    """
    c = config.constraint_config
    
    # 验证到期期限范围
    if c.allowed_maturity_days is not None:
        low, high = c.allowed_maturity_days
        if not (low <= ticket.maturity_days <= high):
            return False
    
    # 验证金额范围
    if c.allowed_amount_range is not None:
        low, high = c.allowed_amount_range
        if not (low <= ticket.amount <= high):
            return False
    
    # 验证承兑人分类
    if c.allowed_acceptor_classes is not None:
        if ticket.acceptor_class not in c.allowed_acceptor_classes:
            return False
    
    return True


def validate_ticket_count(selected: List[Ticket], config: AllocationConfig) -> bool:
    """
    验证选中的票据数量是否超过限制
    
    参数:
        selected: 选中的票据列表
        config: 配置对象
        
    返回:
        bool: True表示未超限，False表示超限
    """
    return len(selected) <= config.constraint_config.max_ticket_count


def validate_small_ticket_constraint(
    selected_tickets: List[Tuple[Ticket, float]],
    order_amount: float,
    config: AllocationConfig,
) -> Tuple[bool, str]:
    """
    验证小额票占比约束
    
    检查小额票前80%的累计金额是否满足订单金额的一定比例
    
    参数:
        selected_tickets: 选中的票据及使用金额列表
        order_amount: 订单金额
        config: 配置对象
        
    返回:
        (是否满足约束, 错误消息)
    """
    if not config.constraint_config.small_ticket_limited:
        return True, ""
    
    # 筛选出小额票
    small = [
        (t, amt)
        for t, amt in selected_tickets
        if t.amount_label == AmountLabel.SMALL
    ]
    
    if not small:
        return True, ""
    
    # 按金额排序
    small_sorted = sorted(small, key=lambda x: x[0].amount)
    
    # 取前80%的票据
    idx_80 = max(1, math.ceil(len(small_sorted) * 0.8))
    top_80_amount = sum(amt for _, amt in small_sorted[:idx_80])
    
    # 检查是否满足阈值
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
    """
    验证拆票约束
    
    检查拆票后的使用金额、留存金额、拆分比例是否满足最小值要求
    
    参数:
        ticket_amount: 票据总金额
        split_ratio: 拆分比例
        config: 配置对象
        
    返回:
        (是否满足约束, 错误消息)
    """
    sc = config.split_config
    
    used = split_ratio * ticket_amount
    remain = (1 - split_ratio) * ticket_amount
    
    # 验证最小使用金额
    if used < sc.min_use:
        return False, f"拆票使用金额{used}小于最小值{sc.min_use}"
    
    # 验证最小留存金额
    if remain < sc.min_remain:
        return False, f"拆票留存金额{remain}小于最小值{sc.min_remain}"
    
    # 验证最小拆分比例
    if split_ratio < sc.min_ratio:
        return False, f"拆票比例{split_ratio}小于最小值{sc.min_ratio}"
    
    return True, ""
