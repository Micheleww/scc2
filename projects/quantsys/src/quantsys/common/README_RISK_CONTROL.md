# 风控模块说明

**模块路径**: `quantsys.common`  
**最后更新**: 2026-01-20

## 模块概览

本模块包含交易系统的核心风控功能，包括：

1. **RiskManager** - 全局风控总闸
2. **OrderWindowTracker** - 订单时间窗口跟踪器（防止订单拆分攻击）
3. **PendingOrderTracker** - Pending订单跟踪器（准确跟踪pending订单）

## 快速开始

### 基本使用

```python
from quantsys.common import RiskManager, RiskVerdict

# 初始化风险管理器
config = {
    'max_single_order_amount': 1000.0,
    'total_exposure_limit': 10.0,
    'order_window_seconds': 60,  # 时间窗口大小
    'max_window_amount': 2000.0  # 时间窗口内最大累计金额
}
risk_manager = RiskManager(config)

# 获取风险评估
verdict = risk_manager.get_risk_verdict(
    symbol="BTC-USDT",
    side="buy",
    amount=0.1,
    price=50000.0,
    balance=10000.0,
    current_position=0.0,
    total_position=0.0,
    equity=10000.0,
    leverage=1.0,
    order_id="order_123"  # 提供订单ID用于跟踪
)

if verdict.allow_open:
    print("订单被允许")
else:
    print(f"订单被阻止: {verdict.blocked_reason}")
```

### 订单跟踪

```python
from quantsys.common import PendingOrderTracker, OrderStatus

# PendingOrderTracker已集成到RiskManager中
# 如果订单被允许，会自动添加到跟踪器

# 订单成交后，更新状态
risk_manager.pending_order_tracker.update_order_status(
    order_id="order_123",
    status=OrderStatus.FILLED
)

# 获取pending金额
pending_amount = risk_manager.pending_order_tracker.get_total_pending_amount(side='buy')
```

## 文件清单

### 核心文件
- `risk_manager.py` - 风险管理器（主模块）
- `order_window_tracker.py` - 订单时间窗口跟踪器
- `pending_order_tracker.py` - Pending订单跟踪器

### 文档
- `risk_manager_enhancements.md` - 增强功能说明
- `risk_control_module_index.md` - 模块文件索引
- `README_RISK_CONTROL.md` - 本文档

## 安全特性

### 1. 订单拆分攻击防护
- 时间窗口累计检查
- 自动清理过期订单
- 线程安全

### 2. Pending订单准确性
- 原子性订单管理
- 自动状态跟踪
- 准确的金额统计

### 3. 状态保护
- 私有变量防止外部修改
- 锁机制防止竞态条件
- 输入验证防止异常值

## 配置参数

### RiskManager配置

```python
config = {
    # 单笔订单风险
    'max_single_order_amount': 1000.0,  # 单笔订单最大金额（USDT）
    'max_single_order_ratio': 0.1,  # 单笔订单最大比例
    
    # 时间窗口防护（新增）
    'order_window_seconds': 60,  # 时间窗口大小（秒）
    'max_window_amount': 2000.0,  # 时间窗口内最大累计金额（USDT）
    
    # 总暴露限制
    'total_exposure_limit': 10.0,  # 总暴露限制（USDT）
    
    # 其他风险参数
    'max_daily_trades': 50,
    'max_consecutive_losses': 5,
    'max_drawdown': 0.1,
    # ... 更多参数见 risk_manager.py
}
```

## 相关文档

- [安全审计报告](../../docs/REPORT/security/RISK_CONTROL_VULNERABILITY_AUDIT.md)
- [修复报告](../../docs/REPORT/security/RISK_CONTROL_FIXES.md)
- [增强功能完成报告](../../docs/REPORT/security/RISK_CONTROL_ENHANCEMENTS_COMPLETE.md)
