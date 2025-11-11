"""
智能配票算法 - 核心分配引擎

本模块实现智能配票的核心算法，支持大规模票据池（1万+）的高效分配。
时间复杂度：O(n log n)，其中n为票据数量。
"""
import random
import time
from typing import List, Tuple

from .models import (
    AllocationConfig,
    AllocationResult,
    AmountLabel,
    Ticket,
    PaymentOrder,
    TicketUsage,
    TicketDistribution,
    ScoreBreakdown,
)
from .scoring import score_ticket, ScoringContext
from .constraints import (
    validate_ticket_filter,
    validate_ticket_count,
    validate_small_ticket_constraint,
    validate_split_constraints,
)
from .splitter import adjust_with_split


class AllocationEngine:
    """
    配票引擎
    
    负责根据配置和策略为付款单选择最优的票据组合
    """
    
    def __init__(self, config: AllocationConfig, seed: int = None):
        """
        初始化配票引擎
        
        参数:
            config: 配票配置
            seed: 随机数种子（可选，用于结果复现）
        """
        self.config = config
        self.rng = random.Random(seed)

    def allocate(
        self, order: PaymentOrder, ticket_pool: List[Ticket]
    ) -> AllocationResult:
        """
        为单个付款单分配票据
        
        参数:
            order: 付款单对象
            ticket_pool: 可用票据池
            
        返回:
            AllocationResult: 配票结果（包含详细统计信息）
            
        时间复杂度: O(n log n)
        """
        start_time = time.time()
        warnings: List[str] = []
        
        # 1. 过滤不符合约束的票据 - O(n)
        filtered = [
            t for t in ticket_pool 
            if validate_ticket_filter(t, self.config) and t.available_amount > 0
        ]
        
        if not filtered:
            return self._create_empty_result(order, warnings, start_time)
        
        # 2. 构建评分上下文 - O(n)
        ctx = self._build_context(filtered)
        
        # 3. 尝试等额配票（如果启用）- O(m)，m为等额票据数量
        if self.config.equal_amount_first:
            equal_result = self._try_equal_match(order, filtered, ctx, start_time)
            if equal_result:
                return equal_result
        
        # 4. 对所有票据评分 - O(n)
        scored = [score_ticket(t, order, self.config, ctx) for t in filtered]
        
        # 5. 按得分排序 - O(n log n)
        scored.sort(key=lambda x: x.total_score, reverse=True)
        
        # 6. 贪心构建票据组合 - O(k)，k为max_ticket_count
        selected, remaining = self._build_combination(order, scored, ctx)
        
        # 7. 拆票调整（如果需要）- O(k)
        selected, split_warnings = adjust_with_split(
            selected, remaining, order, self.config, ctx
        )
        warnings.extend(split_warnings)
        
        # 8. 更新票据可用金额 - O(k)
        for tu in selected:
            tu.ticket.available_amount -= tu.used_amount
        
        # 9. 验证约束 - O(k)
        constraints_ok, constraint_msg = self._validate_constraints(selected, order.amount)
        if not constraints_ok:
            warnings.append(constraint_msg)
        
        # 10. 构建完整结果对象 - O(n)
        result = self._build_result(
            order, selected, ticket_pool, filtered, ctx, 
            constraints_ok, warnings, start_time
        )
        
        return result

    def allocate_batch(
        self, orders: List[PaymentOrder], ticket_pool: List[Ticket]
    ) -> List[AllocationResult]:
        """
        批量为多个付款单分配票据
        
        参数:
            orders: 付款单列表
            ticket_pool: 可用票据池（共享）
            
        返回:
            配票结果列表
            
        时间复杂度: O(m * n log n)，m为订单数量
        """
        # 按优先级排序订单
        orders_sorted = sorted(orders, key=lambda o: o.priority, reverse=True)
        results = []
        
        for order in orders_sorted:
            result = self.allocate(order, ticket_pool)
            results.append(result)
        
        return results

    def _build_context(self, tickets: List[Ticket]) -> ScoringContext:
        """
        构建评分上下文（票据池统计信息）
        
        参数:
            tickets: 票据列表
            
        返回:
            ScoringContext: 包含统计信息的上下文对象
        """
        if not tickets:
            # 默认值
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
            # 计算实际统计信息
            maturity_range = (
                min(t.maturity_days for t in tickets),
                max(t.maturity_days for t in tickets),
            )
            
            # 按标签统计金额范围
            amount_range_by_label = {}
            for label in AmountLabel:
                subset = [t.amount for t in tickets if t.amount_label == label]
                if subset:
                    amount_range_by_label[label] = (min(subset), max(subset))
            
            # 计算库存分布
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
        self, order: PaymentOrder, tickets: List[Ticket], ctx: ScoringContext, start_time: float
    ) -> AllocationResult:
        """
        尝试等额配票
        
        如果存在金额接近的票据，直接使用单张票据匹配
        
        参数:
            order: 付款单
            tickets: 票据列表
            ctx: 评分上下文
            start_time: 开始时间
            
        返回:
            AllocationResult 或 None
        """
        threshold = self.config.equal_amount_threshold
        equal_tickets = [
            t for t in tickets if abs(t.amount - order.amount) <= threshold
        ]
        
        if not equal_tickets:
            return None
        
        # 从等额票据中选择得分最高的
        scored = [score_ticket(t, order, self.config, ctx) for t in equal_tickets]
        best = max(scored, key=lambda x: x.total_score)
        
        # 更新票据可用金额
        best.ticket.available_amount -= best.ticket.amount
        
        tu = TicketUsage(
            ticket=best.ticket,
            used_amount=best.ticket.amount,
            split_ratio=1.0,
            score=best,
            order_index=0,
        )
        
        execution_time = (time.time() - start_time) * 1000
        
        result = AllocationResult(
            order_id=order.id,
            target_amount=order.amount,
            selected_tickets=[tu],
            total_amount=tu.used_amount,
            bias_amount=order.amount - tu.used_amount,
            ticket_count=1,
            total_score=best.total_score,
            execution_time_ms=execution_time,
            constraints_met=True,
            warnings=["等额配票成功"],
        )
        
        # 添加得分明细
        result.score_breakdown = ScoreBreakdown(
            avg_maturity_score=best.maturity_score,
            avg_acceptor_score=best.acceptor_score,
            avg_amount_score=best.amount_score,
            avg_organization_score=best.organization_score,
            total_weighted_score=best.total_score,
        )
        
        return result

    def _build_combination(
        self, order: PaymentOrder, scored_tickets: List, ctx: ScoringContext
    ) -> Tuple[List[TicketUsage], List[Ticket]]:
        """
        贪心构建票据组合
        
        从高分票据开始选择，允许在满足拆票约束的情况下按需使用部分金额
        
        参数:
            order: 付款单
            scored_tickets: 已评分的票据列表（按得分降序）
            ctx: 评分上下文
            
        返回:
            (选中的票据, 剩余的票据)
        """
        selected: List[TicketUsage] = []
        used_ids = set()
        accumulated = 0.0
        max_count = self.config.constraint_config.max_ticket_count
        
        for ts in scored_tickets:
            if len(selected) >= max_count:
                break
            if ts.ticket.id in used_ids:
                continue
            if ts.ticket.available_amount <= 0:
                continue
            
            remaining_need = order.amount - accumulated
            if remaining_need <= 0:
                break
            
            available_amount = min(ts.ticket.available_amount, ts.ticket.amount)
            to_use = available_amount
            split_ratio = to_use / ts.ticket.amount
            
            # 如有必要且允许拆票，尝试按需拆分使用
            if (
                available_amount > remaining_need
                and self.config.split_config.allow_split
                and remaining_need > 0
            ):
                desired_ratio = remaining_need / ts.ticket.amount
                if desired_ratio <= 1.0:
                    ok, _ = validate_split_constraints(ts.ticket.amount, desired_ratio, self.config)
                    if ok:
                        to_use = min(ts.ticket.available_amount, desired_ratio * ts.ticket.amount)
                        split_ratio = to_use / ts.ticket.amount
                    else:
                        adjusted_ratio = max(self.config.split_config.min_ratio, min(1.0, desired_ratio))
                        ok, _ = validate_split_constraints(ts.ticket.amount, adjusted_ratio, self.config)
                        if ok:
                            to_use = min(ts.ticket.available_amount, adjusted_ratio * ts.ticket.amount)
                            split_ratio = to_use / ts.ticket.amount
            
            tu = TicketUsage(
                ticket=ts.ticket,
                used_amount=to_use,
                split_ratio=split_ratio,
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
        """
        验证约束条件
        
        参数:
            selected: 选中的票据
            order_amount: 订单金额
            
        返回:
            (是否满足约束, 错误消息)
        """
        # 验证票据张数
        if not validate_ticket_count([tu.ticket for tu in selected], self.config):
            return False, "票据张数超过限制"
        
        # 验证小票占比约束
        ok, msg = validate_small_ticket_constraint(
            [(tu.ticket, tu.used_amount) for tu in selected],
            order_amount,
            self.config,
        )
        if not ok:
            return False, msg
        
        return True, ""

    def _create_empty_result(
        self, order: PaymentOrder, warnings: List[str], start_time: float
    ) -> AllocationResult:
        """创建空结果（无可用票据时）"""
        warnings.append("无可用票据")
        execution_time = (time.time() - start_time) * 1000
        
        return AllocationResult(
            order_id=order.id,
            target_amount=order.amount,
            selected_tickets=[],
            total_amount=0.0,
            bias_amount=order.amount,
            ticket_count=0,
            total_score=0.0,
            execution_time_ms=execution_time,
            constraints_met=False,
            warnings=warnings,
        )

    def _build_result(
        self, 
        order: PaymentOrder,
        selected: List[TicketUsage],
        all_tickets: List[Ticket],
        filtered_tickets: List[Ticket],
        ctx: ScoringContext,
        constraints_ok: bool,
        warnings: List[str],
        start_time: float
    ) -> AllocationResult:
        """
        构建完整的配票结果对象
        
        计算所有统计信息和分布数据
        """
        # 基础金额统计
        total_used = sum(tu.used_amount for tu in selected)
        bias = order.amount - total_used
        
        # 计算拆票统计
        split_count = sum(1 for tu in selected if tu.split_ratio < 1.0)
        split_amount = sum(tu.used_amount for tu in selected if tu.split_ratio < 1.0)
        remain_amount = sum(tu.ticket.amount - tu.used_amount for tu in selected if tu.split_ratio < 1.0)
        
        # 计算电汇尾差
        tail_diff_threshold = max(
            self.config.split_config.tail_diff_abs,
            order.amount * self.config.split_config.tail_diff_ratio
        )
        wire_transfer_diff = bias if 0 < bias <= tail_diff_threshold else 0.0
        
        # 计算得分统计
        if selected:
            total_score = sum(tu.score.total_score * tu.split_ratio for tu in selected)
            score_breakdown = ScoreBreakdown(
                avg_maturity_score=sum(tu.score.maturity_score for tu in selected) / len(selected),
                avg_acceptor_score=sum(tu.score.acceptor_score for tu in selected) / len(selected),
                avg_amount_score=sum(tu.score.amount_score for tu in selected) / len(selected),
                avg_organization_score=sum(tu.score.organization_score for tu in selected) / len(selected),
                total_weighted_score=total_score,
            )
        else:
            total_score = 0.0
            score_breakdown = None
        
        # 计算选票分布
        selected_distribution = self._calculate_distribution(
            [tu.ticket for tu in selected],
            [tu.used_amount for tu in selected]
        )
        
        # 计算余票分布（实际）
        remaining_tickets = [t for t in all_tickets if t.available_amount > 0]
        remaining_distribution = self._calculate_distribution(
            remaining_tickets,
            [t.available_amount for t in remaining_tickets]
        )
        
        # 计算期望分布
        expected_distribution = self._calculate_expected_distribution()
        
        # 计算执行时间
        execution_time = (time.time() - start_time) * 1000
        
        result = AllocationResult(
            order_id=order.id,
            target_amount=order.amount,
            selected_tickets=selected,
            total_amount=total_used,
            bias_amount=bias,
            wire_transfer_diff=wire_transfer_diff,
            ticket_count=len(selected),
            split_count=split_count,
            split_amount=split_amount,
            remain_amount=remain_amount,
            total_score=total_score,
            score_breakdown=score_breakdown,
            selected_distribution=selected_distribution,
            remaining_distribution=remaining_distribution,
            expected_distribution=expected_distribution,
            execution_time_ms=execution_time,
            constraints_met=constraints_ok,
            warnings=warnings,
        )
        
        return result

    def _calculate_distribution(
        self, tickets: List[Ticket], amounts: List[float] = None
    ) -> TicketDistribution:
        """
        计算票据分布统计
        
        参数:
            tickets: 票据列表
            amounts: 对应的金额列表（可选，默认使用票据金额）
            
        返回:
            TicketDistribution: 分布统计对象
        """
        if not tickets:
            return TicketDistribution()
        
        if amounts is None:
            amounts = [t.amount for t in tickets]
        
        # 统计各标签的数量和金额
        large_count = sum(1 for t in tickets if t.amount_label == AmountLabel.LARGE)
        medium_count = sum(1 for t in tickets if t.amount_label == AmountLabel.MEDIUM)
        small_count = sum(1 for t in tickets if t.amount_label == AmountLabel.SMALL)
        
        large_amount = sum(
            amt for t, amt in zip(tickets, amounts) if t.amount_label == AmountLabel.LARGE
        )
        medium_amount = sum(
            amt for t, amt in zip(tickets, amounts) if t.amount_label == AmountLabel.MEDIUM
        )
        small_amount = sum(
            amt for t, amt in zip(tickets, amounts) if t.amount_label == AmountLabel.SMALL
        )
        
        total_count = len(tickets)
        total_amount = sum(amounts)
        
        return TicketDistribution(
            large_count=large_count,
            large_ratio=large_count / total_count if total_count > 0 else 0.0,
            large_amount=large_amount,
            medium_count=medium_count,
            medium_ratio=medium_count / total_count if total_count > 0 else 0.0,
            medium_amount=medium_amount,
            small_count=small_count,
            small_ratio=small_count / total_count if total_count > 0 else 0.0,
            small_amount=small_amount,
        )

    def _calculate_expected_distribution(self) -> TicketDistribution:
        """计算期望分布（基于配置）"""
        cfg = self.config.amount_label_config
        return TicketDistribution(
            large_ratio=cfg.large_ratio,
            medium_ratio=cfg.medium_ratio,
            small_ratio=cfg.small_ratio,
        )
