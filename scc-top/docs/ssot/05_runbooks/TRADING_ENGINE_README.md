---
oid: 01KGCV321RBS78VJ8235PZ0T0J
layer: CANON
primary_unit: S.CANONICAL_UPDATE
tags: [X.WORKSPACE_ADAPTER]
status: active
---

# QuantSys Trading Engine 使用指南

## 概述

QuantSys Trading Engine 是一个完全可扩展的交易执行系统，替代 freqtrade 的全部功能，并提供更好的扩展性。

## 主要功能

### 1. 核心交易引擎
- ✅ 策略框架（兼容 freqtrade 策略格式）
- ✅ 订单执行管理
- ✅ 实时交易处理
- ✅ 状态管理

### 2. 数据管理
- ✅ 多数据源支持
- ✅ 数据缓存
- ✅ 多时间周期支持
- ✅ 历史数据管理

### 3. 回测引擎
- ✅ 历史数据回测
- ✅ 性能指标计算
- ✅ 权益曲线分析
- ✅ 最大回撤计算

### 4. Web API 服务器
- ✅ RESTful API 接口
- ✅ 实时状态查询
- ✅ 交易管理
- ✅ 账户信息查询

### 5. CLI 工具
- ✅ 命令行交易
- ✅ 回测命令
- ✅ Web 服务器启动

## 快速开始

### 1. 创建策略

继承 `StrategyBase` 类创建策略：

```python
from src.quantsys.trading_engine.core.strategy_base import StrategyBase
import pandas as pd

class MyStrategy(StrategyBase):
    def populate_indicators(self, dataframe, metadata):
        # 添加技术指标
        dataframe["rsi"] = self._calculate_rsi(dataframe["close"])
        return dataframe
    
    def populate_entry_trend(self, dataframe, metadata):
        # 定义入场条件
        dataframe.loc[dataframe["rsi"] < 30, "enter_long"] = 1
        return dataframe
    
    def populate_exit_trend(self, dataframe, metadata):
        # 定义出场条件
        dataframe.loc[dataframe["rsi"] > 70, "exit_long"] = 1
        return dataframe
```

### 2. 运行交易

```bash
python scripts/trading_engine_trade.py \
    --config configs/trading_engine_config.json \
    --strategy MyStrategy
```

### 3. 运行回测

```bash
python scripts/trading_engine_backtest.py \
    --config configs/trading_engine_config.json \
    --strategy MyStrategy \
    --timerange 30d \
    --starting-balance 1000
```

### 4. 启动 Web API 服务器

```bash
python scripts/trading_engine_webserver.py \
    --config configs/trading_engine_config.json \
    --strategy MyStrategy
```

访问 `http://localhost:18788/api/v1/status` 查看状态。

## API 接口

### 健康检查
```
GET /api/v1/ping
```

### 获取状态
```
GET /api/v1/status
```

### 获取交易列表
```
GET /api/v1/trades?type=open
GET /api/v1/trades?type=closed&limit=100
```

### 获取余额
```
GET /api/v1/balance
```

### 获取持仓
```
GET /api/v1/positions
GET /api/v1/positions?symbol=BTC/USDT
```

### 启动/停止机器人
```
POST /api/v1/start
POST /api/v1/stop
```

### 强制入场/出场
```
POST /api/v1/force_entry
{
  "pair": "BTC/USDT",
  "side": "long"
}

POST /api/v1/force_exit
{
  "pair": "BTC/USDT"
}
```

## 配置说明

配置文件示例 (`configs/trading_engine_config.json`):

```json
{
  "dry_run": true,
  "max_open_trades": 3,
  "stake_currency": "USDT",
  "stake_amount": 0.01,
  "exchange": {
    "name": "okx",
    "pair_whitelist": ["BTC/USDT", "ETH/USDT"]
  },
  "data": {
    "data_dir": "data",
    "cache_enabled": true
  },
  "api_server": {
    "host": "127.0.0.1",
    "port": 8080
  }
}
```

## 与 freqtrade 的对比

| 功能 | freqtrade | QuantSys Trading Engine |
|------|-----------|------------------------|
| 策略框架 | ✅ | ✅ |
| 回测 | ✅ | ✅ |
| Web API | ✅ | ✅ |
| 多交易所 | ✅ | ✅ (通过现有 ExchangeAdapter) |
| 风险管理 | 基础 | ✅ (集成现有 RiskEngine) |
| 可扩展性 | 中等 | ✅ 高度可扩展 |
| 代码控制 | 外部依赖 | ✅ 完全自主 |

## 扩展性

### 添加新的数据源

继承 `DataProvider` 类或扩展其方法。

### 添加新的交易所

使用现有的 `ExchangeAdapter` 接口，实现新的适配器。

### 添加新的策略功能

在 `StrategyBase` 中添加新的抽象方法或钩子函数。

## 注意事项

1. **数据格式**: 确保数据文件格式正确，包含 `timestamp`, `open`, `high`, `low`, `close`, `volume` 列
2. **策略兼容性**: 现有 freqtrade 策略需要少量修改以适配新的基类
3. **实盘交易**: 设置 `dry_run: false` 前请充分测试
4. **风险管理**: 系统已集成现有的 RiskEngine，确保配置正确

## 后续开发

- [ ] 策略热加载
- [ ] 更多技术指标库
- [ ] 数据库持久化
- [ ] 实时数据流
- [ ] 更多性能指标
- [ ] 策略优化工具
