# MCP服务器托盘程序设置指南

## 功能说明

增强版托盘程序提供以下功能：

1. **开机自启动**：服务器随Windows启动自动运行
2. **桌面快捷方式**：保留桌面快捷方式，方便手动启动
3. **系统托盘图标**：后台运行，不显示任务栏窗口，可关闭任务栏窗口不影响服务器
4. **状态颜色指示**：根据服务器状态显示不同颜色的图标，一眼分辨服务器情况

## 托盘图标颜色说明

| 颜色 | 状态 | 说明 |
|------|------|------|
| 🟢 **绿色** | 正常运行 | 服务器正常运行，所有服务正常（Freqtrade运行，OKX连接正常） |
| 🟡 **黄色** | 部分异常 | 服务器运行但部分服务异常（Freqtrade未启动或OKX连接失败） |
| 🔴 **红色** | 无法访问 | 服务器无法访问或严重错误 |
| ⚪ **灰色** | 启动中/未知 | 服务器启动中或状态未知 |

## 快速安装

### 方法1：一键安装（推荐）

以管理员身份运行PowerShell，执行：

```powershell
cd d:\quantsys\tools\mcp_bus
.\install_all.ps1
```

这将自动完成：
- ✅ 创建桌面快捷方式
- ✅ 设置开机自启动
- ✅ 检查并安装依赖

### 方法2：分步安装

#### 1. 创建桌面快捷方式

```powershell
cd d:\quantsys\tools\mcp_bus
.\create_desktop_shortcut_tray.ps1
```

#### 2. 设置开机自启动（需要管理员权限）

```powershell
# 以管理员身份运行
.\setup_autostart_tray.ps1
```

#### 3. 安装依赖（如果未安装）

```powershell
pip install pystray pillow
```

## 使用方法

### 启动服务器

**方式1：双击桌面快捷方式**
- 双击 `MCP服务器（托盘图标）.lnk`
- 服务器在后台启动，不显示窗口

**方式2：使用PowerShell脚本**
```powershell
.\start_mcp_server_tray.ps1
```

**方式3：使用批处理文件**
```cmd
start_mcp_server_tray.bat
```

### 查看服务器状态

1. **查看托盘图标颜色**：右下角系统托盘，根据颜色判断状态
2. **右键点击托盘图标**：选择"状态"查看详细信息
3. **访问Web界面**：
   - 打开仪表板：右键 → "打开仪表板"
   - 打开FreqUI：右键 → "打开FreqUI"
   - 打开监控面板：右键 → "打开监控面板"

### 停止服务器

右键点击托盘图标 → 选择"退出"

## 托盘菜单功能

- **状态**：显示当前服务器状态信息
- **打开仪表板**：在浏览器中打开主仪表板
- **打开FreqUI**：在浏览器中打开FreqUI界面
- **打开Web查看器**：在浏览器中打开ATA消息查看器
- **打开监控面板**：在浏览器中打开监控面板
- **退出**：停止服务器并退出托盘程序

## 管理开机自启动

### 查看自启动任务

```powershell
Get-ScheduledTask -TaskName "MCP Bus Server (Tray)"
```

### 删除自启动任务

```powershell
Unregister-ScheduledTask -TaskName "MCP Bus Server (Tray)" -Confirm:$false
```

### 手动运行自启动任务

```powershell
Start-ScheduledTask -TaskName "MCP Bus Server (Tray)"
```

### 禁用自启动任务

```powershell
Disable-ScheduledTask -TaskName "MCP Bus Server (Tray)"
```

### 启用自启动任务

```powershell
Enable-ScheduledTask -TaskName "MCP Bus Server (Tray)"
```

## 状态检查机制

托盘程序每10秒自动检查一次服务器状态：

1. **健康检查**：访问 `/health` 端点
2. **服务状态检查**：访问 `/api/monitoring/status` 端点
3. **状态判断**：
   - 如果健康检查失败 → 红色
   - 如果Freqtrade和OKX都正常 → 绿色
   - 如果部分服务异常 → 黄色
   - 如果无法获取状态 → 灰色

## 故障排除

### 托盘图标不显示

1. 检查依赖是否安装：
   ```powershell
   python -c "import pystray, PIL"
   ```

2. 如果未安装，执行：
   ```powershell
   pip install pystray pillow
   ```

3. 检查Python版本（需要Python 3.7+）

### 服务器无法启动

1. 检查端口是否被占用：
   ```powershell
   netstat -ano | findstr :8000
   ```

2. 检查日志文件（如果有）

3. 尝试手动启动查看错误：
   ```powershell
   python server_tray_enhanced.py
   ```

### 开机不自启动

1. 确认已以管理员身份运行安装脚本
2. 检查任务计划程序：
   ```powershell
   Get-ScheduledTask -TaskName "MCP Bus Server (Tray)"
   ```
3. 检查任务是否启用：
   ```powershell
   (Get-ScheduledTask -TaskName "MCP Bus Server (Tray)").State
   ```

### 状态颜色不正确

1. 检查服务器是否正常运行：
   ```powershell
   curl http://127.0.0.1:18788/health
   ```

2. 检查服务状态：
   ```powershell
   curl http://127.0.0.1:18788/api/monitoring/status
   ```

3. 等待10秒让状态检查更新

## 文件说明

- `server_tray_enhanced.py`：增强版托盘程序（带状态监控）
- `server_tray.py`：基础版托盘程序（无状态监控）
- `setup_autostart_tray.ps1`：设置开机自启动脚本
- `create_desktop_shortcut_tray.ps1`：创建桌面快捷方式脚本
- `start_mcp_server_tray.ps1`：启动托盘版本服务器
- `start_mcp_server_tray.bat`：启动托盘版本服务器（批处理）
- `install_all.ps1`：一键安装脚本

## 注意事项

1. **管理员权限**：设置开机自启动需要管理员权限
2. **依赖安装**：首次使用需要安装 `pystray` 和 `pillow`
3. **端口占用**：确保8000端口未被占用
4. **防火墙**：如果使用防火墙，确保允许Python访问网络
5. **状态更新**：状态检查每10秒更新一次，颜色变化可能有延迟

## 技术细节

### 状态检查逻辑

```python
健康检查失败 → 红色
健康检查通过 + Freqtrade正常 + OKX正常 → 绿色
健康检查通过 + (Freqtrade异常 或 OKX异常) → 黄色
无法连接服务器 → 红色
启动中/未知状态 → 灰色
```

### 图标更新机制

- 初始状态：灰色（启动中）
- 每10秒检查一次状态
- 状态变化时自动更新图标颜色
- 图标更新不阻塞服务器运行
