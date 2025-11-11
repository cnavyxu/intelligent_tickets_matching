"""
智能配票算法 - 工具函数
"""
from typing import List
from decimal import Decimal
from .models import (
    Ticket,
    AmountLabel,
    AmountLabelConfig,
)


def classify_ticket_amount(amount: Decimal, config: AmountLabelConfig) -> AmountLabel:
    """根据金额范围配置为票据划分金额标签"""
    if config.large_range[0] <= amount < config.large_range[1]:
        return AmountLabel.LARGE
    if config.medium_range[0] <= amount < config.medium_range[1]:
        return AmountLabel.MEDIUM
    if config.small_range[0] <= amount < config.small_range[1]:
        return AmountLabel.SMALL
    if amount >= config.large_range[0]:
        return AmountLabel.LARGE
    return AmountLabel.SMALL


def create_tickets_from_data(data: List[dict], config: AmountLabelConfig) -> List[Ticket]:
    """根据原始票据字典数据批量创建Ticket对象"""
    tickets = []
    for item in data:
        amount = Decimal(str(item['amount']))
        label = classify_ticket_amount(amount, config)
        ticket = Ticket(
            id=item['id'],
            amount=amount,
            maturity_days=item['maturity_days'],
            acceptor_class=item['acceptor_class'],
            amount_label=label,
            organization=item.get('organization', 'default'),
        )
        tickets.append(ticket)
    return tickets


def format_allocation_result(result) -> dict:
    """
    格式化配票结果为详细的字典输出
    
    参数:
        result: AllocationResult对象
        
    返回:
        包含完整配票信息的字典
    """
    from .models import AllocationResult
    if not isinstance(result, AllocationResult):
        raise ValueError("输入必须是 AllocationResult 类型")
    
    output = {
        "基本信息": {
            "付款单ID": result.order_id,
            "目标金额": result.target_amount,
            "票据组合金额": result.total_amount,
            "差额": result.bias_amount,
            "电汇尾差": result.wire_transfer_diff if result.wire_transfer_diff > 0 else None,
        },
        "选中票据组合": [
            {
                "票据ID": tu.ticket.id,
                "票据金额": tu.ticket.amount,
                "使用金额": tu.used_amount,
                "留存金额": tu.ticket.amount - tu.used_amount,
                "是否被拆分": tu.split_ratio < 1.0,
                "拆分比例": f"{tu.split_ratio:.2%}",
                "到期天数": tu.ticket.maturity_days,
                "承兑人分类": tu.ticket.acceptor_class,
                "金额标签": tu.ticket.amount_label.value,
                "组织": tu.ticket.organization,
                "得分": {
                    "总分": f"{tu.score.total_score:.4f}",
                    "到期期限得分": f"{tu.score.maturity_score:.4f}",
                    "承兑人得分": f"{tu.score.acceptor_score:.4f}",
                    "金额得分": f"{tu.score.amount_score:.4f}",
                    "组织得分": f"{tu.score.organization_score:.4f}",
                }
            }
            for tu in result.selected_tickets
        ],
        "票据统计": {
            "票据数量": result.ticket_count,
            "拆分票据数量": result.split_count,
            "拆票金额": result.split_amount if result.split_amount > 0 else None,
            "留存金额": result.remain_amount if result.remain_amount > 0 else None,
        },
        "选票结构分布": _format_distribution(result.selected_distribution) if result.selected_distribution else None,
        "选票组合得分": {
            "总得分": f"{result.total_score:.4f}",
            "得分明细": _format_score_breakdown(result.score_breakdown) if result.score_breakdown else None,
        },
        "余票库存分布": {
            "期望分布": _format_distribution(result.expected_distribution) if result.expected_distribution else None,
            "实际分布": _format_distribution(result.remaining_distribution) if result.remaining_distribution else None,
        },
        "执行信息": {
            "选票耗时(毫秒)": f"{result.execution_time_ms:.2f}",
            "约束满足": result.constraints_met,
            "警告信息": result.warnings if result.warnings else [],
        }
    }
    
    # 移除None值
    return _remove_none_values(output)


def _format_distribution(dist) -> dict:
    """格式化分布统计"""
    return {
        "大额票": {
            "数量": dist.large_count,
            "占比": f"{dist.large_ratio:.2%}",
            "金额": dist.large_amount,
        },
        "中额票": {
            "数量": dist.medium_count,
            "占比": f"{dist.medium_ratio:.2%}",
            "金额": dist.medium_amount,
        },
        "小额票": {
            "数量": dist.small_count,
            "占比": f"{dist.small_ratio:.2%}",
            "金额": dist.small_amount,
        }
    }


def _format_score_breakdown(breakdown) -> dict:
    """格式化得分明细"""
    return {
        "平均到期期限得分": f"{breakdown.avg_maturity_score:.4f}",
        "平均承兑人得分": f"{breakdown.avg_acceptor_score:.4f}",
        "平均金额得分": f"{breakdown.avg_amount_score:.4f}",
        "平均组织得分": f"{breakdown.avg_organization_score:.4f}",
        "加权总分": f"{breakdown.total_weighted_score:.4f}",
    }


def _remove_none_values(d):
    """递归移除字典中的None值"""
    if not isinstance(d, dict):
        return d
    return {k: _remove_none_values(v) for k, v in d.items() if v is not None}
