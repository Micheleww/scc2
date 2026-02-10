# Execution Module

## 模块职责

本模块负责交易执行、订单管理和执行反馈，将行动意图转换为具体订单并执行。

## Contract 遵守

### 输入遵守的 Contract
- [../../docs/contracts/action_intent_contract.md](../../docs/contracts/action_intent_contract.md) - 行动意图接口契约

### 输出遵守的 Contract
- [../../docs/contracts/data_contract.md](../../docs/contracts/data_contract.md) - 数据接口契约（交易记录）

## 模块边界

### 本模块负责
- 订单执行
- 执行状态管理
- 执行结果反馈
- 执行异常处理

### 本模块不负责
- 策略决策
- 风险预算计算
- 仓位大小决定
- 行动意图生成

## 核心组件

- [execution_manager.py](execution_manager.py) - 执行管理器
- [order_guard.py](order_guard.py) - 订单守卫
- [risk_controls.py](risk_controls.py) - 执行风险控制

---

**注意**: 本模块负责将行动意图转换为具体订单，并拥有最终否决权。