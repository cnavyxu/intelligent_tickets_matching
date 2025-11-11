"""
智能配票算法 - RESTful API服务 (FastAPI)

提供HTTP接口供外部系统调用配票服务
"""
import sys
sys.path.insert(0, '/home/engine/project')

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_validator
from typing import Dict, List, Any, Optional, Union
import traceback
from decimal import Decimal

from src import (
    AllocationEngine,
    AllocationConfig,
    PaymentOrder,
    WeightConfig,
    SplitConfig,
    ConstraintConfig,
    AmountLabelConfig,
    AmountStrategy,
    AmountSubStrategy,
    MaturityStrategy,
    AcceptorClassStrategy,
    OrganizationStrategy,
    SplitStrategy,
)
from src.utils import create_tickets_from_data, format_allocation_result
import json


class DecimalEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理Decimal类型"""
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def convert_decimals_to_str(obj):
    """递归转换对象中的所有Decimal为字符串"""
    if isinstance(obj, Decimal):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: convert_decimals_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals_to_str(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_decimals_to_str(item) for item in obj)
    return obj


app = FastAPI(
    title="智能配票算法API",
    description="提供单笔和批量配票服务",
    version="2.0",
)


# Pydantic 数据模型
class TicketData(BaseModel):
    """票据数据模型"""
    id: str = Field(..., description="票据ID")
    amount: Union[Decimal, float, int, str] = Field(..., description="票据金额")
    maturity_days: int = Field(..., ge=0, description="到期天数")
    acceptor_class: int = Field(..., ge=1, le=10, description="承兑人等级")
    organization: str = Field(default="default", description="所属组织")
    
    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v):
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float, str)):
            result = Decimal(str(v))
            if result <= 0:
                raise ValueError('amount必须大于0')
            return result
        raise ValueError('amount必须是数字类型')


class OrderData(BaseModel):
    """付款单数据模型"""
    id: str = Field(..., description="付款单ID")
    amount: Union[Decimal, float, int, str] = Field(..., description="付款金额")
    organization: str = Field(default="default", description="所属组织")
    priority: int = Field(default=0, ge=0, description="优先级")
    
    @field_validator('amount')
    @classmethod
    def validate_amount(cls, v):
        if isinstance(v, Decimal):
            return v
        if isinstance(v, (int, float, str)):
            result = Decimal(str(v))
            if result <= 0:
                raise ValueError('amount必须大于0')
            return result
        raise ValueError('amount必须是数字类型')


class AmountLabelConfigData(BaseModel):
    """金额标签配置模型"""
    large_range: List[Union[Decimal, float, int, str]] = Field(default=[1000000, "Infinity"], description="大额票范围")
    medium_range: List[Union[Decimal, float, int, str]] = Field(default=[100000, 1000000], description="中额票范围")
    small_range: List[Union[Decimal, float, int, str]] = Field(default=[0, 100000], description="小额票范围")
    large_ratio: Union[Decimal, float, str] = Field(default=0.5, description="大额票理想比例")
    medium_ratio: Union[Decimal, float, str] = Field(default=0.3, description="中额票理想比例")
    small_ratio: Union[Decimal, float, str] = Field(default=0.2, description="小额票理想比例")
    
    @field_validator('large_range', 'medium_range', 'small_range')
    @classmethod
    def validate_range(cls, v):
        if len(v) != 2:
            raise ValueError('范围必须包含两个值')
        return [Decimal(str(x)) if str(x) != 'Infinity' else Decimal('Infinity') for x in v]
    
    @field_validator('large_ratio', 'medium_ratio', 'small_ratio')
    @classmethod
    def validate_ratio(cls, v):
        result = Decimal(str(v))
        if not (0 <= result <= 1):
            raise ValueError('比例必须在0到1之间')
        return result


class WeightConfigData(BaseModel):
    """权重配置模型"""
    w_maturity: float = Field(default=0.25, ge=0, le=1, description="到期期限权重")
    w_acceptor: float = Field(default=0.25, ge=0, le=1, description="承兑人权重")
    w_amount: float = Field(default=0.25, ge=0, le=1, description="金额权重")
    w_organization: float = Field(default=0.25, ge=0, le=1, description="组织权重")
    maturity_strategy: str = Field(default="优先远", description="到期期限策略")
    maturity_threshold: int = Field(default=90, ge=0, description="到期期限阈值")
    acceptor_strategy: str = Field(default="优先差的", description="承兑人策略")
    acceptor_class_count: int = Field(default=5, ge=1, description="承兑人等级数")
    amount_strategy: str = Field(default="优化期望库存占比", description="金额策略")
    amount_sub_strategy: Optional[str] = Field(default=None, description="金额子策略")
    organization_strategy: str = Field(default="优先同组织", description="组织策略")


class SplitConfigData(BaseModel):
    """拆票配置模型"""
    allow_split: bool = Field(default=True, description="是否允许拆票")
    tail_diff_abs: Union[Decimal, float, int, str] = Field(default=10000, description="尾差绝对值阈值")
    tail_diff_ratio: Union[Decimal, float, str] = Field(default=0.3, description="尾差比例阈值")
    min_remain: Union[Decimal, float, int, str] = Field(default=50000, description="最小留存金额")
    min_use: Union[Decimal, float, int, str] = Field(default=50000, description="最小使用金额")
    min_ratio: Union[Decimal, float, str] = Field(default=0.3, description="最小拆分比例")
    split_strategy: str = Field(default="按金额-接近差额", description="拆票策略")
    
    @field_validator('tail_diff_abs', 'min_remain', 'min_use')
    @classmethod
    def validate_amount_field(cls, v):
        result = Decimal(str(v))
        if result < 0:
            raise ValueError('金额必须大于等于0')
        return result
    
    @field_validator('tail_diff_ratio', 'min_ratio')
    @classmethod
    def validate_ratio_field(cls, v):
        result = Decimal(str(v))
        if not (0 <= result <= 1):
            raise ValueError('比例必须在0到1之间')
        return result


class ConstraintConfigData(BaseModel):
    """约束配置模型"""
    max_ticket_count: int = Field(default=10, ge=1, description="最大票据张数")
    small_ticket_limited: bool = Field(default=False, description="是否限制小票占比")
    small_ticket_80pct_amount_coverage: Union[Decimal, float, str] = Field(
        default=0.5, description="小票占比阈值"
    )
    
    @field_validator('small_ticket_80pct_amount_coverage')
    @classmethod
    def validate_coverage(cls, v):
        result = Decimal(str(v))
        if not (0 <= result <= 1):
            raise ValueError('占比必须在0到1之间')
        return result


class ConfigData(BaseModel):
    """配置数据模型"""
    amount_label_config: Optional[AmountLabelConfigData] = Field(default=None)
    weight_config: Optional[WeightConfigData] = Field(default=None)
    split_config: Optional[SplitConfigData] = Field(default=None)
    constraint_config: Optional[ConstraintConfigData] = Field(default=None)
    equal_amount_first: bool = Field(default=False, description="优先精确金额匹配")
    equal_amount_threshold: Union[Decimal, float, int, str] = Field(default=1000, description="精确金额阈值")
    
    @field_validator('equal_amount_threshold')
    @classmethod
    def validate_threshold(cls, v):
        result = Decimal(str(v))
        if result < 0:
            raise ValueError('阈值必须大于等于0')
        return result


class AllocateRequest(BaseModel):
    """单笔配票请求模型"""
    order: OrderData = Field(..., description="付款单信息")
    tickets: List[TicketData] = Field(..., min_length=1, description="票据池")
    config: Optional[ConfigData] = Field(default=None, description="配置参数")
    seed: Optional[int] = Field(default=None, description="随机数种子")


class BatchAllocateRequest(BaseModel):
    """批量配票请求模型"""
    orders: List[OrderData] = Field(..., min_length=1, description="付款单列表")
    tickets: List[TicketData] = Field(..., min_length=1, description="票据池")
    config: Optional[ConfigData] = Field(default=None, description="配置参数")
    seed: Optional[int] = Field(default=None, description="随机数种子")


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str
    service: str
    version: str


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str


class SuccessResponse(BaseModel):
    """成功响应"""
    success: bool = True
    result: Optional[Dict[str, Any]] = None
    results: Optional[List[Dict[str, Any]]] = None
    summary: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None


def parse_config(config_data: Optional[ConfigData]) -> AllocationConfig:
    """
    解析配置数据为AllocationConfig对象
    
    参数:
        config_data: 配置数据对象
        
    返回:
        AllocationConfig对象
    """
    if config_data is None:
        return AllocationConfig()
    
    # 解析金额标签配置
    amount_label_config = AmountLabelConfig()
    if config_data.amount_label_config:
        cfg = config_data.amount_label_config
        amount_label_config = AmountLabelConfig(
            large_range=tuple(cfg.large_range),
            medium_range=tuple(cfg.medium_range),
            small_range=tuple(cfg.small_range),
            large_ratio=cfg.large_ratio,
            medium_ratio=cfg.medium_ratio,
            small_ratio=cfg.small_ratio,
        )
    
    # 解析权重配置
    weight_config = WeightConfig()
    if config_data.weight_config:
        cfg = config_data.weight_config
        weight_config = WeightConfig(
            w_maturity=cfg.w_maturity,
            w_acceptor=cfg.w_acceptor,
            w_amount=cfg.w_amount,
            w_organization=cfg.w_organization,
            maturity_strategy=MaturityStrategy(cfg.maturity_strategy),
            maturity_threshold=cfg.maturity_threshold,
            acceptor_strategy=AcceptorClassStrategy(cfg.acceptor_strategy),
            acceptor_class_count=cfg.acceptor_class_count,
            amount_strategy=AmountStrategy(cfg.amount_strategy),
            amount_sub_strategy=AmountSubStrategy(cfg.amount_sub_strategy) if cfg.amount_sub_strategy else None,
            organization_strategy=OrganizationStrategy(cfg.organization_strategy),
        )
    
    # 解析拆票配置
    split_config = SplitConfig()
    if config_data.split_config:
        cfg = config_data.split_config
        split_config = SplitConfig(
            allow_split=cfg.allow_split,
            tail_diff_abs=cfg.tail_diff_abs,
            tail_diff_ratio=cfg.tail_diff_ratio,
            min_remain=cfg.min_remain,
            min_use=cfg.min_use,
            min_ratio=cfg.min_ratio,
            split_strategy=SplitStrategy(cfg.split_strategy),
        )
    
    # 解析约束配置
    constraint_config = ConstraintConfig()
    if config_data.constraint_config:
        cfg = config_data.constraint_config
        constraint_config = ConstraintConfig(
            max_ticket_count=cfg.max_ticket_count,
            small_ticket_limited=cfg.small_ticket_limited,
            small_ticket_80pct_amount_coverage=cfg.small_ticket_80pct_amount_coverage,
        )
    
    return AllocationConfig(
        amount_label_config=amount_label_config,
        weight_config=weight_config,
        split_config=split_config,
        constraint_config=constraint_config,
        equal_amount_first=config_data.equal_amount_first,
        equal_amount_threshold=config_data.equal_amount_threshold,
    )


@app.get("/health", response_model=HealthResponse, summary="健康检查", tags=["系统"])
def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "智能配票算法API",
        "version": "2.0"
    }


@app.post(
    "/api/v1/allocate",
    response_model=SuccessResponse,
    summary="单笔配票",
    tags=["配票"],
    responses={
        200: {"description": "配票成功"},
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"},
    }
)
def allocate_single(request: AllocateRequest):
    """
    单个付款单配票接口
    
    - **order**: 付款单信息（id、amount、organization、priority）
    - **tickets**: 票据池列表
    - **config**: 可选配置参数
    - **seed**: 可选随机数种子
    """
    try:
        # 创建付款单对象
        order = PaymentOrder(
            id=request.order.id,
            amount=request.order.amount,
            organization=request.order.organization,
            priority=request.order.priority,
        )
        
        # 解析配置
        config = parse_config(request.config)
        
        # 创建票据对象
        tickets_data = [ticket.model_dump() for ticket in request.tickets]
        tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
        
        # 执行配票
        engine = AllocationEngine(config=config, seed=request.seed)
        result = engine.allocate(order, tickets)
        
        # 格式化输出
        output = format_allocation_result(result)
        # 转换Decimal为字符串以支持JSON序列化
        output = convert_decimals_to_str(output)
        
        return {
            "success": True,
            "result": output
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"参数错误: {str(e)}"
        )
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"服务器内部错误: {str(e)}"
        )


@app.post(
    "/api/v1/allocate/batch",
    response_model=SuccessResponse,
    summary="批量配票",
    tags=["配票"],
    responses={
        200: {"description": "配票成功"},
        400: {"model": ErrorResponse, "description": "请求参数错误"},
        500: {"model": ErrorResponse, "description": "服务器内部错误"},
    }
)
def allocate_batch(request: BatchAllocateRequest):
    """
    批量配票接口
    
    - **orders**: 付款单列表
    - **tickets**: 票据池列表
    - **config**: 可选配置参数
    - **seed**: 可选随机数种子
    """
    try:
        # 创建付款单对象列表
        orders = [
            PaymentOrder(
                id=o.id,
                amount=o.amount,
                organization=o.organization,
                priority=o.priority,
            )
            for o in request.orders
        ]
        
        # 解析配置
        config = parse_config(request.config)
        
        # 创建票据对象
        tickets_data = [ticket.model_dump() for ticket in request.tickets]
        tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
        
        # 批量执行配票
        engine = AllocationEngine(config=config, seed=request.seed)
        results = engine.allocate_batch(orders, tickets)
        
        # 格式化输出
        outputs = [format_allocation_result(r) for r in results]
        # 转换Decimal为字符串以支持JSON序列化
        outputs = convert_decimals_to_str(outputs)
        
        return {
            "success": True,
            "results": outputs,
            "summary": {
                "total_orders": len(orders),
                "processed": len(results),
            }
        }
    
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"参数错误: {str(e)}"
        )
    
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"服务器内部错误: {str(e)}"
        )


@app.get(
    "/api/v1/config/default",
    response_model=SuccessResponse,
    summary="获取默认配置",
    tags=["配置"]
)
def get_default_config():
    """获取默认配置"""
    config = AllocationConfig()
    config_dict = {
        "success": True,
        "config": {
            "amount_label_config": {
                "large_range": list(config.amount_label_config.large_range),
                "medium_range": list(config.amount_label_config.medium_range),
                "small_range": list(config.amount_label_config.small_range),
                "large_ratio": config.amount_label_config.large_ratio,
                "medium_ratio": config.amount_label_config.medium_ratio,
                "small_ratio": config.amount_label_config.small_ratio,
            },
            "weight_config": {
                "w_maturity": config.weight_config.w_maturity,
                "w_acceptor": config.weight_config.w_acceptor,
                "w_amount": config.weight_config.w_amount,
                "w_organization": config.weight_config.w_organization,
                "maturity_strategy": config.weight_config.maturity_strategy.value,
                "maturity_threshold": config.weight_config.maturity_threshold,
                "acceptor_strategy": config.weight_config.acceptor_strategy.value,
                "acceptor_class_count": config.weight_config.acceptor_class_count,
                "amount_strategy": config.weight_config.amount_strategy.value,
                "amount_sub_strategy": config.weight_config.amount_sub_strategy.value if config.weight_config.amount_sub_strategy else None,
                "organization_strategy": config.weight_config.organization_strategy.value,
            },
            "split_config": {
                "allow_split": config.split_config.allow_split,
                "tail_diff_abs": config.split_config.tail_diff_abs,
                "tail_diff_ratio": config.split_config.tail_diff_ratio,
                "min_remain": config.split_config.min_remain,
                "min_use": config.split_config.min_use,
                "min_ratio": config.split_config.min_ratio,
                "split_strategy": config.split_config.split_strategy.value,
            },
            "constraint_config": {
                "max_ticket_count": config.constraint_config.max_ticket_count,
                "small_ticket_limited": config.constraint_config.small_ticket_limited,
                "small_ticket_80pct_amount_coverage": config.constraint_config.small_ticket_80pct_amount_coverage,
            },
            "equal_amount_first": config.equal_amount_first,
            "equal_amount_threshold": config.equal_amount_threshold,
        }
    }
    # 转换Decimal为字符串以支持JSON序列化
    return convert_decimals_to_str(config_dict)


if __name__ == '__main__':
    import uvicorn
    
    print("="*80)
    print("智能配票算法 API 服务启动 (FastAPI)")
    print("="*80)
    print("访问 http://localhost:8000/docs 查看交互式API文档 (Swagger UI)")
    print("访问 http://localhost:8000/redoc 查看API文档 (ReDoc)")
    print("访问 http://localhost:8000/health 进行健康检查")
    print("访问 http://localhost:8000/api/v1/config/default 获取默认配置")
    print("="*80)
    
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
