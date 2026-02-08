---
oid: 01KGEJFTC6V4NZSQCVBJJYG9AJ
layer: ARCH
primary_unit: A.PLANNER
tags: [S.ADR]
status: active
---

# Trading Engine Freqtrade API 兼容性文档

## 概述

QuantSys Trading Engine 实现了完整的 Freqtrade API 兼容层，前端可以无缝切换到新的交易引擎。

## 已实现的API端点

### 基础功能
- ✅ `GET /api/v1/ping` - 健康检查
- ✅ `GET /api/v1/status` - 获取交易状态
- ✅ `GET /api/v1/balance` - 获取账户余额

### 交易管理
- ✅ `GET /api/v1/trades` - 获取交易列表
- ✅ `GET /api/v1/trades/open` - 获取当前持仓
- ✅ `GET /api/v1/profit` - 获取盈亏统计
- ✅ `GET /api/v1/performance` - 获取策略表现

### 控制功能
- ✅ `POST /api/v1/start` - 启动交易机器人
- ✅ `POST /api/v1/stop` - 停止交易机器人
- ✅ `POST /api/v1/reload_config` - 重新加载配置

### 交易对管理
- ✅ `GET /api/v1/whitelist` - 获取交易对白名单
- ✅ `GET /api/v1/blacklist` - 获取交易对黑名单

### 策略管理
- ✅ `GET /api/v1/strategies` - 获取策略列表
- ✅ `GET /api/v1/show_config` - 获取配置

### 强制交易
- ✅ `POST /api/v1/force_entry` - 强制入场
- ✅ `POST /api/v1/force_exit` - 强制出场

## 响应格式

所有API响应格式与Freqtrade完全兼容：

### 状态响应
```json
{
  "state": "running",
  "trade_count": 2,
  "max_open_trades": 3,
  "strategy": "SimpleStrategy",
  "dry_run": true
}
```

### 交易列表响应
```json
[
  {
    "trade_id": "order_123",
    "pair": "BTC/USDT",
    "is_open": true,
    "is_short": false,
    "amount": 0.01,
    "stake_amount": 0.01,
    "stake_currency": "USDT",
    "open_date": "2026-01-25T10:00:00",
    "open_timestamp": 1706176800,
    "open_rate": 50000.0,
    "current_rate": 51000.0,
    "profit_abs": 10.0,
    "profit_ratio": 0.02,
    "profit_pct": 2.0
  }
]
```

## 前端集成

### 1. 更新API地址

前端代码中，将Freqtrade API地址指向Trading Engine：

```typescript
// 原来
const FREQTRADE_URL = "http://127.0.0.1:18788/";

// 现在（保持不变，因为端口和路径都兼容）
const TRADING_ENGINE_URL = "http://127.0.0.1:18788/";
```

### 2. API调用无需修改

所有API调用保持完全一致，无需修改前端代码：

```typescript
// 这些调用都正常工作
await fetch(`${API_URL}/api/v1/ping`);
await fetch(`${API_URL}/api/v1/status`);
await fetch(`${API_URL}/api/v1/trades/open`);
await fetch(`${API_URL}/api/v1/balance`);
```

### 3. 启动Trading Engine

启动Trading Engine API服务器（替代freqtrade webserver）：

```bash
python scripts/start_trading_engine.py webserver \
    --config configs/trading_engine_config.json \
    --strategy SimpleStrategy
```

## 测试兼容性

运行兼容性测试：

```bash
python scripts/test_freqtrade_compat.py
```

## 迁移步骤

1. **启动Trading Engine**（替代freqtrade）
   ```bash
   python scripts/start_trading_engine.py webserver --config configs/trading_engine_config.json --strategy SimpleStrategy
   ```

2. **验证API兼容性**
   ```bash
   python scripts/test_freqtrade_compat.py
   ```

3. **前端无需修改**
   - API地址保持不变（默认8080端口）
   - API端点路径完全兼容
   - 响应格式完全兼容

4. **停止freqtrade**
   - 停止原有的freqtrade webserver
   - Trading Engine会自动接管

## 优势

1. **无缝切换** - 前端代码无需修改
2. **完全兼容** - 所有API端点都已实现
3. **功能完整** - 支持所有freqtrade核心功能
4. **可扩展** - 可以添加更多自定义功能

## 注意事项

1. **认证** - 目前使用Basic Auth（用户名/密码），与freqtrade一致
2. **端口** - 默认使用8080端口，可在配置中修改
3. **策略** - 需要指定策略名称，策略文件需在`user_data/strategies/`目录

## 后续扩展

可以添加更多freqtrade没有的功能：
- WebSocket实时数据推送
- 更详细的性能分析
- 策略优化工具
- 更多技术指标
