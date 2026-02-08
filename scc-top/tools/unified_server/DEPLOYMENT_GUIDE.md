# 统一服务器部署指南

## 部署方式

### 方式1: 基本运行（开发/测试）

```bash
# 直接运行
python main.py

# 或使用启动脚本
python start_unified_server.py
```

### 方式2: 后台服务运行（推荐）

使用PowerShell后台作业运行，不依赖用户登录：

```powershell
# 运行后台服务
.\run_as_background_service.ps1
```

**特点**：
- ✅ 后台运行，无窗口
- ✅ 自动日志记录
- ✅ 进程ID保存到文件
- ✅ 可通过进程ID管理

**管理命令**：
```powershell
# 查看日志
Get-Content logs\server_*.log -Tail 50 -Wait

# 停止服务（需要进程ID）
Stop-Process -Id <PID>

# 查看进程
Get-Process -Id <PID>
```

### 方式3: 开机自启动（推荐生产环境）

使用Windows任务计划程序创建开机自启动任务：

```powershell
# 以管理员身份运行
powershell -ExecutionPolicy Bypass -File create_startup_task.ps1
```

**特点**：
- ✅ 开机自动启动
- ✅ 系统账户运行（不依赖用户登录）
- ✅ 自动重启（失败时）
- ✅ 独立运行

**管理命令**：
```powershell
# 查看任务
Get-ScheduledTask -TaskName QuantSysUnifiedServer

# 手动运行任务
Start-ScheduledTask -TaskName QuantSysUnifiedServer

# 停止任务
Stop-ScheduledTask -TaskName QuantSysUnifiedServer

# 删除任务
Unregister-ScheduledTask -TaskName QuantSysUnifiedServer -Confirm:$false
```

### 方式4: Windows服务（高级）

使用NSSM将服务器安装为Windows服务：

**前置条件**：
1. 下载NSSM: https://nssm.cc/download
2. 将`nssm.exe`放置到`tools/unified_server/`目录

**安装服务**：
```bash
# 以管理员身份运行
python install_windows_service.py
```

**管理服务**：
```bash
# 启动服务
net start QuantSysUnifiedServer

# 停止服务
net stop QuantSysUnifiedServer

# 卸载服务
python install_windows_service.py uninstall
```

**特点**：
- ✅ 系统服务，最高权限
- ✅ 自动启动（开机）
- ✅ 自动重启（失败时）
- ✅ 服务管理界面可见

## 配置说明

### 环境变量

```bash
# 服务器配置
export UNIFIED_SERVER_HOST=127.0.0.1
export UNIFIED_SERVER_PORT=18788
export LOG_LEVEL=info
export DEBUG=false

# 服务配置
export MCP_BUS_ENABLED=true
export A2A_HUB_ENABLED=true
export EXCHANGE_SERVER_ENABLED=true
export A2A_HUB_SECRET_KEY=your_secret_key
```

### 配置文件

创建`.env`文件（可选）：

```env
UNIFIED_SERVER_HOST=127.0.0.1
UNIFIED_SERVER_PORT=18788
LOG_LEVEL=info
DEBUG=false
MCP_BUS_ENABLED=true
A2A_HUB_ENABLED=true
EXCHANGE_SERVER_ENABLED=true
```

## 验证部署

### 1. 检查服务状态

```bash
# 基本健康检查
curl http://localhost:18788/health

# 就绪检查
curl http://localhost:18788/health/ready

# 存活检查
curl http://localhost:18788/health/live
```

### 2. 运行测试

```bash
# 全面测试
python test_comprehensive.py

# 简单测试
python test_unified_server.py
```

### 3. 查看日志

```bash
# 查看服务日志
Get-Content logs\server_*.log -Tail 50

# 实时查看日志
Get-Content logs\server_*.log -Tail 50 -Wait
```

## 故障排除

### 问题1: 端口被占用

**错误**: `Port 18788 is already in use`

**解决**:
```bash
# 查找占用端口的进程
netstat -ano | findstr :18788

# 停止进程
taskkill /PID <PID> /F

# 或更改端口
export UNIFIED_SERVER_PORT=8001
```

### 问题2: 服务无法启动

**检查**:
1. Python环境是否正确
2. 依赖是否安装: `pip install -r requirements.txt`
3. 配置文件是否正确
4. 日志文件中的错误信息

### 问题3: 开机不自启动

**检查**:
1. 任务计划程序中的任务是否存在
2. 任务是否启用
3. 任务触发器是否正确
4. 任务权限是否正确

### 问题4: 后台服务无法访问

**检查**:
1. 服务是否正在运行: `Get-Process -Name python`
2. 端口是否监听: `netstat -ano | findstr :18788`
3. 防火墙设置
4. 日志文件中的错误信息

## 生产环境建议

1. **使用开机自启动** - 确保服务器始终运行
2. **配置日志轮转** - 避免日志文件过大
3. **监控健康检查** - 定期检查`/health/ready`端点
4. **设置告警** - 服务异常时发送通知
5. **定期备份** - 备份配置和状态文件
6. **性能监控** - 监控CPU、内存、网络使用情况

## 安全建议

1. **限制访问** - 仅允许本地访问（127.0.0.1）
2. **使用HTTPS** - 生产环境使用HTTPS（需要反向代理）
3. **认证授权** - 启用认证中间件
4. **日志安全** - 不在日志中记录敏感信息
5. **定期更新** - 保持依赖包最新
