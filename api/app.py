"""
智能配票算法 - RESTful API服务

提供HTTP接口供外部系统调用配票服务
"""
import sys
sys.path.insert(0, '/home/engine/project')

from flask import Flask, request, jsonify
from typing import Dict, List, Any
import traceback

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


app = Flask(__name__)


def parse_config(config_dict: Dict[str, Any]) -> AllocationConfig:
    """
    解析配置字典为AllocationConfig对象
    
    参数:
        config_dict: 配置字典
        
    返回:
        AllocationConfig对象
    """
    # 解析金额标签配置
    amount_label_cfg = config_dict.get('amount_label_config', {})
    amount_label_config = AmountLabelConfig(
        large_range=tuple(amount_label_cfg.get('large_range', [1000000, float('inf')])),
        medium_range=tuple(amount_label_cfg.get('medium_range', [100000, 1000000])),
        small_range=tuple(amount_label_cfg.get('small_range', [0, 100000])),
        large_ratio=amount_label_cfg.get('large_ratio', 0.5),
        medium_ratio=amount_label_cfg.get('medium_ratio', 0.3),
        small_ratio=amount_label_cfg.get('small_ratio', 0.2),
    )
    
    # 解析权重配置
    weight_cfg = config_dict.get('weight_config', {})
    weight_config = WeightConfig(
        w_maturity=weight_cfg.get('w_maturity', 0.25),
        w_acceptor=weight_cfg.get('w_acceptor', 0.25),
        w_amount=weight_cfg.get('w_amount', 0.25),
        w_organization=weight_cfg.get('w_organization', 0.25),
        maturity_strategy=MaturityStrategy(weight_cfg.get('maturity_strategy', '优先远')),
        maturity_threshold=weight_cfg.get('maturity_threshold', 90),
        acceptor_strategy=AcceptorClassStrategy(weight_cfg.get('acceptor_strategy', '优先差的')),
        acceptor_class_count=weight_cfg.get('acceptor_class_count', 5),
        amount_strategy=AmountStrategy(weight_cfg.get('amount_strategy', '优化期望库存占比')),
        amount_sub_strategy=AmountSubStrategy(weight_cfg.get('amount_sub_strategy', '排序')) if weight_cfg.get('amount_sub_strategy') else None,
        organization_strategy=OrganizationStrategy(weight_cfg.get('organization_strategy', '优先同组织')),
    )
    
    # 解析拆票配置
    split_cfg = config_dict.get('split_config', {})
    split_config = SplitConfig(
        allow_split=split_cfg.get('allow_split', True),
        tail_diff_abs=split_cfg.get('tail_diff_abs', 10000),
        tail_diff_ratio=split_cfg.get('tail_diff_ratio', 0.3),
        min_remain=split_cfg.get('min_remain', 50000),
        min_use=split_cfg.get('min_use', 50000),
        min_ratio=split_cfg.get('min_ratio', 0.3),
        split_strategy=SplitStrategy(split_cfg.get('split_strategy', '按金额-接近差额')),
    )
    
    # 解析约束配置
    constraint_cfg = config_dict.get('constraint_config', {})
    constraint_config = ConstraintConfig(
        max_ticket_count=constraint_cfg.get('max_ticket_count', 10),
        small_ticket_limited=constraint_cfg.get('small_ticket_limited', False),
        small_ticket_80pct_amount_coverage=constraint_cfg.get('small_ticket_80pct_amount_coverage', 0.5),
    )
    
    return AllocationConfig(
        amount_label_config=amount_label_config,
        weight_config=weight_config,
        split_config=split_config,
        constraint_config=constraint_config,
        equal_amount_first=config_dict.get('equal_amount_first', False),
        equal_amount_threshold=config_dict.get('equal_amount_threshold', 1000),
    )


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'healthy',
        'service': '智能配票算法API',
        'version': '2.0'
    })


