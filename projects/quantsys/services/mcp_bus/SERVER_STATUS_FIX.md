# 服务器状态"无法访问"问题修复指南

## 问题描述

服务器状态显示"无法访问"，但快捷方式可以启动进程。

## 问题原因

1. **服务器进程启动但未成功监听端口**
   - `pythonw.exe` 进程在运行
   - 但端口8000没有LISTENING状态
   - 服务器可能启动失败或遇到错误

2. **单实例检查**
   - 如果已有实例在运行，新实例会被阻止
   - 使用 Windows 命名互斥体检查

3. **后台运行无错误提示**
   - 使用 `pythonw.exe` 后台运行
   - 错误不会显示在控制台
   - 需要通过系统托盘图标查看状态

## 诊断步骤

### 1. 运行诊断脚本

```powershell
cd d:\quantsys\tools\mcp_bus
.\diagnose_server_status.ps1
```

### 2. 检查项目

- ✅ 端口8000是否被监听
- ✅ Python进程是否在运行
- ✅ 服务器脚本是否存在
- ✅ 工作目录是否存在

## 解决方案

### 方案1: 使用修复脚本（推荐）

```powershell
cd d:\quantsys\tools\mcp_bus
.\fix_server_status.ps1
```

这个脚本会：
1. 停止所有 `pythonw.exe` 进程
2. 检查端口8000状态
3. 验证桌面快捷方式
4. 提供启动选项

### 方案2: 手动修复

#### 步骤1: 停止所有服务器进程

```powershell
# 停止所有pythonw.exe进程
taskkill /F /IM pythonw.exe /T

# 或者使用PowerShell
Get-Process -Name pythonw | Stop-Process -Force
```

#### 步骤2: 检查端口状态

```powershell
netstat -ano | findstr ":8000"
```

如果端口仍被占用，找到占用端口的进程并停止它。

#### 步骤3: 重新启动服务器

**方法A: 使用桌面快捷方式（推荐）**
- 双击桌面上的 `MCP Server.lnk`
- 等待10-30秒
- 检查系统托盘图标

**方法B: 手动启动（查看错误）**
```powershell
cd d:\quantsys\tools\mcp_bus
python server_tray_enhanced.py
```
这会显示控制台输出，可以看到错误信息。

**方法C: 后台启动**
```powershell
cd d:\quantsys\tools\mcp_bus
pythonw server_tray_enhanced.py
```

### 方案3: 检查系统托盘图标

1. 查看右下角系统托盘
2. 找到MCP服务器图标
3. 右键点击查看状态
4. 查看是否有错误信息

## 验证服务器是否启动

### 方法1: 检查端口

```powershell
netstat -ano | findstr ":8000" | findstr "LISTENING"
```

如果看到 `LISTENING` 状态，说明服务器正在运行。

### 方法2: 访问健康检查

```powershell
curl http://127.0.0.1:18788/health
```

或者在浏览器中访问：http://127.0.0.1:18788/health

### 方法3: 检查系统托盘图标

- 🟢 绿色：正常运行
- 🟡 黄色：部分异常
- 🔴 红色：无法访问
- ⚪ 灰色：启动中

## 常见问题

### Q1: 为什么服务器启动后无法访问？

**可能原因：**
1. 服务器启动失败（检查系统托盘图标）
2. 端口被其他程序占用
3. 防火墙阻止了连接
4. 服务器还在启动中（等待更长时间）

**解决方法：**
1. 运行诊断脚本检查问题
2. 停止所有相关进程后重新启动
3. 检查系统托盘图标查看详细状态

### Q2: 如何查看服务器启动错误？

**方法1: 使用python而不是pythonw**
```powershell
cd d:\quantsys\tools\mcp_bus
python server_tray_enhanced.py
```
这会显示控制台输出。

**方法2: 检查日志文件**
```powershell
# 检查是否有日志文件
Get-ChildItem d:\quantsys\tools\mcp_bus\logs -ErrorAction SilentlyContinue
```

**方法3: 检查系统托盘图标**
- 右键点击托盘图标
- 选择"状态"查看详细信息

### Q3: 服务器一直显示"无法访问"怎么办？

1. **停止所有进程并重新启动**
   ```powershell
   taskkill /F /IM pythonw.exe /T
   # 等待几秒
   # 然后双击桌面快捷方式
   ```

2. **检查是否有其他实例在运行**
   - 服务器使用单实例检查
   - 如果已有实例，新实例会被阻止
   - 停止所有实例后重新启动

3. **检查端口是否被占用**
   ```powershell
   netstat -ano | findstr ":8000"
   ```

4. **手动启动查看错误**
   ```powershell
   cd d:\quantsys\tools\mcp_bus
   python server_tray_enhanced.py
   ```

## 预防措施

1. **使用桌面快捷方式启动**
   - 避免手动启动多个实例
   - 快捷方式会自动检查单实例

2. **检查系统托盘图标**
   - 定期查看图标颜色
   - 右键查看详细状态

3. **正确停止服务器**
   - 右键点击托盘图标
   - 选择"退出"
   - 不要直接关闭进程

## 相关文件

- `diagnose_server_status.ps1` - 诊断脚本
- `fix_server_status.ps1` - 修复脚本
- `server_tray_enhanced.py` - 服务器托盘程序
- `MCP Server.lnk` - 桌面快捷方式

## 快速修复命令

```powershell
# 停止所有服务器进程
taskkill /F /IM pythonw.exe /T

# 等待几秒
Start-Sleep -Seconds 3

# 重新启动（使用桌面快捷方式）
# 或手动启动
cd d:\quantsys\tools\mcp_bus
pythonw server_tray_enhanced.py
```

## 总结

如果服务器状态显示"无法访问"：

1. ✅ 运行 `fix_server_status.ps1` 修复脚本
2. ✅ 停止所有相关进程
3. ✅ 重新启动服务器
4. ✅ 等待10-30秒让服务器完全启动
5. ✅ 检查系统托盘图标确认状态

如果问题仍然存在，使用 `diagnose_server_status.ps1` 进行详细诊断。
