---
oid: 01KGEJFV4G3CQGZYQS3TKTP81Q
layer: DOCOPS
primary_unit: V.GUARD
tags: [V.VERDICT]
status: active
---

# FreqUI 集成说明

## 概述

**FreqUI 仍然可以使用！** 它作为前端UI，通过API与后端通信。由于我们的Trading Engine实现了完整的Freqtrade API兼容层，FreqUI可以无缝使用。

## 当前状态

### FreqUI 是什么？
- FreqUI 是 Freqtrade 的官方 Web UI 前端
- 基于 Vue.js 构建
- 通过 RESTful API 与后端通信
- 位于 `frequi-main/` 目录

### 我们的替代方案
- ✅ **后端已替代**: Trading Engine 完全替代了 Freqtrade 后端
- ✅ **API兼容**: 所有 Freqtrade API 端点都已实现
- ✅ **FreqUI可用**: FreqUI 前端仍然可以使用，因为它只依赖API

## 使用方式

### 方式1: 使用现有FreqUI（推荐）

FreqUI 仍然可以使用，因为：

1. **API完全兼容** - Trading Engine 实现了所有 Freqtrade API
2. **无需修改** - FreqUI 前端代码无需修改
3. **无缝切换** - 只需将后端从 Freqtrade 切换到 Trading Engine

#### 启动步骤：

1. **启动 Trading Engine API服务器**:
   ```bash
   python scripts/start_trading_engine.py webserver \
       --config configs/trading_engine_config.json \
       --strategy SimpleStrategy
   ```

2. **启动 FreqUI** (如果需要独立运行):
   ```bash
   cd frequi-main
   npm install
   npm run dev
   ```

3. **访问 FreqUI**: 
   - 如果FreqUI集成在ui-tars中: `http://localhost:3000/quantsys/frequi`
   - 如果独立运行: `http://localhost:3000`

### 方式2: 使用Streamlit Dashboard（已存在）

项目中已有 Streamlit 版本的 Dashboard:
- 位置: `tools/freqtrade_ui_streamlit/app.py`
- 功能: 完整的交易监控面板
- 状态: 可以使用，但需要适配新的API

### 方式3: 使用ui-tars集成（当前使用）

前端代码中已有FreqUI集成:
- 位置: `tools/ui-tars-desktop/apps/ui-tars/src/renderer/src/pages/quantsys/frequi.tsx`
- 方式: 通过iframe加载FreqUI
- 状态: ✅ 可以使用

## 技术细节

### FreqUI需要的API端点

FreqUI需要以下API端点，我们的Trading Engine都已实现：

| API端点 | 状态 | 说明 |
|---------|------|------|
| `GET /api/v1/ping` | ✅ | 健康检查 |
| `GET /api/v1/status` | ✅ | 获取状态 |
| `GET /api/v1/balance` | ✅ | 获取余额 |
| `GET /api/v1/trades` | ✅ | 交易列表 |
| `GET /api/v1/trades/open` | ✅ | 当前持仓 |
| `GET /api/v1/profit` | ✅ | 盈亏统计 |
| `GET /api/v1/performance` | ✅ | 策略表现 |
| `GET /api/v1/whitelist` | ✅ | 白名单 |
| `GET /api/v1/blacklist` | ✅ | 黑名单 |
| `GET /api/v1/strategies` | ✅ | 策略列表 |
| `GET /api/v1/show_config` | ✅ | 获取配置 |
| `POST /api/v1/start` | ✅ | 启动机器人 |
| `POST /api/v1/stop` | ✅ | 停止机器人 |
| `POST /api/v1/force_entry` | ✅ | 强制入场 |
| `POST /api/v1/force_exit` | ✅ | 强制出场 |

### 前端集成方式

在 `tools/ui-tars-desktop/apps/ui-tars/src/renderer/src/pages/quantsys/frequi.tsx` 中：

```typescript
// FreqUI通过iframe加载
const src = `${baseUrl}/frequi`;  // baseUrl指向Freqtrade API服务器

// 检查API健康状态
const response = await fetch(`${url}/api/v1/ping`);
```

## 配置说明

### Trading Engine配置

确保Trading Engine API服务器配置正确：

```json
{
  "api_server": {
    "host": "127.0.0.1",
    "port": 8080,
    "api_key": ""
  }
}
```

### FreqUI配置

FreqUI需要配置API地址（通常在环境变量或配置文件中）：
- API地址: `http://127.0.0.1:18788/`
- 认证: Basic Auth（用户名/密码）

## 总结

### ✅ FreqUI可以使用

**FreqUI仍然可以使用，无需替换！**

原因：
1. FreqUI是前端UI，只依赖API
2. Trading Engine实现了完整的API兼容层
3. 所有API端点都已实现
4. 响应格式完全兼容

### 使用建议

1. **继续使用FreqUI** - 如果已经集成，无需修改
2. **后端切换** - 只需将后端从Freqtrade切换到Trading Engine
3. **无需修改前端** - FreqUI前端代码完全不需要修改

### 替代方案

如果不想使用FreqUI，也可以：
1. 使用Streamlit Dashboard (`tools/freqtrade_ui_streamlit/app.py`)
2. 使用ui-tars的自定义界面
3. 开发新的前端界面

## 结论

**FreqUI仍然可以使用，没有被替换！**

- ✅ 后端: Trading Engine（替代Freqtrade）
- ✅ 前端: FreqUI（继续使用）
- ✅ API: 100%兼容，无缝切换
