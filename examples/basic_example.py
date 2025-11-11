"""
智能配票算法基础示例
"""
import sys
sys.path.insert(0, '/home/engine/project')

from src import (
    AllocationConfig,
    WeightConfig,
    SplitConfig,
    ConstraintConfig,
    AmountLabelConfig,
    PaymentOrder,
    MaturityStrategy,
    AcceptorClassStrategy,
    AmountStrategy,
    AmountSubStrategy,
    AllocationEngine,
)
from src.utils import create_tickets_from_data, format_allocation_result


def example_1_basic():
    """示例1：基础配票"""
    print("=" * 80)
    print("示例1：基础配票 - 贪心策略")
    print("=" * 80)
    tickets_data = [
        {"id": "T001", "amount": 500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
        {"id": "T002", "amount": 300000, "maturity_days": 60, "acceptor_class": 1, "organization": "B"},
        {"id": "T003", "amount": 150000, "maturity_days": 45, "acceptor_class": 2, "organization": "A"},
        {"id": "T004", "amount": 800000, "maturity_days": 200, "acceptor_class": 4, "organization": "C"},
        {"id": "T005", "amount": 120000, "maturity_days": 30, "acceptor_class": 2, "organization": "A"},
    ]
    config = AllocationConfig()
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O001", amount=450000, organization="A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    pretty = format_allocation_result(result)
    for key, value in pretty.items():
        print(f"{key}: {value}")
    print()


def example_2_equal_amount():
    """示例2：等额配票优先"""
    print("=" * 80)
    print("示例2：等额配票优先")
    print("=" * 80)
    tickets_data = [
        {"id": "T101", "amount": 500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
        {"id": "T102", "amount": 300000, "maturity_days": 60, "acceptor_class": 1, "organization": "B"},
        {"id": "T103", "amount": 499500, "maturity_days": 45, "acceptor_class": 2, "organization": "A"},
    ]
    config = AllocationConfig(
        equal_amount_first=True,
        equal_amount_threshold=1000,
    )
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O002", amount=500000, organization="A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    pretty = format_allocation_result(result)
    for key, value in pretty.items():
        print(f"{key}: {value}")
    print()


def example_3_split():
    """示例3：拆票场景"""
    print("=" * 80)
    print("示例3：拆票场景")
    print("=" * 80)
    tickets_data = [
        {"id": "T201", "amount": 500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
        {"id": "T202", "amount": 300000, "maturity_days": 60, "acceptor_class": 1, "organization": "B"},
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
    order = PaymentOrder(id="O003", amount=450000, organization="A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    pretty = format_allocation_result(result)
    for key, value in pretty.items():
        print(f"{key}: {value}")
    print()


def example_4_optimize_inventory():
    """示例4：优化库存占比策略"""
    print("=" * 80)
    print("示例4：优化库存占比策略")
    print("=" * 80)
    tickets_data = [
        {"id": "T301", "amount": 1500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
        {"id": "T302", "amount": 800000, "maturity_days": 90, "acceptor_class": 2, "organization": "B"},
        {"id": "T303", "amount": 200000, "maturity_days": 60, "acceptor_class": 1, "organization": "A"},
        {"id": "T304", "amount": 150000, "maturity_days": 45, "acceptor_class": 2, "organization": "C"},
    ]
    config = AllocationConfig(
        amount_label_config=AmountLabelConfig(
            large_range=(1000000, float('inf')),
            medium_range=(100000, 1000000),
            small_range=(0, 100000),
            large_ratio=0.3,
            medium_ratio=0.5,
            small_ratio=0.2,
        ),
        weight_config=WeightConfig(
            w_maturity=0.2,
            w_acceptor=0.2,
            w_amount=0.5,
            w_organization=0.1,
            amount_strategy=AmountStrategy.OPTIMIZE_INVENTORY,
        )
    )
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O004", amount=950000, organization="A")
    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    pretty = format_allocation_result(result)
    for key, value in pretty.items():
        print(f"{key}: {value}")
    print()


def example_5_batch():
    """示例5：批量配票"""
    print("=" * 80)
    print("示例5：批量配票")
    print("=" * 80)
    tickets_data = [
        {"id": "T401", "amount": 1000000, "maturity_days": 120, "acceptor_class": 2, "organization": "A"},
        {"id": "T402", "amount": 800000, "maturity_days": 90, "acceptor_class": 1, "organization": "B"},
        {"id": "T403", "amount": 500000, "maturity_days": 60, "acceptor_class": 3, "organization": "A"},
        {"id": "T404", "amount": 300000, "maturity_days": 45, "acceptor_class": 2, "organization": "C"},
        {"id": "T405", "amount": 200000, "maturity_days": 30, "acceptor_class": 1, "organization": "A"},
    ]
    config = AllocationConfig()
    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    orders = [
        PaymentOrder(id="O101", amount=700000, organization="A", priority=1),
        PaymentOrder(id="O102", amount=500000, organization="B", priority=2),
        PaymentOrder(id="O103", amount=300000, organization="A", priority=0),
    ]
    engine = AllocationEngine(config=config, seed=42)
    results = engine.allocate_batch(orders, tickets)
    for idx, result in enumerate(results, 1):
        print(f"\n--- 配票结果 {idx} ---")
        pretty = format_allocation_result(result)
        for key, value in pretty.items():
            print(f"{key}: {value}")
    print()


if __name__ == "__main__":
    example_1_basic()
    example_2_equal_amount()
    example_3_split()
    example_4_optimize_inventory()
    example_5_batch()
