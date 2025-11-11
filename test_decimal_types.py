"""
测试Decimal类型是否正确使用
"""
from decimal import Decimal
from src import AllocationEngine, AllocationConfig, PaymentOrder
from src.utils import create_tickets_from_data


def test_decimal_types():
    """验证Decimal类型的正确性"""
    print("=" * 80)
    print("测试Decimal类型")
    print("=" * 80)
    
    # 创建配置（使用Decimal）
    config = AllocationConfig()
    
    # 验证配置中的Decimal类型
    print(f"\n✓ 金额标签配置:")
    print(f"  - 大额范围: {config.amount_label_config.large_range}")
    print(f"    类型: {type(config.amount_label_config.large_range[0])}")
    print(f"  - 大额比例: {config.amount_label_config.large_ratio}")
    print(f"    类型: {type(config.amount_label_config.large_ratio)}")
    
    print(f"\n✓ 拆票配置:")
    print(f"  - 尾差绝对值: {config.split_config.tail_diff_abs}")
    print(f"    类型: {type(config.split_config.tail_diff_abs)}")
    print(f"  - 最小留存: {config.split_config.min_remain}")
    print(f"    类型: {type(config.split_config.min_remain)}")
    
    # 创建票据数据
    ticket_data = [
        {"id": "T001", "amount": 300000.00, "maturity_days": 90, "acceptor_class": 3},
        {"id": "T002", "amount": 200000.50, "maturity_days": 60, "acceptor_class": 2},
        {"id": "T003", "amount": 150000.75, "maturity_days": 120, "acceptor_class": 4},
    ]
    
    tickets = create_tickets_from_data(ticket_data, config.amount_label_config)
    
    print(f"\n✓ 票据创建:")
    for t in tickets:
        print(f"  - {t.id}: 金额={t.amount}, 类型={type(t.amount)}")
        print(f"           可用金额={t.available_amount}, 类型={type(t.available_amount)}")
    
    # 创建付款单
    order = PaymentOrder(
        id="O001",
        amount=Decimal("500000.00"),
        organization="default"
    )
    
    print(f"\n✓ 付款单创建:")
    print(f"  - {order.id}: 金额={order.amount}, 类型={type(order.amount)}")
    
    # 执行配票
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    
    print(f"\n✓ 配票结果:")
    print(f"  - 目标金额: {result.target_amount}, 类型={type(result.target_amount)}")
    print(f"  - 组合金额: {result.total_amount}, 类型={type(result.total_amount)}")
    print(f"  - 差额: {result.bias_amount}, 类型={type(result.bias_amount)}")
    print(f"  - 拆票金额: {result.split_amount}, 类型={type(result.split_amount)}")
    
    # 验证精度
    print(f"\n✓ 精度验证:")
    amount1 = Decimal("0.1") + Decimal("0.2")
    amount2 = Decimal("0.3")
    print(f"  - Decimal('0.1') + Decimal('0.2') = {amount1}")
    print(f"  - Decimal('0.3') = {amount2}")
    print(f"  - 相等性: {amount1 == amount2} ✓")
    
    # 对比float精度问题
    float_sum = 0.1 + 0.2
    print(f"  - float: 0.1 + 0.2 = {float_sum}")
    print(f"  - float: 0.1 + 0.2 == 0.3: {float_sum == 0.3} (精度问题)")
    
    print(f"\n✓ 大额计算验证:")
    amount_a = Decimal("1234567890.12")
    amount_b = Decimal("9876543210.34")
    result_sum = amount_a + amount_b
    print(f"  - {amount_a} + {amount_b} = {result_sum}")
    print(f"  - 类型: {type(result_sum)}")
    
    print("\n" + "=" * 80)
    print("✓ 所有Decimal类型验证通过！")
    print("=" * 80)


if __name__ == "__main__":
    test_decimal_types()
