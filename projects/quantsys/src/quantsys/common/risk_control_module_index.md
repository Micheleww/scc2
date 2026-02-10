# 风控模块文件索引

**模块路径**: `src/quantsys/common/`  
**最后更新**: 2026-01-20

## 核心风控文件

### 1. 风险管理器
- **文件**: `risk_manager.py`
- **类**: `RiskManager`, `RiskVerdict`
- **功能**: 全局风控总闸，实现各种风险控制机制
- **状态**: ✅ 已增强（添加订单拆分防护和pending跟踪）

### 2. 订单时间窗口跟踪器
- **文件**: `order_window_tracker.py`
- **类**: `OrderWindowTracker`, `WindowOrder`
- **功能**: 防止订单拆分攻击，跟踪时间窗口内的累计订单金额
- **状态**: ✅ 新建

### 3. Pending订单跟踪器
- **文件**: `pending_order_tracker.py`
- **类**: `PendingOrderTracker`, `PendingOrder`, `OrderStatus`
- **功能**: 准确跟踪所有pending订单，用于风险控制
- **状态**: ✅ 新建

## 相关文件

### 执行层风控
- `../execution/guards/risk_guard.py` - Runtime Guard，验证RiskVerdict
- `../execution/risk_gate.py` - 统一风险门禁
- `../execution/order_validator.py` - 订单验证器

### 策略层风控
- `strategy_risk_budget.py` - 策略风险预算管理

### 其他工具
- `black_swan_mode.py` - 黑天鹅模式管理
- `rate_limiter.py` - 速率限制器

## 导入示例

```python
# 导入核心风控模块
from quantsys.common.risk_manager import RiskManager, RiskVerdict
from quantsys.common.order_window_tracker import OrderWindowTracker
from quantsys.common.pending_order_tracker import PendingOrderTracker, OrderStatus

# 使用示例
risk_manager = RiskManager(config)
# OrderWindowTracker和PendingOrderTracker已自动集成到RiskManager中
```

## 文档

- `risk_manager_enhancements.md` - 增强功能说明
- `../docs/REPORT/security/RISK_CONTROL_VULNERABILITY_AUDIT.md` - 安全审计报告
- `../docs/REPORT/security/RISK_CONTROL_FIXES.md` - 修复报告
- `../docs/REPORT/security/RISK_CONTROL_ENHANCEMENTS_COMPLETE.md` - 增强功能完成报告
