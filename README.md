# 智能配票算法

基于多目标优化的智能票据分配系统，用于解决金融票据的自动化、智能化配置问题。

## 项目概述

智能配票算法是一个带有多维度偏好和复杂约束的组合优化问题，可以看作是多目标背包问题（Multi-Objective Knapsack Problem）的扩展变体。系统根据付款单金额、业务偏好、约束条件，从票据池中自动选择最优票据组合。

### 核心特性

- **多维度偏好评分**：支持到期期限、承兑人分类、票据金额、承兑组织四个维度的综合评分
- **灵活的权重配置**：可自定义各维度权重和优先策略
- **智能拆票机制**：支持票据拆分以精确匹配付款单金额
- **丰富的约束条件**：支持数量限制、金额范围、小额票约束等多种业务规则
- **批量处理能力**：支持多付款单批量配票，票据池动态更新

## 项目结构

```
.
├── README.md                    # 本文件
├── 算法流程设计.md              # 算法流程设计文档
├── 智能配票算法逻辑.md          # 业务逻辑文档
├── 数学模型.md                  # 数学模型文档
├── src/                         # 源代码
│   ├── __init__.py             # 包初始化
│   ├── models.py               # 数据模型定义
│   ├── scoring.py              # 得分计算模块
│   ├── constraints.py          # 约束检查模块
│   ├── splitter.py             # 拆票模块
│   ├── allocator.py            # 核心分配引擎
│   ├── utils.py                # 工具函数
│   └── example.py              # 简单示例
└── examples/                    # 示例代码
    └── basic_example.py        # 基础示例集

```

## 快速开始

### 基础使用

```python
from src import (
    AllocationConfig,
    PaymentOrder,
    AllocationEngine,
)
from src.utils import create_tickets_from_data, format_allocation_result

# 1. 准备票据数据
tickets_data = [
    {"id": "T001", "amount": 500000, "maturity_days": 120, "acceptor_class": 3, "organization": "A"},
    {"id": "T002", "amount": 300000, "maturity_days": 60, "acceptor_class": 1, "organization": "B"},
    {"id": "T003", "amount": 150000, "maturity_days": 45, "acceptor_class": 2, "organization": "A"},
]

# 2. 创建配置和票据对象
config = AllocationConfig()
tickets = create_tickets_from_data(tickets_data, config.amount_label_config)

# 3. 创建付款单
order = PaymentOrder(id="O001", amount=450000, organization="A")

# 4. 创建分配引擎并执行配票
engine = AllocationEngine(config=config, seed=42)
result = engine.allocate(order, tickets)

# 5. 格式化输出结果
pretty_result = format_allocation_result(result)
print(pretty_result)
```

### 高级配置

#### 1. 优先等额配票

```python
from src import AllocationConfig, WeightConfig, SplitConfig

config = AllocationConfig(
    equal_amount_first=True,           # 启用等额配票优先
    equal_amount_threshold=5000,        # 等额判定阈值（元）
)
```

#### 2. 自定义权重策略

```python
from src import (
    WeightConfig,
    MaturityStrategy,
    AcceptorClassStrategy,
    AmountStrategy,
)

weight_config = WeightConfig(
    w_maturity=0.3,                     # 到期期限权重
    w_acceptor=0.3,                     # 承兑人分类权重
    w_amount=0.3,                       # 金额策略权重
    w_organization=0.1,                 # 承兑组织权重
    
    maturity_strategy=MaturityStrategy.FAR_FIRST,          # 优先远期票据
    maturity_threshold=90,                                  # 远期阈值90天
    
    acceptor_strategy=AcceptorClassStrategy.BAD_FIRST,     # 优先差的承兑人
    acceptor_class_count=5,                                 # 承兑人分类总数
    
    amount_strategy=AmountStrategy.OPTIMIZE_INVENTORY,     # 优化库存占比
)

config = AllocationConfig(weight_config=weight_config)
```

#### 3. 配置拆票规则

