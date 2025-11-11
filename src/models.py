"""
智能配票算法 - 数据模型定义
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class AmountLabel(str, Enum):
    """金额标签"""
    LARGE = "大额"
    MEDIUM = "中额"
    SMALL = "小额"


class MaturityStrategy(str, Enum):
    """到期期限策略"""
    FAR_FIRST = "优先远"
    NEAR_FIRST = "优先近"


class AcceptorClassStrategy(str, Enum):
    """承兑人分类策略"""
    GOOD_FIRST = "优先好的"
    BAD_FIRST = "优先差的"


class AmountStrategy(str, Enum):
    """票据金额策略"""
    LARGE_FIRST = "大额优先"
    SMALL_FIRST = "小额优先"
    RANDOM = "金额随机"
    LESS_THAN_ORDER = "整票金额小于等于付款单金额"
    GREATER_THAN_ORDER = "单票金额大于等于付款单金额"
    OPTIMIZE_INVENTORY = "优化期望库存占比"


class AmountSubStrategy(str, Enum):
    """金额子策略"""
    RANDOM_WITHIN = "随机"
    SORTED = "排序"


class OrganizationStrategy(str, Enum):
    """承兑组织策略"""
    SAME_ORG = "优先同组织"
    DIFF_ORG = "优先不同组织"


class SplitStrategy(str, Enum):
    """拆票策略维度"""
    BY_MATURITY = "按到期期限"
    BY_ACCEPTOR_CLASS = "按承兑人分类"
    BY_AMOUNT_LARGE = "按金额-大额优先"
    BY_AMOUNT_CLOSE = "按金额-接近差额"


@dataclass
class Ticket:
    """票据"""
    id: str
    amount: float
    maturity_days: int
    acceptor_class: int
    amount_label: AmountLabel
    organization: str
    available_amount: float = None
    
    def __post_init__(self):
        if self.available_amount is None:
            self.available_amount = self.amount


@dataclass
class PaymentOrder:
    """付款单"""
    id: str
    amount: float
    organization: str
    priority: int = 0


@dataclass
class AmountLabelConfig:
    """金额标签配置"""
    large_range: tuple = (1000000, float('inf'))
    medium_range: tuple = (100000, 1000000)
    small_range: tuple = (0, 100000)
    large_ratio: float = 0.5
    medium_ratio: float = 0.3
    small_ratio: float = 0.2


@dataclass
class WeightConfig:
    """权重配置"""
    w_maturity: float = 0.25
    w_acceptor: float = 0.25
    w_amount: float = 0.25
    w_organization: float = 0.25
    
    maturity_strategy: MaturityStrategy = MaturityStrategy.FAR_FIRST
    maturity_threshold: int = 90
    
    acceptor_strategy: AcceptorClassStrategy = AcceptorClassStrategy.BAD_FIRST
    acceptor_class_count: int = 5
    
    amount_strategy: AmountStrategy = AmountStrategy.OPTIMIZE_INVENTORY
    amount_sub_strategy: Optional[AmountSubStrategy] = None
    
    organization_strategy: OrganizationStrategy = OrganizationStrategy.SAME_ORG
    
    force_penetrate: bool = False


@dataclass
class SplitConfig:
    """拆票配置"""
    allow_split: bool = True
    tail_diff_abs: float = 10000
    tail_diff_ratio: float = 0.3
    min_remain: float = 50000
    min_use: float = 50000
    min_ratio: float = 0.3
    split_strategy: SplitStrategy = SplitStrategy.BY_AMOUNT_CLOSE
    split_condition_unlimited: bool = False


@dataclass
class ConstraintConfig:
    """约束配置"""
    max_ticket_count: int = 10
    small_ticket_limited: bool = False
    small_ticket_80pct_amount_coverage: float = 0.5
    
    allowed_maturity_days: Optional[tuple] = None
    allowed_amount_range: Optional[tuple] = None
    allowed_acceptor_classes: Optional[List[int]] = None


@dataclass
class AllocationConfig:
    """完整分配配置"""
    amount_label_config: AmountLabelConfig = field(default_factory=AmountLabelConfig)
    weight_config: WeightConfig = field(default_factory=WeightConfig)
    split_config: SplitConfig = field(default_factory=SplitConfig)
    constraint_config: ConstraintConfig = field(default_factory=ConstraintConfig)
    
    equal_amount_first: bool = False
    equal_amount_threshold: float = 1000


@dataclass
class TicketScore:
    """票据得分"""
    ticket: Ticket
    total_score: float
    maturity_score: float
    acceptor_score: float
    amount_score: float
    organization_score: float


@dataclass
class TicketUsage:
    """票据使用明细"""
    ticket: Ticket
    used_amount: float
    split_ratio: float
    score: TicketScore
    order_index: int


@dataclass
class TicketDistribution:
    """票据分布统计"""
    large_count: int = 0
    large_ratio: float = 0.0
    large_amount: float = 0.0
    medium_count: int = 0
    medium_ratio: float = 0.0
    medium_amount: float = 0.0
    small_count: int = 0
    small_ratio: float = 0.0
    small_amount: float = 0.0


@dataclass
class ScoreBreakdown:
    """得分明细"""
    avg_maturity_score: float = 0.0
    avg_acceptor_score: float = 0.0
    avg_amount_score: float = 0.0
    avg_organization_score: float = 0.0
    total_weighted_score: float = 0.0


@dataclass
class AllocationResult:
    """
    配票结果
    
    包含完整的配票信息、统计数据和性能指标
    """
    # 基础信息
    order_id: str
    target_amount: float  # 目标金额（付款单金额）
    selected_tickets: List[TicketUsage]  # 选中的票据组合
    
    # 金额统计
    total_amount: float  # 票据组合金额
    bias_amount: float  # 差额（目标金额 - 组合金额）
    wire_transfer_diff: float = 0.0  # 电汇尾差（如有）
    
    # 票据统计
    ticket_count: int = 0  # 票据数量
    split_count: int = 0  # 拆分票据数量
    split_amount: float = 0.0  # 拆票金额
    remain_amount: float = 0.0  # 留存金额
    
    # 得分信息
    total_score: float = 0.0  # 组合总得分
    score_breakdown: Optional[ScoreBreakdown] = None  # 得分明细
    
    # 票据分布
    selected_distribution: Optional[TicketDistribution] = None  # 选票结构分布
    remaining_distribution: Optional[TicketDistribution] = None  # 余票库存分布（实际）
    expected_distribution: Optional[TicketDistribution] = None  # 余票库存分布（期望）
    
    # 执行信息
    execution_time_ms: float = 0.0  # 选票耗时（毫秒）
    constraints_met: bool = True  # 约束满足情况
    warnings: List[str] = field(default_factory=list)  # 警告信息
