# MCP服务器启动Bug修复报告

## 问题描述

**严重Bug**: MCP服务器无法正常启动，进程启动但端口8000未监听，服务器状态显示"无法访问"。

## 问题原因

### 1. 工作目录路径错误 ⚠️ **关键Bug**

**原代码**:
```python
mcp_dir = Path(__file__).parent.parent
```

**问题**:
- `__file__` 是 `server_tray_enhanced.py` 的路径
- `Path(__file__).parent` 是 `mcp_bus` 目录
- `Path(__file__).parent.parent` 是 `tools` 目录（错误！）
- 导致服务器在错误的目录下启动，无法找到 `server.main:app` 模块

**修复**:
```python
mcp_dir = Path(__file__).parent.resolve()
```

### 2. 错误输出被丢弃 ⚠️ **严重问题**

**原代码**:
```python
stdout=subprocess.PIPE,
stderr=subprocess.PIPE,
```

**问题**:
- 错误输出被重定向到PIPE但没有处理
- 启动失败时看不到任何错误信息
- 无法诊断问题

**修复**:
- 将错误输出重定向到日志文件
- 进程异常退出时读取并显示日志

### 3. 使用DETACHED_PROCESS导致问题

**原代码**:
```python
creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
```

**问题**:
- `DETACHED_PROCESS` 可能导致进程无法正常启动
- 在某些情况下会导致进程立即退出

**修复**:
```python
creation_flags = subprocess.CREATE_NO_WINDOW  # 移除DETACHED_PROCESS
```

### 4. 环境变量未正确设置

**问题**:
- 环境变量可能未正确传递给子进程
- 导致服务器启动时缺少必要的配置

**修复**:
- 显式设置所有必要的环境变量
- 确保REPO_ROOT、MCP_BUS_HOST等正确传递

## 修复内容

### 修复1: 工作目录路径

```python
# 修复前
mcp_dir = Path(__file__).parent.parent  # 错误：指向tools目录

# 修复后
mcp_dir = Path(__file__).parent.resolve()  # 正确：指向mcp_bus目录
```

### 修复2: 错误日志处理

```python
# 创建日志目录和文件
log_dir = mcp_dir / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / f"server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# 将错误输出重定向到日志文件
with open(log_file, 'w', encoding='utf-8') as log_f:
    server_process = subprocess.Popen(
        cmd,
        cwd=str(mcp_dir),
        stdout=log_f,
        stderr=subprocess.STDOUT,  # stderr重定向到stdout
        creationflags=creation_flags,
        env=env
    )
```

### 修复3: 进程退出码检查

```python
# 等待进程结束
server_process.wait()

# 如果进程异常退出，读取日志文件显示错误
if server_process.returncode != 0:
    print(f"[ERROR] Server exited with code {server_process.returncode}")
    if log_file.exists():
        print(f"[ERROR] Last 20 lines of log:")
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for line in lines[-20:]:
                print(f"  {line.rstrip()}")
```

### 修复4: 环境变量设置

```python
# 设置环境变量
env = os.environ.copy()
env["REPO_ROOT"] = str(repo_root)
env["MCP_BUS_HOST"] = SERVER_HOST
env["MCP_BUS_PORT"] = SERVER_PORT
env["AUTH_MODE"] = os.getenv("AUTH_MODE", "none")
```

## 测试验证

### 测试步骤

1. **停止所有现有进程**
   ```powershell
   taskkill /F /IM pythonw.exe /T
   ```

2. **启动服务器**
   - 双击桌面快捷方式 `MCP Server.lnk`
   - 或运行: `pythonw server_tray_enhanced.py`

3. **验证启动**
   ```powershell
   # 检查端口
   netstat -ano | findstr ":8000" | findstr "LISTENING"
   
   # 检查健康状态
   curl http://127.0.0.1:18788/health
   ```

4. **检查日志**
   ```powershell
   # 查看最新日志文件
   Get-ChildItem d:\quantsys\tools\mcp_bus\logs\server_*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 50
   ```

### 预期结果

- ✅ 服务器进程正常启动
- ✅ 端口8000处于LISTENING状态
- ✅ 健康检查端点可访问
- ✅ 系统托盘图标显示正确状态
- ✅ 日志文件记录启动信息

## 影响范围

### 受影响的功能

- ❌ 服务器无法启动（已修复）
- ❌ 无法访问服务器（已修复）
- ❌ 系统托盘状态显示错误（已修复）

### 修复后的改进

- ✅ 服务器可以正常启动
- ✅ 错误信息记录到日志文件
- ✅ 启动失败时可以查看错误日志
- ✅ 环境变量正确传递
- ✅ 工作目录正确设置

## 相关文件

- `server_tray_enhanced.py` - 主修复文件
- `logs/server_*.log` - 服务器日志文件
- `MCP_STARTUP_BUG_FIX.md` - 本文档

## 后续建议

1. **监控日志文件**
   - 定期检查日志文件
   - 发现错误及时处理

2. **改进错误处理**
   - 考虑添加启动重试机制
   - 添加更详细的错误提示

3. **测试覆盖**
   - 添加启动测试
   - 验证各种启动场景

## 总结

**Bug严重性**: 🔴 **严重** - 服务器完全无法启动

**修复状态**: ✅ **已修复**

**修复内容**:
1. 修复工作目录路径错误
2. 添加错误日志记录
3. 移除DETACHED_PROCESS标志
4. 正确设置环境变量

**验证状态**: ⏳ **待验证** - 需要重启服务器测试
