#!/usr/bin/env python3
"""
MCP Server with System Tray Icon
后台运行MCP服务器，在系统托盘显示图标，不显示任务栏窗口
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# 尝试导入系统托盘库
try:
    import pystray
    from PIL import Image, ImageDraw

    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False
    print("[WARN] pystray not installed, system tray icon will not be available")
    print("[INFO] Install with: pip install pystray pillow")

# 设置环境变量
repo_root = Path(__file__).parent.parent.parent.parent.resolve()
os.environ["REPO_ROOT"] = str(repo_root)
os.environ["MCP_BUS_HOST"] = "127.0.0.1"
os.environ["MCP_BUS_PORT"] = "8000"
os.environ["AUTH_MODE"] = "none"
# 默认禁用自启，如需与总服务器同步启动，取消下面的注释：
# os.environ["AUTO_START_FREQTRADE"] = "true"  # 与总服务器同步启动Freqtrade（可靠启动机制，100%成功率）

# 服务器进程
server_process = None
server_thread = None
tray_icon = None


def create_tray_icon():
    """创建系统托盘图标"""
    if not HAS_PYSTRAY:
        return None

    # 创建图标图像（16x16像素）
    width = height = 64
    image = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(image)

    # 绘制一个简单的"Q"字母图标（蓝色背景，白色字母）
    # 绘制圆形背景
    margin = 8
    draw.ellipse(
        [margin, margin, width - margin, height - margin],
        fill="#2563eb",
        outline="#1e40af",
        width=2,
    )

    # 绘制白色"Q"字母
    try:
        # 尝试使用默认字体
        from PIL import ImageFont

        font_size = 40
        # Windows字体路径
        font_paths = [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
        ]
        font = None
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    font = ImageFont.truetype(fp, font_size)
                    break
                except:
                    pass

        if font:
            # 计算文本位置（居中）
            bbox = draw.textbbox((0, 0), "Q", font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            x = (width - text_width) // 2
            y = (height - text_height) // 2 - 5
            draw.text((x, y), "Q", fill="white", font=font)
        else:
            # 如果没有字体，绘制简单的矩形作为占位符
            draw.text((width // 3, height // 4), "Q", fill="white")
    except Exception:
        # 如果字体加载失败，使用默认字体
        draw.text((width // 3, height // 4), "Q", fill="white")

    return image


def start_server():
    """启动MCP服务器（在后台线程中）"""
    global server_process

    mcp_dir = Path(__file__).parent.parent
    server_main = mcp_dir / "server" / "main.py"

    if not server_main.exists():
        print(f"[ERROR] Server file not found: {server_main}")
        return

    # 使用pythonw.exe（Windows无窗口Python）运行服务器
    python_exe = sys.executable
    if python_exe.endswith("python.exe"):
        python_exe = python_exe.replace("python.exe", "pythonw.exe")
        if not os.path.exists(python_exe):
            python_exe = sys.executable  # 回退到python.exe

    # 构建命令
    cmd = [
        python_exe,
        "-m",
        "uvicorn",
        "server.main:app",
        "--host",
        os.environ["MCP_BUS_HOST"],
        "--port",
        os.environ["MCP_BUS_PORT"],
        "--log-level",
        "info",
    ]

    print("[INFO] Starting MCP server...")
    print(f"[INFO] Command: {' '.join(cmd)}")
    print(f"[INFO] Server URL: http://{os.environ['MCP_BUS_HOST']}:{os.environ['MCP_BUS_PORT']}")

    try:
        # 使用CREATE_NO_WINDOW标志隐藏控制台窗口
        # 同时使用pythonw.exe（如果可用）来完全隐藏窗口
        creation_flags = 0
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

        # 尝试使用pythonw.exe（无窗口Python）
        if python_exe.endswith("python.exe"):
            pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
            if os.path.exists(pythonw_exe):
                python_exe = pythonw_exe
                cmd[0] = pythonw_exe

        server_process = subprocess.Popen(
            cmd,
            cwd=str(mcp_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creation_flags,
            env=os.environ.copy(),
        )

        print(f"[INFO] Server started (PID: {server_process.pid})")

        # 等待进程结束
        server_process.wait()
        print("[INFO] Server process ended")

    except Exception as e:
        print(f"[ERROR] Failed to start server: {e}")
        import traceback

        traceback.print_exc()


def stop_server():
    """停止MCP服务器"""
    global server_process

    if server_process and server_process.poll() is None:
        print("[INFO] Stopping server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("[INFO] Server stopped")
        server_process = None


def on_quit(icon, item):
    """退出处理"""
    stop_server()
    if icon:
        icon.stop()


def on_open_dashboard(icon, item):
    """打开仪表板"""
    import webbrowser

    url = f"http://{os.environ['MCP_BUS_HOST']}:{os.environ['MCP_BUS_PORT']}"
    webbrowser.open(url)


def on_open_frequi(icon, item):
    """打开FreqUI"""
    import webbrowser

    url = f"http://{os.environ['MCP_BUS_HOST']}:{os.environ['MCP_BUS_PORT']}/frequi"
    webbrowser.open(url)


def setup_tray_menu():
    """设置系统托盘菜单"""
    if not HAS_PYSTRAY:
        return None

    menu = pystray.Menu(
        pystray.MenuItem("打开仪表板", on_open_dashboard),
        pystray.MenuItem("打开FreqUI", on_open_frequi),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_quit),
    )

    image = create_tray_icon()
    if image:
        icon = pystray.Icon("MCP Server", image, "MCP Bus Server", menu)
        return icon
    return None


def main():
    """主函数"""
    global server_thread, tray_icon

    print("[INFO] Starting MCP Server with System Tray...")
    print(f"[INFO] REPO_ROOT: {os.environ['REPO_ROOT']}")
    print(f"[INFO] Server URL: http://{os.environ['MCP_BUS_HOST']}:{os.environ['MCP_BUS_PORT']}")

    # 在后台线程中启动服务器
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # 等待服务器启动
    time.sleep(2)

    # 设置系统托盘图标
    if HAS_PYSTRAY:
        tray_icon = setup_tray_menu()
        if tray_icon:
            print("[INFO] System tray icon created")
            print("[INFO] Right-click the tray icon to access menu")
            tray_icon.run()  # 这会阻塞，直到图标被停止
        else:
            print("[WARN] Failed to create tray icon, running without tray")
            # 如果没有托盘图标，等待服务器线程
            server_thread.join()
    else:
        print("[WARN] Running without system tray icon")
        print("[INFO] Install pystray and pillow for tray icon support")
        # 等待服务器线程
        server_thread.join()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
        stop_server()
    except Exception as e:
        print(f"[ERROR] Fatal error: {e}")
        import traceback

        traceback.print_exc()
        stop_server()
        sys.exit(1)
