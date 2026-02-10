# Risk Module

## 模块职责

本模块负责风险控制、风险预算管理和风险决策，为整个系统提供风险约束。

## Contract 遵守

### 输入遵守的 Contract
- [../../docs/contracts/action_intent_contract.md](../../docs/contracts/action_intent_contract.md) - 行动意图接口契约
- [../../docs/contracts/signal_contract.md](../../docs/contracts/signal_contract.md) - 信号接口契约

### 输出遵守的 Contract
- [../../docs/contracts/signal_contract.md](../../docs/contracts/signal_contract.md) - 信号接口契约（健康度评分）

## 模块边界

### 本模块负责
- 风险预算计算
- 仓位大小决定
- 风险限制执行
- 健康度评分

### 本模块不负责
- 策略决策
- 交易执行
- 行动意图生成
- 因子计算

## 核心组件

- [budget.py](budget.py) - 风险预算管理
- [live_gate.py](live_gate.py) - 实时交易门禁

---

**注意**: 本模块负责风险控制和仓位管理，不直接参与策略决策或交易执行。