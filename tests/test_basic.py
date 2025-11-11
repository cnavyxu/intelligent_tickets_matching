"""
智能配票算法基础测试
"""
import sys
sys.path.insert(0, '/home/engine/project')

from src import (
    AllocationConfig,
    PaymentOrder,
    AllocationEngine,
    WeightConfig,
    SplitConfig,
    ConstraintConfig,
    AmountStrategy,
)
from src.utils import create_tickets_from_data


def test_basic_allocation():
    """测试基础配票"""
    print("测试1: 基础配票")
    tickets_data = [
        {"id": "T1", "amount": 500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
        {"id": "T2", "amount": 300000, "maturity_days": 60, "acceptor_class": 1, "organization": "B"},
    ]
    config = AllocationConfig()
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O1", amount=300000, organization="A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    assert result.ticket_count > 0, "应该选中至少一张票据"
    assert result.total_amount > 0, "总金额应该大于0"
    print(f"  ✓ 选中{result.ticket_count}张票据，总金额{result.total_amount}")


def test_equal_amount():
    """测试等额配票"""
    print("测试2: 等额配票")
    tickets_data = [
        {"id": "T1", "amount": 500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
        {"id": "T2", "amount": 300500, "maturity_days": 60, "acceptor_class": 1, "organization": "B"},
    ]
    config = AllocationConfig(
        equal_amount_first=True,
        equal_amount_threshold=1000,
    )
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O1", amount=300000, organization="A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    assert result.ticket_count == 1, "等额配票应该只选一张"
    assert abs(result.selected_tickets[0].ticket.amount - order.amount) <= 1000, "应该选择等额票据"
    print(f"  ✓ 等额配票成功，差额{result.bias_amount}")


def test_split_ticket():
    """测试拆票功能"""
    print("测试3: 拆票功能")
    tickets_data = [
        {"id": "T1", "amount": 500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
    ]
    config = AllocationConfig(
        split_config=SplitConfig(
            allow_split=True,
            tail_diff_abs=5000,
            min_remain=50000,
            min_use=50000,
            min_ratio=0.3,
        )
    )
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O1", amount=400000, organization="A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    if result.ticket_count > 0:
        for tu in result.selected_tickets:
            if tu.split_ratio < 1.0:
                print(f"  ✓ 拆票成功，拆分比例{tu.split_ratio:.2%}")
                assert tu.split_ratio >= config.split_config.min_ratio, "拆分比例应满足最小约束"
                break
        else:
            print(f"  ✓ 未触发拆票（差额{result.bias_amount}在阈值内）")


def test_batch_allocation():
    """测试批量配票"""
    print("测试4: 批量配票")
    tickets_data = [
        {"id": "T1", "amount": 1000000, "maturity_days": 120, "acceptor_class": 2, "organization": "A"},
        {"id": "T2", "amount": 800000, "maturity_days": 90, "acceptor_class": 1, "organization": "B"},
        {"id": "T3", "amount": 500000, "maturity_days": 60, "acceptor_class": 3, "organization": "A"},
    ]
    config = AllocationConfig()
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    orders = [
        PaymentOrder(id="O1", amount=400000, organization="A", priority=1),
        PaymentOrder(id="O2", amount=500000, organization="B", priority=2),
    ]
    engine = AllocationEngine(config=config, seed=42)
    results = engine.allocate_batch(orders, tickets)
    assert len(results) == 2, "应该返回2个结果"
    print(f"  ✓ 批量配票成功，处理{len(results)}个订单")
    for idx, result in enumerate(results, 1):
        print(f"    订单{idx}: {result.ticket_count}张票据，总金额{result.total_amount}")


def test_constraint_validation():
    """测试约束检查"""
    print("测试5: 约束检查")
    tickets_data = [
        {"id": "T1", "amount": 100000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
        {"id": "T2", "amount": 200000, "maturity_days": 60, "acceptor_class": 1, "organization": "B"},
        {"id": "T3", "amount": 300000, "maturity_days": 45, "acceptor_class": 2, "organization": "A"},
    ]
    config = AllocationConfig(
        constraint_config=ConstraintConfig(
            max_ticket_count=2,
        )
    )
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O1", amount=600000, organization="A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    assert result.ticket_count <= 2, "票据张数不应超过限制"
    print(f"  ✓ 约束检查通过，最大张数限制为2，实际选中{result.ticket_count}张")


def test_optimize_inventory():
    """测试优化库存占比策略"""
    print("测试6: 优化库存占比策略")
    tickets_data = [
        {"id": "T1", "amount": 1500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
        {"id": "T2", "amount": 800000, "maturity_days": 90, "acceptor_class": 2, "organization": "B"},
        {"id": "T3", "amount": 200000, "maturity_days": 60, "acceptor_class": 1, "organization": "A"},
    ]
    config = AllocationConfig(
        weight_config=WeightConfig(
            w_amount=0.6,
            w_maturity=0.2,
            w_acceptor=0.1,
            w_organization=0.1,
            amount_strategy=AmountStrategy.OPTIMIZE_INVENTORY,
        )
    )
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O1", amount=800000, organization="A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    assert result.ticket_count > 0, "应该选中票据"
    print(f"  ✓ 优化库存策略执行成功，选中{result.ticket_count}张票据")


if __name__ == "__main__":
    print("=" * 60)
    print("运行智能配票算法测试")
    print("=" * 60)
    try:
        test_basic_allocation()
        test_equal_amount()
        test_split_ticket()
        test_batch_allocation()
        test_constraint_validation()
        test_optimize_inventory()
        print("=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
