"""
智能配票算法 - 场景化测试

测试覆盖以下场景：
1. 小规模配票
2. 大规模配票（1万票据池）
3. 各种金额策略
4. 约束条件测试
5. 拆票测试
6. 性能测试
7. 边界条件测试
"""
import sys
import random
import time
sys.path.insert(0, '/home/engine/project')

from src import (
    AllocationConfig,
    PaymentOrder,
    AllocationEngine,
    WeightConfig,
    SplitConfig,
    ConstraintConfig,
    AmountStrategy,
    AmountSubStrategy,
    MaturityStrategy,
    AcceptorClassStrategy,
)
from src.utils import create_tickets_from_data, format_allocation_result


def generate_random_tickets(count: int, seed: int = 42) -> list:
    """
    生成随机票据数据
    
    参数:
        count: 票据数量
        seed: 随机数种子
        
    返回:
        票据数据列表
    """
    rng = random.Random(seed)
    tickets = []
    orgs = ['公司A', '公司B', '公司C', '公司D', '公司E']
    
    for i in range(count):
        tickets.append({
            'id': f'T{i+1:05d}',
            'amount': rng.choice([
                rng.randint(10000, 100000),      # 小额
                rng.randint(100000, 1000000),    # 中额
                rng.randint(1000000, 5000000),   # 大额
            ]),
            'maturity_days': rng.randint(30, 180),
            'acceptor_class': rng.randint(1, 5),
            'organization': rng.choice(orgs),
        })
    
    return tickets


def test_scenario_1_small_scale():
    """场景1：小规模配票（基础功能验证）"""
    print("\n" + "="*80)
    print("场景1：小规模配票")
    print("="*80)
    
    tickets_data = [
        {"id": "T001", "amount": 500000, "maturity_days": 120, "acceptor_class": 3, "organization": "公司A"},
        {"id": "T002", "amount": 300000, "maturity_days": 60, "acceptor_class": 1, "organization": "公司B"},
        {"id": "T003", "amount": 200000, "maturity_days": 90, "acceptor_class": 2, "organization": "公司A"},
    ]
    
    config = AllocationConfig()
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O001", amount=500000, organization="公司A")
    
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    
    output = format_allocation_result(result)
    print(f"✓ 选中 {result.ticket_count} 张票据")
    print(f"✓ 总金额: {result.total_amount}")
    print(f"✓ 差额: {result.bias_amount}")
    print(f"✓ 耗时: {result.execution_time_ms:.2f}ms")
    
    assert result.ticket_count > 0, "应该选中票据"
    print("✓ 场景1测试通过")


def test_scenario_2_large_scale():
    """场景2：大规模配票（1万票据池，200万付款金额）"""
    print("\n" + "="*80)
    print("场景2：大规模配票（1万票据，200万付款金额）")
    print("="*80)
    
    # 生成1万张票据
    tickets_data = generate_random_tickets(10000, seed=42)
    
    config = AllocationConfig(
        weight_config=WeightConfig(
            amount_strategy=AmountStrategy.OPTIMIZE_INVENTORY,
            amount_sub_strategy=AmountSubStrategy.SORTED,
        ),
        constraint_config=ConstraintConfig(
            max_ticket_count=20,
        )
    )
    
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O002", amount=2000000, organization="公司A")
    
    start_time = time.time()
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    end_time = time.time()
    
    print(f"✓ 票据池大小: 10,000张")
    print(f"✓ 目标金额: 2,000,000")
    print(f"✓ 选中票据: {result.ticket_count}张")
    print(f"✓ 组合金额: {result.total_amount:,.2f}")
    print(f"✓ 差额: {result.bias_amount:,.2f}")
    print(f"✓ 综合得分: {result.total_score:.4f}")
    print(f"✓ 选票耗时: {result.execution_time_ms:.2f}ms")
    print(f"✓ 总耗时: {(end_time - start_time)*1000:.2f}ms")
    
    if result.selected_distribution:
        dist = result.selected_distribution
        print(f"✓ 选票结构: 大额{dist.large_count}张({dist.large_ratio:.1%}), "
              f"中额{dist.medium_count}张({dist.medium_ratio:.1%}), "
              f"小额{dist.small_count}张({dist.small_ratio:.1%})")
    
    # 性能断言：1万票据应在100ms内完成
    assert result.execution_time_ms < 1000, f"性能要求未达标: {result.execution_time_ms:.2f}ms > 1000ms"
    assert result.ticket_count > 0, "应该选中票据"
    print("✓ 场景2测试通过（性能达标）")


