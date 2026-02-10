# Strategy Module

## 模块职责

本模块负责策略逻辑、信号生成和行动意图输出，将市场信念转换为可执行的行动意图。

## Contract 遵守

### 输入遵守的 Contract
- [../../docs/contracts/signal_contract.md](../../docs/contracts/signal_contract.md) - 信号接口契约

### 输出遵守的 Contract
- [../../docs/contracts/action_intent_contract.md](../../docs/contracts/action_intent_contract.md) - 行动意图接口契约

## 模块边界

### 本模块负责
- 策略逻辑实现
- 市场信念生成
- 行动意图输出
- 策略推理依据

### 本模块不负责
- 仓位大小决定
- 风险控制
- 交易执行
- 资金管理

## 核心组件

- [strategy_interface.py](strategy_interface.py) - 策略接口
- [strategy_evaluation_system.py](strategy_evaluation_system.py) - 策略评估系统

---

**注意**: 本模块严格遵守行动意图接口契约，明确禁止输出仓位和风险相关字段。