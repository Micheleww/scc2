# RiskManager 增强功能说明

## 新增功能

### 1. 订单时间窗口跟踪器 (OrderWindowTracker)

**目的**: 防止订单拆分攻击

**功能**:
- 跟踪指定时间窗口（默认60秒）内的所有订单
- 限制时间窗口内的累计订单金额
- 自动清理过期订单

**配置参数**:
- `order_window_seconds`: 时间窗口大小（秒），默认60
- `max_window_amount`: 时间窗口内最大累计金额（USDT），默认2倍单笔订单限制

**使用示例**:
```python
# 在get_risk_verdict()中自动使用
verdict = risk_manager.get_risk_verdict(...)
# 如果时间窗口内累计金额超限，订单会被拒绝
```

### 2. Pending订单跟踪器 (PendingOrderTracker)

**目的**: 准确跟踪所有pending订单，改进总暴露计算的准确性

**功能**:
- 原子性地添加、更新、移除pending订单
- 自动跟踪订单状态变化
- 提供准确的pending金额统计

**使用示例**:
```python
# 添加pending订单（在订单提交时）
risk_manager.pending_order_tracker.add_order(
    order_id="order_123",
    symbol="BTC-USDT",
    side="buy",
    amount=100.0,
    price=50000.0
)

# 更新订单状态（在订单成交/取消时）
risk_manager.pending_order_tracker.update_order_status(
    order_id="order_123",
    status=OrderStatus.FILLED
)

# 获取准确的pending金额
pending_amount = risk_manager.pending_order_tracker.get_total_pending_amount()
```

## API变更

### get_risk_verdict() 新增参数

```python
def get_risk_verdict(
    ...,
    order_id: Optional[str] = None  # 新增：订单ID，用于跟踪pending订单
) -> RiskVerdict:
```

如果提供了`order_id`且订单被允许，会自动添加到pending跟踪器。

## 集成建议

### 在OrderExecution中集成

```python
# 在提交订单前
verdict = risk_manager.get_risk_verdict(
    ...,
    order_id=order_id  # 提供订单ID
)

if verdict.allow_open:
    # 提交订单
    result = exchange_adapter.place_order(...)
    
    # 如果订单被拒绝，从pending跟踪器移除
    if result.status == 'rejected':
        risk_manager.pending_order_tracker.remove_order(order_id)
    
    # 如果订单成交，更新状态
    if result.status == 'filled':
        risk_manager.pending_order_tracker.update_order_status(
            order_id, OrderStatus.FILLED
        )
```

## 安全改进

1. **防止订单拆分攻击**: 时间窗口累计检查确保无法通过拆分订单绕过单笔限制
2. **准确的pending跟踪**: 使用专门的跟踪器确保pending金额的准确性
3. **原子性操作**: 所有操作都使用锁保护，确保线程安全

## 性能考虑

- OrderWindowTracker使用deque，自动清理过期订单，内存占用小
- PendingOrderTracker使用字典，查找和更新都是O(1)
- 所有操作都使用锁保护，但锁粒度小，性能影响最小