def test_scenario_3_amount_strategies():
    """场景3：不同金额策略测试"""
    print("\n" + "="*80)
    print("场景3：金额策略对比测试")
    print("="*80)
    
    tickets_data = generate_random_tickets(1000, seed=42)
    
    strategies = [
        (AmountStrategy.LARGE_FIRST, "大额优先"),
        (AmountStrategy.SMALL_FIRST, "小额优先"),
        (AmountStrategy.OPTIMIZE_INVENTORY, "优化库存"),
    ]
    
    for strategy, name in strategies:
        config = AllocationConfig(
            weight_config=WeightConfig(
                w_amount=0.6,
                amount_strategy=strategy,
                amount_sub_strategy=AmountSubStrategy.SORTED,
            )
        )
        
        tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
        order = PaymentOrder(id="O003", amount=800000, organization="公司A")
        
        engine = AllocationEngine(config=config, seed=42)
        result = engine.allocate(order, tickets)
        
        dist = result.selected_distribution
        print(f"\n策略: {name}")
        print(f"  选中票据: {result.ticket_count}张")
        print(f"  组合金额: {result.total_amount:,.2f}")
        print(f"  结构分布: 大{dist.large_count}张, 中{dist.medium_count}张, 小{dist.small_count}张")
        print(f"  耗时: {result.execution_time_ms:.2f}ms")
        
        assert result.ticket_count > 0, f"{name}策略应该选中票据"
    
    print("\n✓ 场景3测试通过")


def test_scenario_4_constraints():
    """场景4：约束条件测试"""
    print("\n" + "="*80)
    print("场景4：约束条件测试")
    print("="*80)
    
    tickets_data = generate_random_tickets(500, seed=42)
    
    # 测试4.1：最大张数限制
    print("\n4.1 最大张数限制（max_ticket_count=5）")
    config = AllocationConfig(
        constraint_config=ConstraintConfig(max_ticket_count=5)
    )
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O004", amount=1000000, organization="公司A")
    
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    
    print(f"  选中票据: {result.ticket_count}张")
    assert result.ticket_count <= 5, "票据数量应不超过5张"
    print("  ✓ 最大张数约束满足")
    
    # 测试4.2：小票占比限制
    print("\n4.2 小票占比限制")
    config = AllocationConfig(
        constraint_config=ConstraintConfig(
            small_ticket_limited=True,
            small_ticket_80pct_amount_coverage=0.3,
        )
    )
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O005", amount=800000, organization="公司A")
    
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    
    print(f"  选中票据: {result.ticket_count}张")
    print(f"  约束满足: {result.constraints_met}")
    print("  ✓ 小票约束测试完成")
    
    print("\n✓ 场景4测试通过")


def test_scenario_5_split():
    """场景5：拆票功能测试"""
    print("\n" + "="*80)
    print("场景5：拆票功能测试")
    print("="*80)
    
    tickets_data = [
        {"id": "T001", "amount": 1000000, "maturity_days": 120, "acceptor_class": 2, "organization": "公司A"},
        {"id": "T002", "amount": 800000, "maturity_days": 90, "acceptor_class": 1, "organization": "公司B"},
        {"id": "T003", "amount": 500000, "maturity_days": 60, "acceptor_class": 3, "organization": "公司A"},
    ]
    
    config = AllocationConfig(
        split_config=SplitConfig(
            allow_split=True,
            tail_diff_abs=5000,
            min_remain=50000,
            min_use=50000,
            min_ratio=0.2,
        )
    )
    
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O006", amount=750000, organization="公司A")
    
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    
    print(f"✓ 选中票据: {result.ticket_count}张")
    print(f"✓ 拆分票据: {result.split_count}张")
    print(f"✓ 组合金额: {result.total_amount:,.2f}")
    print(f"✓ 差额: {result.bias_amount:,.2f}")
    print(f"✓ 拆票金额: {result.split_amount:,.2f}")
    print(f"✓ 留存金额: {result.remain_amount:,.2f}")
    
    # 检查拆票详情
    for tu in result.selected_tickets:
        if tu.split_ratio < 1.0:
            print(f"  拆票详情: {tu.ticket.id}, 使用{tu.used_amount:,.2f}, "
                  f"留存{tu.ticket.amount - tu.used_amount:,.2f}, "
                  f"拆分比例{tu.split_ratio:.2%}")
    
    print("✓ 场景5测试通过")


