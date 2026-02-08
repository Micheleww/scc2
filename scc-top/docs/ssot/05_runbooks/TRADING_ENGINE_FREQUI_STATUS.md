---
oid: 01KGEJFVCMAN6YFDWWS9ECSG4K
layer: DOCOPS
primary_unit: V.GUARD
tags: [V.VERDICT]
status: active
---

# Trading Engine 与 FreqUI 状态说明

## 问题回答

**Q: frequi是否可以使用，还是被替换成了自建的代码？**

**A: FreqUI仍然可以使用，没有被替换！**

## 详细说明

### 1. 后端替代情况

| 组件 | 原方案 | 新方案 | 状态 |
|------|--------|--------|------|
| **后端引擎** | Freqtrade | Trading Engine | ✅ 已替代 |
| **API服务器** | Freqtrade webserver | Trading Engine API | ✅ 已替代 |
| **前端UI** | FreqUI | FreqUI | ✅ 继续使用 |

### 2. 为什么FreqUI仍然可以使用？

1. **FreqUI是前端** - 它只通过API与后端通信
2. **API完全兼容** - Trading Engine实现了所有Freqtrade API端点
3. **响应格式一致** - 所有API响应格式与Freqtrade完全兼容
4. **无需修改** - FreqUI前端代码完全不需要修改

### 3. 当前架构

```
┌─────────────────┐
│   FreqUI (前端)  │  ← 继续使用，无需修改
└────────┬────────┘
         │ HTTP API
         │ (完全兼容)
         ▼
┌─────────────────┐
│ Trading Engine  │  ← 新替代方案
│   (后端API)     │
└─────────────────┘
```

### 4. 使用方式

#### 方式1: 通过ui-tars集成（当前）

```typescript
// tools/ui-tars-desktop/apps/ui-tars/src/renderer/src/pages/quantsys/frequi.tsx
const src = `${baseUrl}/frequi`;  // baseUrl = http://127.0.0.1:18788/
```

#### 方式2: 独立运行FreqUI

```bash
cd frequi-main
npm install
npm run dev
# 访问 http://localhost:3000
# 配置API地址为 http://127.0.0.1:18788/
```

### 5. 替代了什么？

✅ **已替代**:
- Freqtrade 后端引擎
- Freqtrade webserver
- Freqtrade CLI工具

❌ **未替代**:
- FreqUI 前端（继续使用）
- Streamlit Dashboard（可选使用）

### 6. 总结

| 项目 | 状态 | 说明 |
|------|------|------|
| **后端** | ✅ 已替代 | Trading Engine完全替代Freqtrade |
| **API** | ✅ 已替代 | 100%兼容Freqtrade API |
| **前端UI** | ✅ 继续使用 | FreqUI仍然可用，无需修改 |
| **CLI工具** | ✅ 已替代 | Trading Engine CLI替代Freqtrade CLI |

## 结论

**FreqUI没有被替换，仍然可以使用！**

- 后端已完全替代（Trading Engine）
- API完全兼容（所有端点已实现）
- 前端继续使用（FreqUI无需修改）
- 无缝切换（只需启动Trading Engine替代Freqtrade）
