# Factors Module

## 模块职责

本模块负责因子计算、管理和注册，为策略模块提供因子数据。

## Contract 遵守

### 输入遵守的 Contract
- [../../docs/contracts/data_contract.md](../../docs/contracts/data_contract.md) - 数据接口契约

### 输出遵守的 Contract
- [../../docs/contracts/signal_contract.md](../../docs/contracts/signal_contract.md) - 信号接口契约

## 模块边界

### 本模块负责
- 因子计算逻辑
- 因子注册表管理
- 因子值输出
- 因子元数据管理

### 本模块不负责
- 策略决策
- 风险控制
- 交易执行
- 仓位管理

## 核心组件

- [factor_library.py](factor_library.py) - 因子库
- [registry.py](registry.py) - 因子注册表
- [factor_registry.json](factor_registry.json) - 因子注册表配置

---

**注意**: 本模块严格遵守信号接口契约，确保因子输出的一致性和可解释性。