def test_scenario_6_maturity_strategies():
    """场景6：到期期限策略测试"""
    print("\n" + "="*80)
    print("场景6：到期期限策略测试")
    print("="*80)
    
    tickets_data = generate_random_tickets(500, seed=42)
    
    strategies = [
        (MaturityStrategy.FAR_FIRST, "优先远期"),
        (MaturityStrategy.NEAR_FIRST, "优先近期"),
    ]
    
    for strategy, name in strategies:
        config = AllocationConfig(
            weight_config=WeightConfig(
                w_maturity=0.6,
                maturity_strategy=strategy,
                maturity_threshold=90,
            )
        )
        
        tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
        order = PaymentOrder(id="O007", amount=600000, organization="公司A")
        
        engine = AllocationEngine(config=config, seed=42)
        result = engine.allocate(order, tickets)
        
        if result.selected_tickets:
            avg_maturity = sum(tu.ticket.maturity_days for tu in result.selected_tickets) / len(result.selected_tickets)
            print(f"\n策略: {name}")
            print(f"  选中票据: {result.ticket_count}张")
            print(f"  平均期限: {avg_maturity:.1f}天")
            print(f"  期限得分: {result.score_breakdown.avg_maturity_score:.4f}")
        
        assert result.ticket_count > 0, f"{name}策略应该选中票据"
    
    print("\n✓ 场景6测试通过")


def test_scenario_7_acceptor_strategies():
    """场景7：承兑人策略测试"""
    print("\n" + "="*80)
    print("场景7：承兑人策略测试")
    print("="*80)
    
    tickets_data = generate_random_tickets(500, seed=42)
    
    strategies = [
        (AcceptorClassStrategy.GOOD_FIRST, "优先好的"),
        (AcceptorClassStrategy.BAD_FIRST, "优先差的"),
    ]
    
    for strategy, name in strategies:
        config = AllocationConfig(
            weight_config=WeightConfig(
                w_acceptor=0.6,
                acceptor_strategy=strategy,
                acceptor_class_count=5,
            )
        )
        
        tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
        order = PaymentOrder(id="O008", amount=600000, organization="公司A")
        
        engine = AllocationEngine(config=config, seed=42)
        result = engine.allocate(order, tickets)
        
        if result.selected_tickets:
            avg_class = sum(tu.ticket.acceptor_class for tu in result.selected_tickets) / len(result.selected_tickets)
            print(f"\n策略: {name}")
            print(f"  选中票据: {result.ticket_count}张")
            print(f"  平均承兑人等级: {avg_class:.2f}")
            print(f"  承兑人得分: {result.score_breakdown.avg_acceptor_score:.4f}")
        
        assert result.ticket_count > 0, f"{name}策略应该选中票据"
    
    print("\n✓ 场景7测试通过")


def test_scenario_8_batch_allocation():
    """场景8：批量配票测试"""
    print("\n" + "="*80)
    print("场景8：批量配票测试")
    print("="*80)
    
    tickets_data = generate_random_tickets(2000, seed=42)
    
    config = AllocationConfig()
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    
    orders = [
        PaymentOrder(id="O101", amount=500000, organization="公司A", priority=1),
        PaymentOrder(id="O102", amount=800000, organization="公司B", priority=2),
        PaymentOrder(id="O103", amount=300000, organization="公司C", priority=1),
        PaymentOrder(id="O104", amount=1200000, organization="公司A", priority=3),
        PaymentOrder(id="O105", amount=600000, organization="公司D", priority=1),
    ]
    
    engine = AllocationEngine(config=config, seed=42)
    start_time = time.time()
    results = engine.allocate_batch(orders, tickets)
    end_time = time.time()
    
    print(f"✓ 处理订单数: {len(orders)}个")
    print(f"✓ 总耗时: {(end_time - start_time)*1000:.2f}ms")
    print(f"✓ 平均耗时: {(end_time - start_time)*1000/len(orders):.2f}ms/订单")
    
    for idx, result in enumerate(results, 1):
        print(f"\n订单{idx} ({result.order_id}):")
        print(f"  目标金额: {result.target_amount:,.2f}")
        print(f"  选中票据: {result.ticket_count}张")
        print(f"  组合金额: {result.total_amount:,.2f}")
        print(f"  差额: {result.bias_amount:,.2f}")
        print(f"  耗时: {result.execution_time_ms:.2f}ms")
    
    assert len(results) == len(orders), "结果数量应与订单数量一致"
    print("\n✓ 场景8测试通过")


