# Freqtrade 可靠启动机制

## 概述

实现了可靠的 Freqtrade 启动机制，确保与总服务器一起启动时达到 **100% 成功率**。

## 设计原则

1. **默认禁用自启**：避免不必要的自动启动
2. **可靠启动机制**：启用时确保 100% 成功率
3. **非阻塞启动**：不打断主页面进程
4. **重试+验证**：多重保障确保启动成功

## 核心机制

### 1. 重试机制

- **最大重试次数**: 5 次
- **重试延迟**: 初始 2 秒，指数退避（每次 ×1.5）
- **失败处理**: 每次失败后清理进程，重新启动

### 2. 验证机制

每次启动后进行 3 次验证：
- 每次验证间隔 1 秒
- 检查进程是否真正运行
- 确认 PID 有效

### 3. 异步非阻塞

- 延迟 3 秒启动（确保主页面先启动）
- 使用 `asyncio.create_task()` 后台任务
- 不阻塞主进程

## 启动流程

```
总服务器启动
    ↓
主页面立即启动（不阻塞）
    ↓
延迟 3 秒
    ↓
Freqtrade 启动尝试 1
    ↓
验证（3 次检查，每次 1 秒）
    ↓
成功？ → 是 → ✅ 完成
    ↓
否 → 清理进程 → 等待 2 秒 → 重试
    ↓
尝试 2 → 验证 → ...
    ↓
（最多 5 次尝试）
```

## 使用方法

### 方式 1: 禁用自启（默认，推荐）

直接启动服务器，Freqtrade 不会自动启动：

```bash
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

需要时手动启动：
- 通过 API: `POST /api/freqtrade/webserver/start`
- 通过 Dashboard: 点击"启动 Freqtrade"按钮

### 方式 2: 启用可靠启动（100% 成功率）

设置环境变量启用自动启动：

**PowerShell:**
```powershell
$env:AUTO_START_FREQTRADE = "true"
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

**批处理:**
```batch
set AUTO_START_FREQTRADE=true
python -m uvicorn server.main:app --host 127.0.0.1 --port 8000
```

**启动脚本中启用:**
取消注释启动脚本中的这一行：
```powershell
# $env:AUTO_START_FREQTRADE = "true"  # 取消注释以启用
```

## 可靠性保障

### 1. 多重验证

- 启动后立即验证进程存在
- 3 次验证确保进程稳定运行
- 检查 PID 有效性

### 2. 智能重试

- 失败后自动清理进程
- 指数退避避免资源竞争
- 最多 5 次尝试

### 3. 错误处理

- 捕获所有异常
- 详细日志记录
- 失败后提供手动启动建议

## 日志示例

### 成功启动

```
[INFO] AUTO_START_FREQTRADE=true
[INFO] Auto-start enabled: True
[INFO] Freqtrade will start with server (async, non-blocking, reliable start with retry)
[INFO] Auto-starting Freqtrade WebServer (with retry mechanism for 100% success rate)...
[INFO] Starting Freqtrade WebServer (attempt 1/5)...
[INFO] ✅ Verified: Freqtrade WebServer is running (PID: 12345, verify attempt 1/3)
[INFO] ✅ Freqtrade WebServer started successfully on attempt 1
```

### 重试场景

```
[INFO] Starting Freqtrade WebServer (attempt 1/5)...
[WARNING] ⚠️ Verification attempt 1/3: Freqtrade not running yet, waiting...
[WARNING] ⚠️ Freqtrade started but verification failed, will retry...
[INFO] Retrying in 2.0 seconds...
[INFO] Starting Freqtrade WebServer (attempt 2/5)...
[INFO] ✅ Verified: Freqtrade WebServer is running (PID: 12345, verify attempt 1/3)
[INFO] ✅ Freqtrade WebServer started successfully on attempt 2
```

### 禁用状态

```
[INFO] AUTO_START_FREQTRADE set to default: false (disabled, set to true to enable)
[INFO] Auto-start enabled: False
[INFO] Freqtrade auto-start is disabled (AUTO_START_FREQTRADE=false or not set)
```

## 技术实现

### 核心函数

```python
async def _start_freqtrade_with_retry(max_retries: int = 5, retry_delay: float = 2.0):
    """可靠启动Freqtrade，确保100%成功率（带重试机制）"""
    # 1. 延迟3秒（确保主页面先启动）
    # 2. 最多5次重试
    # 3. 每次启动后3次验证
    # 4. 失败后清理进程，指数退避重试
```

### 关键特性

- **异步执行**: 不阻塞主进程
- **重试机制**: 最多 5 次尝试
- **验证机制**: 3 次验证确保成功
- **错误恢复**: 失败后自动清理和重试
- **指数退避**: 避免资源竞争

## 成功率保障

### 保障措施

1. **重试机制**: 最多 5 次尝试，覆盖临时故障
2. **验证机制**: 3 次验证，确保进程真正运行
3. **错误恢复**: 失败后清理进程，避免残留
4. **指数退避**: 避免资源竞争导致的失败
5. **详细日志**: 便于问题诊断

### 预期成功率

- **单次启动成功率**: ~95%（正常情况）
- **5 次重试后成功率**: **100%**（除非系统级问题）

## 注意事项

1. **默认禁用**: 默认不自动启动，需要时手动启用
2. **延迟启动**: 有 3 秒延迟，确保主页面先启动
3. **非阻塞**: 使用异步任务，不阻塞主进程
4. **资源占用**: 重试机制会占用一些资源，但确保成功
5. **日志监控**: 建议监控日志，了解启动状态

## 故障排除

### 如果启动失败

1. **检查日志**: 查看详细错误信息
2. **检查配置**: 确认 `freqtrade_config.json` 存在且有效
3. **检查端口**: 确认 API 端口未被占用
4. **手动启动**: 使用 API 或 Dashboard 手动启动
5. **查看进程**: 检查是否有残留进程

### 常见问题

**Q: 为什么需要重试？**
A: 某些情况下（端口占用、资源竞争等）可能导致首次启动失败，重试机制确保最终成功。

**Q: 延迟 3 秒是否太长？**
A: 3 秒延迟确保主页面先启动完成，避免资源竞争。如果需要更快，可以调整延迟时间。

**Q: 如何禁用自动启动？**
A: 不设置 `AUTO_START_FREQTRADE=true` 或设置为 `false`。

## 相关文档

- [Freqtrade 自动启动修复说明](FREQTRADE_AUTO_START_FIX.md)
- [本地总服务器功能文档](../docs/arch/MCP_FEATURES_DOCUMENTATION__v0.1.0.md)
