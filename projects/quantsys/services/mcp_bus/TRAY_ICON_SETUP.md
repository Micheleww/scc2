# MCP服务器系统托盘图标设置指南

**日期**: 2026-01-21  
**状态**: ✅ 已完成

## 功能说明

MCP服务器现在支持后台运行，在系统托盘（右下角）显示图标，不显示任务栏窗口。

## 创建的文件

1. **`server_tray.py`** - 带系统托盘图标的服务器启动脚本
2. **`start_mcp_server_tray.ps1`** - PowerShell启动脚本（隐藏窗口）
3. **`start_mcp_server_tray.bat`** - BAT启动脚本（隐藏窗口）
4. **`create_tray_shortcuts.py`** - 创建桌面快捷方式的脚本

## 使用方法

### 方法1: 使用快捷方式（推荐）

运行以下命令创建桌面快捷方式：

```powershell
cd d:\quantsys\tools\mcp_bus
python create_tray_shortcuts.py
```

这会在桌面创建两个快捷方式：
- **MCP服务器（后台运行）.lnk** - 使用PowerShell启动
- **MCP服务器（托盘图标）.lnk** - 使用BAT文件启动

双击任一快捷方式即可启动服务器。

### 方法2: 直接运行脚本

#### PowerShell方式：
```powershell
cd d:\quantsys\tools\mcp_bus
.\start_mcp_server_tray.ps1
```

#### BAT方式：
```cmd
cd d:\quantsys\tools\mcp_bus
start_mcp_server_tray.bat
```

#### Python方式：
```cmd
cd d:\quantsys\tools\mcp_bus
python server_tray.py
```

## 系统托盘图标功能

启动后，在系统托盘（右下角）会显示一个蓝色圆形图标，中间有白色"Q"字母。

### 右键菜单选项：

1. **打开仪表板** - 打开主控制面板 (http://127.0.0.1:18788/)
2. **打开FreqUI** - 打开Freqtrade UI (http://127.0.0.1:18788/frequi)
3. **退出** - 停止服务器并退出

## 依赖安装

首次运行需要安装以下Python库：

```bash
pip install pystray pillow
```

如果未安装，服务器仍可运行，但不会显示系统托盘图标。

## 特性

✅ **后台运行** - 服务器在后台运行，不显示控制台窗口  
✅ **系统托盘图标** - 在系统托盘显示图标，方便管理  
✅ **隐藏任务栏** - 不在任务栏显示窗口  
✅ **右键菜单** - 快速访问仪表板和FreqUI  
✅ **优雅退出** - 通过托盘图标菜单退出服务器  

## 注意事项

1. **首次运行** - 可能需要安装`pystray`和`pillow`库
2. **系统托盘** - 图标显示在系统托盘（右下角），可能需要点击"显示隐藏的图标"才能看到
3. **服务器状态** - 服务器启动后会在后台运行，通过托盘图标管理
4. **端口占用** - 如果端口8000已被占用，服务器可能无法启动

## 故障排除

### 问题1: 看不到系统托盘图标

**解决方案**:
1. 检查是否安装了`pystray`和`pillow`：`pip install pystray pillow`
2. 点击系统托盘区域的"显示隐藏的图标"箭头
3. 检查服务器是否正常启动（查看日志）

### 问题2: 服务器无法启动

**解决方案**:
1. 检查端口8000是否被占用：`netstat -ano | findstr ":8000"`
2. 检查Python环境是否正确
3. 查看错误日志

### 问题3: 快捷方式无法运行

**解决方案**:
1. 检查快捷方式指向的路径是否正确
2. 尝试直接运行脚本文件
3. 检查文件权限

## 相关文件

- `tools/mcp_bus/server_tray.py` - 系统托盘服务器脚本
- `tools/mcp_bus/start_mcp_server_tray.ps1` - PowerShell启动脚本
- `tools/mcp_bus/start_mcp_server_tray.bat` - BAT启动脚本
- `tools/mcp_bus/create_tray_shortcuts.py` - 快捷方式创建脚本

## 总结

✅ **MCP服务器现在可以在后台运行，通过系统托盘图标管理！**

- 不显示任务栏窗口
- 系统托盘图标方便管理
- 右键菜单快速访问功能
- 优雅的启动和退出方式
