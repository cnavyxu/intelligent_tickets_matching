"""
智能配票算法 - 工具函数
"""
from typing import List
from .models import (
    Ticket,
    AmountLabel,
    AmountLabelConfig,
)


def classify_ticket_amount(amount: float, config: AmountLabelConfig) -> AmountLabel:
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
    tickets = []
    for item in data:
        label = classify_ticket_amount(item['amount'], config)
        ticket = Ticket(
            id=item['id'],
            amount=item['amount'],
            maturity_days=item['maturity_days'],
            acceptor_class=item['acceptor_class'],
            amount_label=label,
            organization=item.get('organization', 'default'),
        )
        tickets.append(ticket)
    return tickets


def format_allocation_result(result) -> dict:
    from .models import AllocationResult
    if not isinstance(result, AllocationResult):
        raise ValueError("输入必须是 AllocationResult 类型")
    return {
        "付款单ID": result.order_id,
        "选中票据": [
            {
                "票据ID": tu.ticket.id,
                "票据金额": tu.ticket.amount,
                "使用金额": tu.used_amount,
                "拆分比例": f"{tu.split_ratio:.2%}",
                "综合得分": f"{tu.score.total_score:.4f}",
                "到期天数": tu.ticket.maturity_days,
                "承兑人分类": tu.ticket.acceptor_class,
                "金额标签": tu.ticket.amount_label.value,
            }
            for tu in result.selected_tickets
        ],
        "总使用金额": result.total_amount,
        "差额": result.bias_amount,
        "票据张数": result.ticket_count,
        "综合得分": result.total_score,
        "约束满足": result.constraints_met,
        "警告信息": result.warnings,
    }