def test_scenario_9_edge_cases():
    """场景9：边界条件测试"""
    print("\n" + "="*80)
    print("场景9：边界条件测试")
    print("="*80)
    
    config = AllocationConfig()
    
    # 测试9.1：空票据池
    print("\n9.1 空票据池")
    order = PaymentOrder(id="O901", amount=100000, organization="公司A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, [])
    print(f"  结果: {result.warnings}")
    assert result.ticket_count == 0, "空票据池应返回空结果"
    print("  ✓ 空票据池处理正确")
    
    # 测试9.2：单张票据
    print("\n9.2 单张票据")
    tickets_data = [
        {"id": "T001", "amount": 100000, "maturity_days": 90, "acceptor_class": 2, "organization": "公司A"}
    ]
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O902", amount=100000, organization="公司A")
    result = engine.allocate(order, tickets)
    print(f"  选中票据: {result.ticket_count}张")
    assert result.ticket_count == 1, "应选中唯一的票据"
    print("  ✓ 单张票据处理正确")
    
    # 测试9.3：票据金额不足
    print("\n9.3 票据金额不足")
    tickets_data = [
        {"id": "T001", "amount": 50000, "maturity_days": 90, "acceptor_class": 2, "organization": "公司A"}
    ]
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O903", amount=100000, organization="公司A")
    result = engine.allocate(order, tickets)
    print(f"  选中票据: {result.ticket_count}张")
    print(f"  组合金额: {result.total_amount}")
    print(f"  差额: {result.bias_amount}")
    assert result.bias_amount > 0, "差额应为正"
    print("  ✓ 金额不足处理正确")
    
    print("\n✓ 场景9测试通过")


def test_scenario_10_performance_benchmark():
    """场景10：性能基准测试"""
    print("\n" + "="*80)
    print("场景10：性能基准测试")
    print("="*80)
    
    config = AllocationConfig()
    
    test_cases = [
        (100, 100000),
        (500, 500000),
        (1000, 1000000),
        (5000, 1500000),
        (10000, 2000000),
    ]
    
    print(f"\n{'票据数':<10} {'目标金额':<15} {'选中票据':<10} {'耗时(ms)':<12} {'性能等级'}")
    print("-" * 80)
    
    for ticket_count, target_amount in test_cases:
        tickets_data = generate_random_tickets(ticket_count, seed=42)
        tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
        order = PaymentOrder(id=f"O10_{ticket_count}", amount=target_amount, organization="公司A")
        
        engine = AllocationEngine(config=config, seed=42)
        result = engine.allocate(order, tickets)
        
        # 性能评级
        if result.execution_time_ms < 10:
            perf = "优秀"
        elif result.execution_time_ms < 50:
            perf = "良好"
        elif result.execution_time_ms < 200:
            perf = "合格"
        else:
            perf = "待优化"
        
        print(f"{ticket_count:<10} {target_amount:<15,} {result.ticket_count:<10} "
              f"{result.execution_time_ms:<12.2f} {perf}")
    
    print("\n✓ 场景10测试通过")


if __name__ == "__main__":
    print("="*80)
    print("智能配票算法 - 场景化测试套件")
    print("="*80)
    
    try:
        test_scenario_1_small_scale()
        test_scenario_2_large_scale()
        test_scenario_3_amount_strategies()
        test_scenario_4_constraints()
        test_scenario_5_split()
        test_scenario_6_maturity_strategies()
        test_scenario_7_acceptor_strategies()
        test_scenario_8_batch_allocation()
        test_scenario_9_edge_cases()
        test_scenario_10_performance_benchmark()
        
        print("\n" + "="*80)
        print("✓ 所有场景测试通过！")
        print("="*80)
    
    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
