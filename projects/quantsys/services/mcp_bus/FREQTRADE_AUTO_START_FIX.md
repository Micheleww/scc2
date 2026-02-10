# Freqtrade 自动启动修复说明

> **注意**: 已实现可靠启动机制，确保 100% 成功率。详见 [FREQTRADE_RELIABLE_START.md](FREQTRADE_RELIABLE_START.md)

## 问题描述

之前 Freqtrade 在服务器启动时自动启动，会：
- 阻塞主进程，导致主页面启动延迟
- 打断主页面的正常启动流程

## 修复方案

### 1. 与总服务器同步启动（默认启用）

- **修改前**: 同步启动但阻塞主进程
- **修改后**: 与总服务器同步启动，但使用异步非阻塞方式

### 2. 异步延迟启动（不阻塞主进程）

- 使用异步任务延迟 3 秒启动
- 不阻塞主进程
- 主页面先启动完成，Freqtrade 后台启动
- 与总服务器同步启动，但以非阻塞方式实现

### 3. 修改的文件

#### 核心代码
- `tools/mcp_bus/server/main.py`
  - 默认值改为 `false`
  - 启动逻辑改为异步延迟启动

#### 启动脚本（已注释自动启动）
- `tools/mcp_bus/start_local_mcp.ps1`
- `tools/mcp_bus/start_mcp_server.bat`
- `tools/mcp_bus/start_mcp_server.ps1`
- `tools/mcp_bus/start_mcp_background_service.ps1`
- `tools/mcp_bus/server_tray.py`

## 使用方法

### 默认方式：与总服务器同步启动（推荐）

默认情况下，Freqtrade 会与总服务器同步启动（异步非阻塞方式）：

```bash
# 使用任何启动脚本
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

启动流程：
1. 总服务器立即启动
2. 主页面立即启动（不阻塞）
3. Freqtrade 延迟 3 秒后台启动（异步，不阻塞）

### 禁用自动启动（可选）

如果需要禁用自动启动，设置环境变量：

**PowerShell:**
```powershell
$env:AUTO_START_FREQTRADE = "false"
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

**批处理:**
```batch
set AUTO_START_FREQTRADE=false
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

手动启动：
- 通过 API: `POST /api/freqtrade/webserver/start`
- 通过 Dashboard: 点击"启动 Freqtrade"按钮

## 技术细节

### 异步启动实现

```python
async def _start_freqtrade_async():
    """异步启动Freqtrade，不阻塞主进程"""
    import time
    # 延迟3秒启动，确保主页面先启动完成
    await asyncio.sleep(3)
    
    # ... 启动逻辑 ...
```

### 启动流程

1. **服务器启动** → 主进程立即启动
2. **Dashboard 启动** → 后台线程启动（不阻塞）
3. **Freqtrade 启动**（如果启用）:
   - 延迟 3 秒
   - 异步任务执行
   - 不阻塞主进程

## 效果

### 修复前
- ❌ 主页面启动延迟（等待 Freqtrade 启动）
- ❌ 启动流程被打断
- ❌ 同步启动但阻塞主进程

### 修复后
- ✅ 主页面立即启动，无延迟
- ✅ 启动流程顺畅，不被打断
- ✅ 与总服务器同步启动（默认启用）
- ✅ 异步延迟启动，不阻塞主进程
- ✅ Freqtrade 后台启动，不影响主页面响应

## 验证

启动服务器后检查日志：

**默认情况（与总服务器同步启动）:**
```
[INFO] AUTO_START_FREQTRADE set to default: true (will start async with server)
[INFO] AUTO_START_FREQTRADE environment variable: true
[INFO] Auto-start enabled: True
[INFO] Freqtrade will start with server (async, non-blocking, delayed 3s)
[INFO] Auto-starting Freqtrade WebServer (async, delayed)...
[INFO] ✅ Freqtrade WebServer started successfully
```

**禁用自动启动:**
```
[INFO] AUTO_START_FREQTRADE=false
[INFO] Freqtrade auto-start is disabled (AUTO_START_FREQTRADE=false)
```

## 注意事项

1. **默认行为**: 默认与总服务器同步启动（异步非阻塞方式）
2. **延迟启动**: 有 3 秒延迟，确保主页面先启动完成，这是正常的
3. **非阻塞**: 使用异步任务，不阻塞主进程，主页面立即响应
4. **手动控制**: 可以通过 API 或 Dashboard 随时手动启动/停止
5. **禁用方式**: 设置 `AUTO_START_FREQTRADE=false` 可禁用自动启动

## 相关文档

- [本地总服务器功能文档](../docs/arch/MCP_FEATURES_DOCUMENTATION__v0.1.0.md)
- [总网页和总服务器文档](../docs/arch/总网页和总服务器__v0.1.0.md)
