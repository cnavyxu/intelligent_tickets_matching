# 智能配票算法 API 文档

## 概述

智能配票算法API提供RESTful接口，支持单笔和批量配票操作。

## 启动服务

```bash
cd /home/engine/project
python api/app.py
```

服务默认运行在 `http://localhost:5000`

## API 接口

### 1. 健康检查

**接口**: `GET /health`

**响应示例**:
```json
{
  "status": "healthy",
  "service": "智能配票算法API",
  "version": "2.0"
}
```

### 2. 获取默认配置

**接口**: `GET /api/v1/config/default`

**响应示例**:
```json
{
  "success": true,
  "config": {
    "weight_config": {
      "w_maturity": 0.25,
      "w_acceptor": 0.25,
      "w_amount": 0.25,
      "w_organization": 0.25,
      ...
    },
    ...
  }
}
```

### 3. 单笔配票

**接口**: `POST /api/v1/allocate`

**请求体**:
```json
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
    {
      "id": "T002",
      "amount": 250000,
      "maturity_days": 60,
      "acceptor_class": 1,
      "organization": "公司B"
    }
  ],
  "config": {
    "weight_config": {
      "w_amount": 0.5,
      "amount_strategy": "大额优先"
    }
  },
  "seed": 42
}
```

**响应示例**:
```json
{
  "success": true,
  "result": {
    "基本信息": {
      "付款单ID": "O001",
      "目标金额": 500000,
      "票据组合金额": 500000,
      "差额": 0
    },
    "选中票据组合": [
      {
        "票据ID": "T001",
        "票据金额": 300000,
        "使用金额": 300000,
        "留存金额": 0,
        "是否被拆分": false,
        "得分": {
          "总分": "0.8523",
          "到期期限得分": "0.7500",
          "承兑人得分": "0.8000",
          "金额得分": "0.9500",
          "组织得分": "1.0000"
        }
      }
    ],
    "票据统计": {
      "票据数量": 2,
      "拆分票据数量": 0
    },
    "选票结构分布": {
      "大额票": {"数量": 0, "占比": "0.00%", "金额": 0},
      "中额票": {"数量": 2, "占比": "100.00%", "金额": 500000},
      "小额票": {"数量": 0, "占比": "0.00%", "金额": 0}
    },
    "选票组合得分": {
      "总得分": "0.8523",
      "得分明细": {
        "平均到期期限得分": "0.7500",
        "平均承兑人得分": "0.8000",
        "平均金额得分": "0.9000",
        "平均组织得分": "0.5000"
      }
    },
    "执行信息": {
      "选票耗时(毫秒)": "2.35",
      "约束满足": true,
      "警告信息": []
    }
  }
}
```

### 4. 批量配票

**接口**: `POST /api/v1/allocate/batch`

**请求体**:
```json
{
  "orders": [
    {
      "id": "O001",
      "amount": 500000,
      "organization": "公司A",
      "priority": 1
    },
    {
      "id": "O002",
      "amount": 800000,
      "organization": "公司B",
      "priority": 2
    }
  ],
  "tickets": [...],
  "config": {...},
  "seed": 42
}
```

**响应示例**:
```json
{
  "success": true,
  "results": [
    {...},  // 第一个订单的配票结果
    {...}   // 第二个订单的配票结果
  ],
  "summary": {
    "total_orders": 2,
    "processed": 2
  }
}
```

## 配置说明

### 权重配置 (weight_config)

- `w_maturity`: 到期期限权重 (0-1)
- `w_acceptor`: 承兑人权重 (0-1)
- `w_amount`: 金额权重 (0-1)
- `w_organization`: 组织权重 (0-1)
- `maturity_strategy`: 到期期限策略 ("优先远" | "优先近")
- `acceptor_strategy`: 承兑人策略 ("优先好的" | "优先差的")
- `amount_strategy`: 金额策略 ("大额优先" | "小额优先" | "优化期望库存占比" | "整票金额小于等于付款单金额" | "单票金额大于等于付款单金额" | "金额随机")
- `amount_sub_strategy`: 金额子策略 ("随机" | "排序")

### 拆票配置 (split_config)

- `allow_split`: 是否允许拆票 (boolean)
- `tail_diff_abs`: 尾差绝对值阈值
- `tail_diff_ratio`: 尾差比例阈值
- `min_remain`: 最小留存金额
- `min_use`: 最小使用金额
- `min_ratio`: 最小拆分比例

### 约束配置 (constraint_config)

- `max_ticket_count`: 最大票据张数
- `small_ticket_limited`: 是否限制小票占比
- `small_ticket_80pct_amount_coverage`: 小票占比阈值

## 测试示例

### 使用 curl 测试

```bash
# 健康检查
curl http://localhost:5000/health

# 获取默认配置
curl http://localhost:5000/api/v1/config/default

# 单笔配票
curl -X POST http://localhost:5000/api/v1/allocate \
  -H "Content-Type: application/json" \
  -d '{
    "order": {
      "id": "O001",
      "amount": 500000,
      "organization": "公司A"
    },
    "tickets": [
      {
        "id": "T001",
        "amount": 300000,
        "maturity_days": 90,
        "acceptor_class": 2,
        "organization": "公司A"
      }
    ]
  }'
```

### 使用 Python 测试

```python
import requests
import json

url = "http://localhost:5000/api/v1/allocate"
data = {
    "order": {
        "id": "O001",
        "amount": 500000,
        "organization": "公司A"
    },
    "tickets": [
        {
            "id": "T001",
            "amount": 300000,
            "maturity_days": 90,
            "acceptor_class": 2,
            "organization": "公司A"
        }
    ]
}

response = requests.post(url, json=data)
result = response.json()
print(json.dumps(result, indent=2, ensure_ascii=False))
```

## 性能指标

- 1万票据池，200万付款金额：< 200ms
- 1千票据池，100万付款金额：< 50ms
- 100票据池，10万付款金额：< 10ms

## 错误处理

API返回标准HTTP状态码：

- `200`: 成功
- `400`: 请求参数错误
- `500`: 服务器内部错误

错误响应格式：
```json
{
  "success": false,
  "error": "错误描述"
}
```
