"""
智能配票算法使用示例
"""
from .models import (
    AllocationConfig,
    WeightConfig,
    SplitConfig,
    ConstraintConfig,
    PaymentOrder,
)
from .utils import create_tickets_from_data, format_allocation_result
from .allocator import AllocationEngine


def run_example():
    tickets_data = [
        {"id": "T1", "amount": 500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
        {"id": "T2", "amount": 300000, "maturity_days": 60, "acceptor_class": 1, "organization": "B"},
        {"id": "T3", "amount": 150000, "maturity_days": 45, "acceptor_class": 2, "organization": "A"},
        {"id": "T4", "amount": 800000, "maturity_days": 200, "acceptor_class": 4, "organization": "C"},
        {"id": "T5", "amount": 120000, "maturity_days": 30, "acceptor_class": 2, "organization": "A"},
    ]

    config = AllocationConfig(
        weight_config=WeightConfig(),
        split_config=SplitConfig(),
        constraint_config=ConstraintConfig(max_ticket_count=3),
        equal_amount_first=True,
        equal_amount_threshold=5000,
    )

    tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
    order = PaymentOrder(id="O1", amount=750000, organization="A")

    engine = AllocationEngine(config=config, seed=42)
    result = engine.allocate(order, tickets)
    pretty = format_allocation_result(result)
    for key, value in pretty.items():
        print(key, ":", value)


if __name__ == "__main__":
    run_example()