@app.route('/api/v1/allocate', methods=['POST'])
def allocate_single():
    """
    单个付款单配票接口
    
    请求体:
    {
        "order": {
            "id": "O001",
            "amount": 500000,
            "organization": "公司A",
            "priority": 0
        },
        "tickets": [
            {
                "id": "T001",
                "amount": 300000,
                "maturity_days": 90,
                "acceptor_class": 2,
                "organization": "公司A"
            },
            ...
        ],
        "config": {  // 可选，使用默认配置
            "weight_config": {...},
            "split_config": {...},
            ...
        },
        "seed": 42  // 可选，随机数种子
    }
    
    响应:
    {
        "success": true,
        "result": {...}  // 详细的配票结果
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': '请求体不能为空'
            }), 400
        
        # 解析付款单
        order_data = data.get('order')
        if not order_data:
            return jsonify({
                'success': False,
                'error': '缺少order字段'
            }), 400
        
        order = PaymentOrder(
            id=order_data['id'],
            amount=order_data['amount'],
            organization=order_data.get('organization', 'default'),
            priority=order_data.get('priority', 0),
        )
        
        # 解析票据池
        tickets_data = data.get('tickets', [])
        if not tickets_data:
            return jsonify({
                'success': False,
                'error': '票据池不能为空'
            }), 400
        
        # 解析配置
        config_data = data.get('config', {})
        config = parse_config(config_data)
        
        # 创建票据对象
        tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
        
        # 执行配票
        seed = data.get('seed')
        engine = AllocationEngine(config=config, seed=seed)
        result = engine.allocate(order, tickets)
        
        # 格式化输出
        output = format_allocation_result(result)
        
        return jsonify({
            'success': True,
            'result': output
        })
    
    except KeyError as e:
        return jsonify({
            'success': False,
            'error': f'缺少必需字段: {str(e)}'
        }), 400
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'服务器内部错误: {str(e)}'
        }), 500


@app.route('/api/v1/allocate/batch', methods=['POST'])
def allocate_batch():
    """
    批量配票接口
    
    请求体:
    {
        "orders": [
            {
                "id": "O001",
                "amount": 500000,
                "organization": "公司A",
                "priority": 1
            },
            ...
        ],
        "tickets": [...],
        "config": {...},  // 可选
        "seed": 42  // 可选
    }
    
    响应:
    {
        "success": true,
        "results": [...]  // 配票结果列表
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': '请求体不能为空'
            }), 400
        
        # 解析付款单列表
        orders_data = data.get('orders', [])
        if not orders_data:
            return jsonify({
                'success': False,
                'error': '订单列表不能为空'
            }), 400
        
        orders = [
            PaymentOrder(
                id=o['id'],
                amount=o['amount'],
                organization=o.get('organization', 'default'),
                priority=o.get('priority', 0),
            )
            for o in orders_data
        ]
        
        # 解析票据池
        tickets_data = data.get('tickets', [])
        if not tickets_data:
            return jsonify({
                'success': False,
                'error': '票据池不能为空'
            }), 400
        
        # 解析配置
        config_data = data.get('config', {})
        config = parse_config(config_data)
        
        # 创建票据对象
        tickets = create_tickets_from_data(tickets_data, config.amount_label_config)
        
        # 批量执行配票
        seed = data.get('seed')
        engine = AllocationEngine(config=config, seed=seed)
        results = engine.allocate_batch(orders, tickets)
        
        # 格式化输出
        outputs = [format_allocation_result(r) for r in results]
        
        return jsonify({
            'success': True,
            'results': outputs,
            'summary': {
                'total_orders': len(orders),
                'processed': len(results),
            }
        })
    
    except KeyError as e:
        return jsonify({
            'success': False,
            'error': f'缺少必需字段: {str(e)}'
        }), 400
    
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'服务器内部错误: {str(e)}'
        }), 500


@app.route('/api/v1/config/default', methods=['GET'])
def get_default_config():
    """获取默认配置"""
    config = AllocationConfig()
    return jsonify({
        'success': True,
        'config': {
            'amount_label_config': {
                'large_range': list(config.amount_label_config.large_range),
                'medium_range': list(config.amount_label_config.medium_range),
                'small_range': list(config.amount_label_config.small_range),
                'large_ratio': config.amount_label_config.large_ratio,
                'medium_ratio': config.amount_label_config.medium_ratio,
                'small_ratio': config.amount_label_config.small_ratio,
            },
            'weight_config': {
                'w_maturity': config.weight_config.w_maturity,
                'w_acceptor': config.weight_config.w_acceptor,
                'w_amount': config.weight_config.w_amount,
                'w_organization': config.weight_config.w_organization,
                'maturity_strategy': config.weight_config.maturity_strategy.value,
                'maturity_threshold': config.weight_config.maturity_threshold,
                'acceptor_strategy': config.weight_config.acceptor_strategy.value,
                'acceptor_class_count': config.weight_config.acceptor_class_count,
                'amount_strategy': config.weight_config.amount_strategy.value,
                'amount_sub_strategy': config.weight_config.amount_sub_strategy.value if config.weight_config.amount_sub_strategy else None,
                'organization_strategy': config.weight_config.organization_strategy.value,
            },
            'split_config': {
                'allow_split': config.split_config.allow_split,
                'tail_diff_abs': config.split_config.tail_diff_abs,
                'tail_diff_ratio': config.split_config.tail_diff_ratio,
                'min_remain': config.split_config.min_remain,
                'min_use': config.split_config.min_use,
                'min_ratio': config.split_config.min_ratio,
                'split_strategy': config.split_config.split_strategy.value,
            },
            'constraint_config': {
                'max_ticket_count': config.constraint_config.max_ticket_count,
                'small_ticket_limited': config.constraint_config.small_ticket_limited,
                'small_ticket_80pct_amount_coverage': config.constraint_config.small_ticket_80pct_amount_coverage,
            },
            'equal_amount_first': config.equal_amount_first,
            'equal_amount_threshold': config.equal_amount_threshold,
        }
    })


if __name__ == '__main__':
    print("="*80)
    print("智能配票算法 API 服务启动")
    print("="*80)
    print("访问 http://localhost:5000/health 进行健康检查")
    print("访问 http://localhost:5000/api/v1/config/default 获取默认配置")
    print("="*80)
    app.run(host='0.0.0.0', port=5000, debug=True)
