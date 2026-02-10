# 风控模块文件清单

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

## 测试文件

### 1. 独立测试文件
- **文件**: `test_risk_modules_standalone.py`
- **功能**: 测试OrderWindowTracker和PendingOrderTracker的功能
- **状态**: ✅ 已创建

### 2. 包导入测试文件
- **文件**: `test_risk_control_modules.py`
- **功能**: 通过包导入测试模块功能
- **状态**: ✅ 已创建（可能有导入问题，使用standalone版本）

## 文档文件

### 1. 模块索引
- **文件**: `risk_control_module_index.md`
- **功能**: 模块文件索引和导入示例
- **状态**: ✅ 已创建

### 2. 功能说明
- **文件**: `risk_manager_enhancements.md`
- **功能**: 增强功能详细说明
- **状态**: ✅ 已创建

### 3. 快速开始
- **文件**: `README_RISK_CONTROL.md`
- **功能**: 模块使用说明和快速开始指南
- **状态**: ✅ 已创建

### 4. 模块文件清单
- **文件**: `MODULE_FILES.md` (本文档)
- **功能**: 模块文件清单
- **状态**: ✅ 已创建

## 模块导出

### `__init__.py` 导出

```python
from .risk_manager import RiskManager, RiskVerdict
from .order_window_tracker import OrderWindowTracker, WindowOrder
from .pending_order_tracker import PendingOrderTracker, PendingOrder, OrderStatus
```

## 使用方式

### 方式1: 通过包导入（推荐）

```python
from quantsys.common import RiskManager, OrderWindowTracker, PendingOrderTracker
```

### 方式2: 直接导入文件

```python
from quantsys.common.order_window_tracker import OrderWindowTracker
from quantsys.common.pending_order_tracker import PendingOrderTracker
from quantsys.common.risk_manager import RiskManager
```

### 方式3: 独立测试（避免包导入问题）

```python
# 在common目录下直接运行
cd src/quantsys/common
python test_risk_modules_standalone.py
```

## 文件清单总结

### 核心代码文件 (3个)
1. ✅ `risk_manager.py` - 风险管理器
2. ✅ `order_window_tracker.py` - 订单时间窗口跟踪器
3. ✅ `pending_order_tracker.py` - Pending订单跟踪器

### 测试文件 (2个)
1. ✅ `test_risk_modules_standalone.py` - 独立测试文件（推荐使用）
2. ✅ `test_risk_control_modules.py` - 包导入测试文件

### 文档文件 (4个)
1. ✅ `risk_control_module_index.md` - 模块索引
2. ✅ `risk_manager_enhancements.md` - 功能说明
3. ✅ `README_RISK_CONTROL.md` - 快速开始指南
4. ✅ `MODULE_FILES.md` - 本文档

### 配置文件 (1个)
1. ✅ `__init__.py` - 模块导出配置

## 验证

### 语法检查
```bash
python -m py_compile order_window_tracker.py pending_order_tracker.py risk_manager.py
```

### 功能测试
```bash
cd src/quantsys/common
python test_risk_modules_standalone.py
```

## 相关文档

- [安全审计报告](../../docs/REPORT/security/RISK_CONTROL_VULNERABILITY_AUDIT.md)
- [修复报告](../../docs/REPORT/security/RISK_CONTROL_FIXES.md)
- [增强功能完成报告](../../docs/REPORT/security/RISK_CONTROL_ENHANCEMENTS_COMPLETE.md)
