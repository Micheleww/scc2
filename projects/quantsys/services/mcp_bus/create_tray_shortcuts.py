#!/usr/bin/env python3
"""
创建带系统托盘图标的MCP服务器快捷方式
"""

import os
import sys
from pathlib import Path

import winshell
from win32com.client import Dispatch


def create_tray_shortcuts():
    """创建系统托盘版本的快捷方式"""
    try:
        # 获取项目根目录
        root = Path(__file__).parent.parent.parent

        # 获取桌面路径
        desktop = winshell.desktop()

        # 快捷方式1: MCP服务器（系统托盘版本）
        shortcut1_name = "MCP服务器（后台运行）.lnk"
        shortcut1_path = os.path.join(desktop, shortcut1_name)

        # 使用PowerShell脚本启动（隐藏窗口）
        target1 = "powershell.exe"
        arguments1 = '-WindowStyle Hidden -ExecutionPolicy Bypass -File "d:\\quantsys\\tools\\mcp_bus\\start_mcp_server_tray.ps1"'
        working_dir1 = str(root / "tools" / "mcp_bus")
        description1 = "启动MCP服务器（后台运行，系统托盘图标）"

        shell = Dispatch("WScript.Shell")
        shortcut1 = shell.CreateShortCut(shortcut1_path)
        shortcut1.Targetpath = target1
        shortcut1.Arguments = arguments1
        shortcut1.WorkingDirectory = working_dir1
        shortcut1.Description = description1
        # 使用Python图标
        python_exe = sys.executable
        shortcut1.IconLocation = f"{python_exe},0"
        shortcut1.save()

        print(f"[OK] Shortcut 1 created: {shortcut1_path}")
        print(f"  Name: {shortcut1_name}")
        print(f"  Description: {description1}")
        print()

        # 快捷方式2: 使用BAT文件启动（备用方案）
        shortcut2_name = "MCP服务器（托盘图标）.lnk"
        shortcut2_path = os.path.join(desktop, shortcut2_name)

        target2 = "d:\\quantsys\\tools\\mcp_bus\\start_mcp_server_tray.bat"
        arguments2 = ""
        working_dir2 = str(root / "tools" / "mcp_bus")
        description2 = "启动MCP服务器（系统托盘图标，隐藏窗口）"

        shortcut2 = shell.CreateShortCut(shortcut2_path)
        shortcut2.Targetpath = target2
        shortcut2.Arguments = arguments2
        shortcut2.WorkingDirectory = working_dir2
        shortcut2.Description = description2
        shortcut2.IconLocation = f"{python_exe},0"
        # 设置运行方式为最小化
        shortcut2.WindowStyle = 7  # 7 = Minimized
        shortcut2.save()

        print(f"[OK] Shortcut 2 created: {shortcut2_path}")
        print(f"  Name: {shortcut2_name}")
        print(f"  Description: {description2}")
        print()

        print("=" * 60)
        print("Shortcuts created successfully!")
        print("=" * 60)
        print()
        print("Usage:")
        print("1. Double-click shortcut to start MCP server")
        print("2. Server runs in background, no taskbar window")
        print("3. Look for server icon in system tray (bottom-right)")
        print("4. Right-click tray icon to:")
        print("   - Open Dashboard")
        print("   - Open FreqUI")
        print("   - Exit server")
        print()
        print("Note: First run may need to install pystray and pillow")
        print("Install: pip install pystray pillow")

        return True

    except Exception as e:
        print(f"[ERROR] Failed to create shortcuts: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("Create MCP Server System Tray Shortcuts")
    print("=" * 60)
    print()

    success = create_tray_shortcuts()

    if success:
        print()
        print("[OK] All shortcuts created successfully!")
    else:
        print()
        print("[ERROR] Failed to create shortcuts, please check error messages")
        sys.exit(1)


if __name__ == "__main__":
    main()
