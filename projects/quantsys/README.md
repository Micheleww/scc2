# Quantsys 量化交易系统

独立的项目，包含量化交易核心引擎和相关服务。

## 项目结构

```
projects/quantsys/
├── src/quantsys/              # 量化核心代码
│   ├── adapter/               # 信号适配器
│   ├── api/                   # API管理
│   ├── automation/            # 自动化系统
│   ├── backtest/              # 回测引擎
│   ├── belief/                # 市场信念
│   ├── calibration/           # 校准系统
│   ├── common/                # 通用工具
│   ├── contracts_runtime/     # 合约运行时
│   ├── core/                  # 核心管道
│   ├── domain/                # 领域引擎
│   ├── evaluation/            # 评估系统
│   ├── execution/             # 执行系统
│   ├── factors/               # 因子系统
│   ├── models/                # 模型定义
│   ├── monitor/               # 监控系统
│   ├── portfolio/             # 投资组合
│   ├── risk/                  # 风险管理
│   ├── strategy/              # 策略系统
│   └── trading_engine/        # 交易引擎
├── configs/                   # 配置文件
├── contracts/                 # 合约定义
├── services/                  # 独立服务
│   ├── mcp_bus/              # MCP总线服务
│   ├── a2a_hub/              # A2A Hub服务
│   └── exchange_server/      # 交易所服务器
└── docs/                      # 项目文档
```

## 主要功能

- **量化交易核心引擎**: 完整的交易系统实现
- **回测系统**: 策略回测和评估
- **实时执行系统**: 实盘交易执行
- **因子系统**: 因子生成、评估和管理
- **策略系统**: 策略生成、测试和优化
- **风险管理系统**: 风险控制和监控

## 独立服务

### MCP总线服务
- 路径: `services/mcp_bus/`
- 功能: 消息总线服务
- 启动: `python server/main.py`

### A2A Hub服务
- 路径: `services/a2a_hub/`
- 功能: A2A代理通信
- 启动: `python main.py`

### 交易所服务器
- 路径: `services/exchange_server/`
- 功能: 交易所接口服务
- 启动: `python main.py`

## 依赖关系

- MCP总线服务依赖 `quantsys` 核心模块
- 其他服务相对独立

## 配置文件

配置文件位于 `configs/` 目录:
- `current/` - 当前活动配置
- `control_plane/` - 控制平面配置
- `router/` - 路由配置
- `scc/` - SCC执行配置

## 注意事项

本项目从 `scc-top/_docker_ctx_scc/` 迁移而来，已移除与SCC核心工具的重复代码。
