# Freqtrade自动启动问题修复指南

## 问题诊断

**症状**: Freqtrade WebServer没有随主服务器一起启动

**原因**: 当前运行的服务器启动时没有设置`AUTO_START_FREQTRADE=true`环境变量

## 解决方案

### 方法1: 使用正确的启动脚本重启服务器（推荐）

1. **停止当前服务器**
   ```powershell
   # 查找占用8000端口的进程
   netstat -ano | findstr ":8000.*LISTENING"
   # 停止进程（替换PID为实际进程ID）
   taskkill /PID <PID> /F
   ```

2. **使用桌面快捷方式启动**
   - 双击桌面上的 **"启动MCP服务器.lnk"** 快捷方式
   - 或者运行：`d:\quantsys\tools\mcp_bus\start_mcp_server.ps1`

3. **验证启动**
   ```powershell
   # 等待几秒钟后检查状态
   curl http://127.0.0.1:18788/api/freqtrade/status
   ```

### 方法2: 手动设置环境变量后重启

如果服务器是通过其他方式启动的（如IDE、命令行等），需要手动设置环境变量：

```powershell
# 设置环境变量
$env:AUTO_START_FREQTRADE = "true"
$env:REPO_ROOT = "d:\quantsys"
$env:MCP_BUS_HOST = "127.0.0.1"
$env:MCP_BUS_PORT = "8000"

# 然后启动服务器
cd d:\quantsys\tools\mcp_bus
python -m uvicorn server.main:app --host $env:MCP_BUS_HOST --port $env:MCP_BUS_PORT
```

### 方法3: 手动启动Freqtrade（临时方案）

如果暂时无法重启服务器，可以手动启动Freqtrade：

```powershell
# 通过API启动（无需认证）
curl -X POST http://127.0.0.1:18788/api/freqtrade/webserver/start

# 检查状态
curl http://127.0.0.1:18788/api/freqtrade/status
```

## 验证步骤

1. **检查环境变量**
   ```powershell
   python check_freqtrade_startup.py
   ```

2. **检查Freqtrade状态**
   ```powershell
   curl http://127.0.0.1:18788/api/freqtrade/status
   ```

3. **检查端口**
   ```powershell
   netstat -ano | findstr ":8080.*LISTENING"
   ```

4. **访问FreqUI**
   - 浏览器打开：`http://127.0.0.1:18788/frequi`

## 日志检查

如果启动失败，检查以下日志：

1. **服务器日志**: 查看启动时的日志输出，应该看到：
   ```
   AUTO_START_FREQTRADE environment variable: true
   Auto-start check result: True
   Auto-starting Freqtrade WebServer...
   ```

2. **Freqtrade日志**: `d:\quantsys\logs\freqtrade_webserver.log`

## 常见问题

### Q: 为什么环境变量没有传递？

A: 可能的原因：
- 服务器是通过IDE或其他方式启动的，没有使用启动脚本
- PowerShell环境变量没有正确设置
- 服务器进程启动时环境变量未继承

### Q: 如何确认服务器是通过哪个脚本启动的？

A: 检查进程的命令行参数：
```powershell
Get-WmiObject Win32_Process | Where-Object {$_.CommandLine -like "*uvicorn*"} | Select-Object CommandLine
```

### Q: 启动脚本中已经设置了环境变量，为什么还是不行？

A: 确保：
1. 使用`start_mcp_server.ps1`启动（不是直接运行uvicorn）
2. 环境变量在启动uvicorn之前设置
3. 服务器进程确实继承了环境变量

## 预防措施

1. **始终使用启动脚本**: 使用`start_mcp_server.ps1`或桌面快捷方式启动服务器
2. **检查启动日志**: 启动时查看日志确认环境变量已设置
3. **使用诊断工具**: 运行`check_freqtrade_startup.py`检查配置
