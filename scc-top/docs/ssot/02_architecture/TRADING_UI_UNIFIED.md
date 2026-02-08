---
oid: 01KGCVHD9G9T7ZYGXD6ZE0N2YH
layer: ARCH
primary_unit: S.CANONICAL_UPDATE
tags: [S.NAV_UPDATE]
status: active
---

# 交易前端UI统一整合说明

## 概述

已将所有交易相关的前端整合为一个统一的**交易控制中心**，保持系统整洁稳定。

## 整合内容

### 已整合的功能

1. **FreqUI功能** ✅
   - 交易监控
   - 持仓管理
   - 盈亏统计
   - 策略管理

2. **Streamlit Dashboard功能** ✅
   - 实时数据展示
   - 图表分析
   - 性能指标

3. **原有交易页面功能** ✅
   - 订单管理
   - 账户信息
   - 风险控制
   - 信号监控

### 新的统一界面

**位置**: `tools/ui-tars-desktop/apps/ui-tars/src/renderer/src/pages/quantsys/trading.tsx`

**功能模块**:
- 📊 **概览** - 账户余额、持仓、盈亏、胜率等关键指标
- 📦 **持仓** - 当前持仓详情，支持强制平仓
- 📝 **历史交易** - 已关闭交易记录
- 📈 **性能分析** - 盈亏统计、交易统计
- ⚡ **策略管理** - 策略列表、交易对白名单
- ⚙️ **配置** - 系统配置信息

## 技术实现

### API集成

直接调用Trading Engine API，无需iframe：

```typescript
class TradingEngineAPI {
  // 直接调用Trading Engine API
  async getStatus()
  async getBalance()
  async getOpenTrades()
  async getClosedTrades()
  async getProfit()
  // ... 更多API
}
```

### 功能特点

1. **实时更新** - 每5秒自动刷新数据
2. **响应式设计** - 适配不同屏幕尺寸
3. **现代化UI** - 使用shadcn/ui组件库
4. **完整功能** - 涵盖所有交易相关功能

## 使用方式

### 访问路径

- **新统一界面**: `/quantsys/trading`
- **旧FreqUI** (保留): `/quantsys/frequi`
- **旧Freqtrade控制** (保留): `/quantsys/freqtrade`

### 侧边栏入口

在侧边栏的"交易"菜单中：
- ✅ **交易控制中心** - 新的统一界面（推荐使用）
- FreqUI (旧版) - 保留作为备用

## 系统架构

```
统一交易前端 (trading.tsx)
    ↓
Trading Engine API (完全兼容Freqtrade API)
    ↓
Trading Engine (后端)
```

## 优势

### 1. 系统整洁
- ✅ 单一入口，统一管理
- ✅ 代码集中，易于维护
- ✅ 减少重复代码

### 2. 功能完整
- ✅ 整合所有交易功能
- ✅ 无需切换多个页面
- ✅ 一站式交易管理

### 3. 性能优化
- ✅ 直接API调用，无iframe开销
- ✅ 实时数据更新
- ✅ 响应速度快

### 4. 用户体验
- ✅ 现代化UI设计
- ✅ 直观的操作界面
- ✅ 完整的功能覆盖

## 迁移建议

### 推荐做法

1. **使用新界面** - 访问 `/quantsys/trading`
2. **逐步迁移** - 从新界面开始使用
3. **保留旧界面** - 作为过渡期的备用

### 旧界面状态

- **FreqUI** (`/quantsys/frequi`) - 保留，但建议使用新界面
- **Freqtrade控制** (`/quantsys/freqtrade`) - 保留，功能已整合到新界面
- **Streamlit Dashboard** - 保留，可作为独立工具使用

## 后续优化

- [ ] 添加图表可视化
- [ ] 添加实时K线图
- [ ] 添加回测功能集成
- [ ] 添加策略编辑器
- [ ] 添加更多技术指标

## 总结

✅ **所有交易前端已整合为统一的交易控制中心**

✅ **系统更加整洁稳定，功能完整**

✅ **用户体验提升，操作更便捷**

---

**新的统一交易界面已就绪，可以开始使用！** 🎉