```python
from src import SplitConfig, SplitStrategy

split_config = SplitConfig(
    allow_split=True,                   # 允许拆票
    tail_diff_abs=10000,                # 绝对尾差阈值（元）
    tail_diff_ratio=0.3,                # 相对尾差阈值（30%）
    min_remain=50000,                   # 最小留存金额（元）
    min_use=50000,                      # 最小使用金额（元）
    min_ratio=0.3,                      # 最小使用比例（30%）
    split_strategy=SplitStrategy.BY_AMOUNT_CLOSE,  # 按接近差额选择拆票对象
)

config = AllocationConfig(split_config=split_config)
```

#### 4. 设置约束条件

```python
from src import ConstraintConfig

constraint_config = ConstraintConfig(
    max_ticket_count=10,                 # 单张付款单最大票据数
    small_ticket_limited=True,           # 启用小额票限制
    small_ticket_80pct_amount_coverage=0.5,  # 小额票前80%覆盖度要求
    
    allowed_maturity_days=(30, 180),     # 允许的到期天数范围
    allowed_amount_range=(10000, 5000000),  # 允许的金额范围
    allowed_acceptor_classes=[1, 2, 3],  # 允许的承兑人分类
)

config = AllocationConfig(constraint_config=constraint_config)
```

### 批量配票

```python
orders = [
    PaymentOrder(id="O001", amount=700000, organization="A", priority=1),
    PaymentOrder(id="O002", amount=500000, organization="B", priority=2),
    PaymentOrder(id="O003", amount=300000, organization="A", priority=0),
]

engine = AllocationEngine(config=config)
results = engine.allocate_batch(orders, tickets)

for result in results:
    print(format_allocation_result(result))
```

## 运行示例

```bash
# 运行基础示例集
python examples/basic_example.py

# 运行简单示例
python -m src.example
```

## 算法说明

### 算法流程

1. **配置解析与初始化**：合并配置参数，生成运行上下文
2. **票据预处理**：过滤不符合约束条件的票据
3. **优先等额尝试**（可选）：查找并择优选择等额票据
4. **偏好得分计算**：计算每张票据的四维度综合得分
5. **组合构建**：基于得分贪心选择票据组合
6. **拆票调节**：根据差额进行票据拆分或补充
7. **结果封装**：输出分配方案并更新票据池

### 得分计算

综合得分由四个维度加权求和：

```
总得分 = w1×到期期限得分 + w2×承兑人分类得分 + w3×金额策略得分 + w4×承兑组织得分
```

各维度支持多种策略，详见 [数学模型.md](数学模型.md)。

### 拆票机制

当组合金额与付款单金额的差额超过阈值时触发：

- **补票场景**：差额>0且超阈值，从票据池选择新票拆分补充
- **超额场景**：差额<0，从已选票据中调整使用金额

拆票需满足：
- 留存金额 ≥ 最小留存金额
- 使用金额 ≥ 最小使用金额
- 使用比例 ≥ 最小使用比例

## 文档

- [算法流程设计.md](算法流程设计.md) - 详细的算法流程说明
- [智能配票算法逻辑.md](智能配票算法逻辑.md) - 业务逻辑与需求定义
- [数学模型.md](数学模型.md) - 数学模型与符号定义

## 开发说明

### 模块说明

- **models.py**：定义票据、付款单、配置、结果等数据结构
- **scoring.py**：实现四维度得分计算逻辑
- **constraints.py**：实现各类约束条件的校验
- **splitter.py**：实现拆票选择与调节逻辑
- **allocator.py**：核心分配引擎，编排整体流程
- **utils.py**：提供工具函数和格式化输出

### 扩展建议

1. **优化算法**：引入更强的组合优化算法（整数规划、遗传算法等）
2. **策略学习**：增加在线学习模块，动态调整权重
3. **并发处理**：支持大规模票据池的并发计算
4. **可视化**：增加配票结果的图形化展示

## 许可证

本项目仅用于学习和研究目的。
