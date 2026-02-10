#!/usr/bin/env python3
"""
MCP Server with Enhanced System Tray Icon
增强版系统托盘：根据服务器状态显示不同颜色的图标，一眼分辨服务器情况
- 绿色：服务器正常运行，所有服务正常
- 黄色：服务器运行但部分服务异常（Freqtrade未启动或OKX连接失败）
- 红色：服务器无法访问或严重错误
- 灰色：服务器启动中或状态未知
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# 尝试导入psutil（用于进程检查）
try:
    import psutil

    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# Windows命名互斥体（最成熟和通用的单实例检查方法）
HAS_WIN32 = False
if os.name == "nt":  # Windows平台
    try:
        import win32api
        import win32con
        import win32event

        HAS_WIN32 = True
    except ImportError:
        HAS_WIN32 = False

# 尝试导入系统托盘库
try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont

    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False
    print("[WARN] pystray not installed, system tray icon will not be available")
    print("[INFO] Install with: pip install pystray pillow")

# 设置环境变量
repo_root = Path(__file__).parent.parent.parent.resolve()
os.environ["REPO_ROOT"] = str(repo_root)
os.environ["MCP_BUS_HOST"] = os.getenv("MCP_BUS_HOST", "127.0.0.1")
os.environ["MCP_BUS_PORT"] = os.getenv("MCP_BUS_PORT", "8000")
os.environ["AUTH_MODE"] = os.getenv("AUTH_MODE", "none")

# 服务器配置
SERVER_HOST = os.environ["MCP_BUS_HOST"]
SERVER_PORT = os.environ["MCP_BUS_PORT"]
SERVER_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"
HEALTH_URL = f"{SERVER_URL}/health"
STATUS_URL = f"{SERVER_URL}/api/monitoring/status"

# 服务器进程和状态
server_process = None
server_thread = None
tray_icon = None
status_check_thread = None
current_status = "unknown"  # unknown, healthy, warning, error
status_lock = threading.Lock()

# 单实例互斥体（Windows命名互斥体 - 最成熟和通用的方法）
instance_mutex = None
MUTEX_NAME = "Global\\MCP_Bus_Server_Tray_Instance"  # Global命名空间确保跨用户会话唯一
ERROR_ALREADY_EXISTS = 183  # Windows错误码：对象已存在


class SingleInstance:
    """
    单实例检查类（使用Windows命名互斥体）
    这是Windows平台最成熟和通用的单实例检查方法

    原理：
    1. 使用Windows内核对象 - 命名互斥体（Named Mutex）
    2. 互斥体是系统级对象，跨进程可见
    3. 如果互斥体已存在，说明另一个实例正在运行
    4. 程序退出时，系统自动清理互斥体

    优点：
    - 可靠性高：内核级对象，不依赖端口或进程检查
    - 性能好：系统级检查，速度快
    - 自动清理：进程退出时系统自动释放
    - 跨会话：使用Global命名空间可跨用户会话
    """

    def __init__(self, mutex_name: str = MUTEX_NAME):
        self.mutex_name = mutex_name
        self.mutex_handle = None
        self.already_running = False

        if not HAS_WIN32:
            # 非Windows平台，使用备用方法
            self._check_fallback()
            return

        try:
            # 尝试创建命名互斥体（bInitialOwner=True表示创建时即拥有所有权）
            self.mutex_handle = win32event.CreateMutex(None, True, self.mutex_name)
            last_error = win32api.GetLastError()

            if last_error == ERROR_ALREADY_EXISTS:
                # 互斥体已存在，说明另一个实例正在运行
                self.already_running = True
                # 关闭我们刚创建的句柄（我们不是所有者）
                win32api.CloseHandle(self.mutex_handle)
                self.mutex_handle = None
            else:
                # 成功创建互斥体，我们是第一个实例
                self.already_running = False

        except Exception as e:
            # 创建互斥体失败，使用备用方法
            print(f"[WARN] Failed to create mutex: {e}, using fallback method")
            self._check_fallback()

    def _check_fallback(self):
        """备用检查方法（当互斥体不可用时）"""
        # 方法1: 检查端口
        if is_port_in_use(SERVER_HOST, SERVER_PORT):
            try:
                req = urllib.request.Request(HEALTH_URL, method="GET")
                req.add_header("User-Agent", "MCP-Server-Instance-Checker/1.0")
                with urllib.request.urlopen(req, timeout=2) as response:
                    if response.status == 200:
                        health_data = json.loads(response.read().decode())
                        if health_data.get("ok", False):
                            self.already_running = True
                            return
            except:
                pass

        # 方法2: 检查进程（如果psutil可用）
        if HAS_PSUTIL:
            try:
                current_pid = os.getpid()
                script_name = os.path.basename(__file__)

                for proc in psutil.process_iter(["pid", "name", "cmdline"]):
                    try:
                        if proc.info["pid"] == current_pid:
                            continue

                        proc_name = proc.info.get("name", "").lower()
                        if "python" not in proc_name and "pythonw" not in proc_name:
                            continue

                        cmdline = proc.info.get("cmdline", [])
                        if not cmdline:
                            continue

                        cmdline_str = " ".join(cmdline).lower()
                        if (
                            script_name.lower() in cmdline_str
                            or "server_tray_enhanced" in cmdline_str
                        ):
                            if "uvicorn" in cmdline_str and "server.main:app" in cmdline_str:
                                self.already_running = True
                                return
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        continue
            except:
                pass

        self.already_running = False

    def release(self):
        """释放互斥体（程序退出时调用）"""
        if self.mutex_handle and HAS_WIN32:
            try:
                win32event.ReleaseMutex(self.mutex_handle)
                win32api.CloseHandle(self.mutex_handle)
            except:
                pass
            self.mutex_handle = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()


def is_port_in_use(host, port):
    """检查端口是否被占用（备用方法）"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, int(port)))
            return result == 0
    except Exception:
        return False


def create_tray_icon(color="gray"):
    """
    创建系统托盘图标（根据状态显示不同颜色）

    Args:
        color: 图标颜色
            - "green": 绿色（正常运行）
            - "yellow": 黄色（警告）
            - "red": 红色（错误）
            - "gray": 灰色（未知/启动中）
    """
    if not HAS_PYSTRAY:
        return None

    # 创建图标图像（64x64像素，高分辨率）
    width = height = 64

    # 根据颜色选择背景色和边框色
    color_map = {
        "green": {"bg": "#10b981", "border": "#059669", "text": "white"},  # 绿色：正常运行
        "yellow": {"bg": "#f59e0b", "border": "#d97706", "text": "white"},  # 黄色：警告
        "red": {"bg": "#ef4444", "border": "#dc2626", "text": "white"},  # 红色：错误
        "gray": {"bg": "#6b7280", "border": "#4b5563", "text": "white"},  # 灰色：未知/启动中
    }

    colors = color_map.get(color, color_map["gray"])

    # 创建图像
    image = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(image)

    # 绘制圆形背景
    margin = 6
    draw.ellipse(
        [margin, margin, width - margin, height - margin],
        fill=colors["bg"],
        outline=colors["border"],
        width=3,
    )

    # 绘制白色"Q"字母（QuantSys）
    try:
        # 尝试使用Windows字体
        font_size = 42
        font_paths = [
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\calibri.ttf",
            r"C:\Windows\Fonts\segoeui.ttf",
            r"C:\Windows\Fonts\msyh.ttc",  # 微软雅黑
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
            y = (height - text_height) // 2 - 6
            draw.text((x, y), "Q", fill=colors["text"], font=font)
        else:
            # 如果没有字体，使用默认字体
            draw.text((width // 3, height // 4), "Q", fill=colors["text"])
    except Exception:
        # 如果字体加载失败，使用默认字体
        draw.text((width // 3, height // 4), "Q", fill=colors["text"])

    return image


def check_server_status():
    """检查服务器状态"""
    global current_status

    try:
        # 检查健康状态
        try:
            req = urllib.request.Request(HEALTH_URL, method="GET")
            req.add_header("User-Agent", "MCP-Tray-Status-Checker/1.0")
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.status == 200:
                    health_data = json.loads(response.read().decode())
                    if not health_data.get("ok", False):
                        with status_lock:
                            current_status = "error"
                        return "error"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            # 服务器无法访问
            with status_lock:
                current_status = "error"
            return "error"

        # 检查详细状态（Freqtrade和OKX）
        freqtrade_ok = False
        okx_ok = False

        # 检查Freqtrade状态
        try:
            freq_req = urllib.request.Request(f"{SERVER_URL}/api/freqtrade/status", method="GET")
            freq_req.add_header("User-Agent", "MCP-Tray-Status-Checker/1.0")
            with urllib.request.urlopen(freq_req, timeout=3) as freq_response:
                if freq_response.status == 200:
                    freq_data = json.loads(freq_response.read().decode())
                    freqtrade_ok = freq_data.get("webserver", {}).get("running", False)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError):
            # Freqtrade检查失败，视为未运行
            freqtrade_ok = False

        # 检查OKX状态
        try:
            okx_req = urllib.request.Request(f"{SERVER_URL}/api/exchange/okx/status", method="GET")
            okx_req.add_header("User-Agent", "MCP-Tray-Status-Checker/1.0")
            with urllib.request.urlopen(okx_req, timeout=3) as okx_response:
                if okx_response.status == 200:
                    okx_data = json.loads(okx_response.read().decode())
                    okx_conn = okx_data.get("connection", {})
                    okx_ok = okx_conn.get("state") == "connected"
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError):
            # OKX检查失败，视为未连接
            okx_ok = False

        # 根据状态确定颜色
        # 注意：如果Freqtrade未启用自动启动，okx_ok为False是正常的，不应该显示警告
        # 这里我们主要关注Freqtrade的状态（如果启用了自动启动）
        if freqtrade_ok and okx_ok:
            # 所有服务正常：绿色
            with status_lock:
                current_status = "healthy"
            return "healthy"
        elif freqtrade_ok:
            # Freqtrade正常，OKX可能未配置或未连接（这是正常的）：绿色
            # 因为OKX不是必需服务，只有Freqtrade是核心服务
            with status_lock:
                current_status = "healthy"
            return "healthy"
        elif okx_ok:
            # 只有OKX正常，Freqtrade未运行：黄色警告
            with status_lock:
                current_status = "warning"
            return "warning"
        else:
            # 服务都未运行：如果健康检查通过，说明服务器运行正常，只是服务未启动
            # 这可能是因为AUTO_START_FREQTRADE=false，所以视为正常（绿色）
            # 但如果健康检查失败，已经在上面返回error了
            with status_lock:
                current_status = "healthy"  # 服务器运行正常，服务未启动是配置问题，不是错误
            return "healthy"

    except Exception:
        # 检查失败，保持当前状态或设为未知
        return current_status


def status_check_loop():
    """状态检查循环（后台线程）"""
    global tray_icon

    # 等待服务器启动（初始延迟）
    time.sleep(5)

    while True:
        try:
            status = check_server_status()

            # 更新托盘图标颜色
            if HAS_PYSTRAY and tray_icon:
                icon_image = create_tray_icon(status)
                if icon_image:
                    tray_icon.icon = icon_image
                    # 更新提示文本
                    status_text_map = {
                        "healthy": "服务器正常运行 ✓",
                        "warning": "服务器运行中，部分服务异常 ⚠",
                        "error": "服务器无法访问 ✗",
                        "unknown": "服务器状态未知",
                    }
                    tray_icon.title = (
                        f"MCP Bus Server\n{status_text_map.get(status, '状态未知')}\n{SERVER_URL}"
                    )
                    # 更新菜单状态文本
                    update_tray_menu()

            # 每10秒检查一次状态
            time.sleep(10)

        except Exception:
            # 检查出错，继续运行
            time.sleep(10)


def start_server():
    """启动MCP服务器（在后台线程中）"""
    global server_process

    # 修复：mcp_dir应该是当前脚本所在目录（mcp_bus），不是parent.parent
    mcp_dir = Path(__file__).parent.resolve()
    server_main = mcp_dir / "server" / "main.py"

    if not server_main.exists():
        print(f"[ERROR] Server file not found: {server_main}")
        print(f"[ERROR] MCP directory: {mcp_dir}")
        print(f"[ERROR] Current working directory: {os.getcwd()}")
        return

    # 使用pythonw.exe（Windows无窗口Python）运行服务器
    python_exe = sys.executable
    if python_exe.endswith("python.exe"):
        pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
        if os.path.exists(pythonw_exe):
            python_exe = pythonw_exe

    # 构建命令
    cmd = [
        python_exe,
        "-m",
        "uvicorn",
        "server.main:app",
        "--host",
        SERVER_HOST,
        "--port",
        SERVER_PORT,
        "--log-level",
        "info",
    ]

    print("[INFO] Starting MCP server...")
    print(f"[INFO] Command: {' '.join(cmd)}")
    print(f"[INFO] Server URL: {SERVER_URL}")
    print(f"[INFO] Working directory: {mcp_dir}")

    # 设置环境变量
    env = os.environ.copy()
    env["REPO_ROOT"] = str(repo_root)
    env["MCP_BUS_HOST"] = SERVER_HOST
    env["MCP_BUS_PORT"] = SERVER_PORT
    env["AUTH_MODE"] = os.getenv("AUTH_MODE", "none")

    try:
        # 修复：使用CREATE_NO_WINDOW但不使用DETACHED_PROCESS，避免进程无法正常启动
        # 同时将错误输出重定向到日志文件，方便调试
        creation_flags = 0
        log_dir = mcp_dir / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        if os.name == "nt":
            creation_flags = subprocess.CREATE_NO_WINDOW

        # 打开日志文件用于写入错误
        with open(log_file, "w", encoding="utf-8") as log_f:
            server_process = subprocess.Popen(
                cmd,
                cwd=str(mcp_dir),
                stdout=log_f,
                stderr=subprocess.STDOUT,  # 将stderr重定向到stdout
                creationflags=creation_flags,
                env=env,
            )

        print(f"[INFO] Server started (PID: {server_process.pid})")
        print(f"[INFO] Log file: {log_file}")

        # 等待进程结束
        server_process.wait()
        print(f"[INFO] Server process ended (exit code: {server_process.returncode})")

        # 如果进程异常退出，读取日志文件显示错误
        if server_process.returncode != 0:
            print(f"[ERROR] Server exited with code {server_process.returncode}")
            if log_file.exists():
                print("[ERROR] Last 20 lines of log:")
                try:
                    with open(log_file, encoding="utf-8") as f:
                        lines = f.readlines()
                        for line in lines[-20:]:
                            print(f"  {line.rstrip()}")
                except Exception as e:
                    print(f"[ERROR] Failed to read log: {e}")

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


def get_status_text():
    """获取当前状态文本"""
    with status_lock:
        status = current_status

    status_map = {
        "healthy": "✓ 正常运行",
        "warning": "⚠ 部分异常",
        "error": "✗ 无法访问",
        "unknown": "? 状态未知",
    }
    return status_map.get(status, "? 状态未知")


def get_detailed_status():
    """获取详细状态信息"""
    try:
        # 获取Freqtrade状态
        freqtrade_status = "未知"
        try:
            freq_req = urllib.request.Request(f"{SERVER_URL}/api/freqtrade/status", method="GET")
            freq_req.add_header("User-Agent", "MCP-Tray-Status-Checker/1.0")
            with urllib.request.urlopen(freq_req, timeout=3) as freq_response:
                if freq_response.status == 200:
                    freq_data = json.loads(freq_response.read().decode())
                    if freq_data.get("webserver", {}).get("running", False):
                        freqtrade_status = "运行中"
                    else:
                        freqtrade_status = "已停止"
        except:
            freqtrade_status = "检查失败"

        # 获取OKX状态
        okx_status = "未知"
        try:
            okx_req = urllib.request.Request(f"{SERVER_URL}/api/exchange/okx/status", method="GET")
            okx_req.add_header("User-Agent", "MCP-Tray-Status-Checker/1.0")
            with urllib.request.urlopen(okx_req, timeout=3) as okx_response:
                if okx_response.status == 200:
                    okx_data = json.loads(okx_response.read().decode())
                    okx_conn = okx_data.get("connection", {})
                    conn_state = okx_conn.get("state", "unknown")
                    if conn_state == "connected":
                        okx_status = "已连接"
                    elif conn_state == "error":
                        okx_status = f"连接失败: {okx_conn.get('detail', '未知错误')}"
                    else:
                        okx_status = "未连接"
        except:
            okx_status = "检查失败"

        return {"freqtrade": freqtrade_status, "okx": okx_status, "server_url": SERVER_URL}
    except:
        return {"freqtrade": "未知", "okx": "未知", "server_url": SERVER_URL}


def on_quit(icon, item):
    """退出处理"""
    global status_check_thread, instance_mutex
    stop_server()
    if status_check_thread and status_check_thread.is_alive():
        # 状态检查线程会在主线程退出时自动结束（daemon=True）
        pass
    # 释放单实例互斥体
    if instance_mutex:
        instance_mutex.release()
    if icon:
        icon.stop()


def on_open_dashboard(icon, item):
    """打开仪表板"""
    import webbrowser

    webbrowser.open(SERVER_URL)


def on_open_frequi(icon, item):
    """打开FreqUI"""
    import webbrowser

    webbrowser.open(f"{SERVER_URL}/frequi")


def on_open_viewer(icon, item):
    """打开Web查看器"""
    import webbrowser

    webbrowser.open(f"{SERVER_URL}/viewer")


def on_open_monitoring(icon, item):
    """打开监控面板"""
    import webbrowser

    webbrowser.open(f"{SERVER_URL}/monitoring")


def on_show_status(icon, item):
    """显示状态信息（带颜色和可关闭功能）"""
    import tkinter as tk

    status_text = get_status_text()
    with status_lock:
        status = current_status

    # 获取详细状态
    detailed = get_detailed_status()

    # 状态颜色说明（增强版，更多颜色）
    color_desc = {
        "healthy": "🟢 绿色: 服务器正常运行，所有服务正常",
        "warning": "🟡 黄色: 服务器运行但部分服务异常",
        "error": "🔴 红色: 服务器无法访问或严重错误",
        "unknown": "⚪ 灰色: 服务器启动中或状态未知",
    }

    # 根据状态选择消息框类型和图标
    status_icons = {
        "healthy": "info",  # 绿色信息图标
        "warning": "warning",  # 黄色警告图标
        "error": "error",  # 红色错误图标
        "unknown": "question",  # 灰色问号图标
    }

    # 构建状态信息
    info = f"""MCP Bus Server 状态

服务器地址: {SERVER_URL}
当前状态: {status_text}
图标颜色: {color_desc.get(status, "未知")}

服务状态:
• Freqtrade: {detailed.get("freqtrade", "未知")}
• OKX连接: {detailed.get("okx", "未知")}

状态说明:
• 🟢 绿色: 服务器正常运行，所有服务正常
• 🟡 黄色: 服务器运行但部分服务异常（Freqtrade未启动或OKX连接失败）
• 🔴 红色: 服务器无法访问或严重错误
• ⚪ 灰色: 服务器启动中或状态未知

更新时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""

    # 创建自定义对话框窗口（可关闭，带颜色）
    root = tk.Tk()
    root.title("MCP Bus Server 状态")
    root.geometry("500x450")
    root.resizable(False, False)

    # 根据状态设置窗口颜色主题
    status_colors = {
        "healthy": {"bg": "#f0fdf4", "fg": "#166534", "accent": "#10b981"},  # 绿色主题
        "warning": {"bg": "#fffbeb", "fg": "#92400e", "accent": "#f59e0b"},  # 黄色主题
        "error": {"bg": "#fef2f2", "fg": "#991b1b", "accent": "#ef4444"},  # 红色主题
        "unknown": {"bg": "#f9fafb", "fg": "#374151", "accent": "#6b7280"},  # 灰色主题
    }

    colors = status_colors.get(status, status_colors["unknown"])
    root.configure(bg=colors["bg"])

    # 标题栏（带颜色指示）
    title_frame = tk.Frame(root, bg=colors["accent"], height=50)
    title_frame.pack(fill=tk.X)
    title_frame.pack_propagate(False)

    title_label = tk.Label(
        title_frame,
        text="MCP Bus Server 状态",
        font=("Arial", 14, "bold"),
        bg=colors["accent"],
        fg="white",
    )
    title_label.pack(pady=15)

    # 关闭按钮（右上角）
    close_btn = tk.Button(
        title_frame,
        text="✕",
        font=("Arial", 12, "bold"),
        bg=colors["accent"],
        fg="white",
        activebackground="#dc2626",
        activeforeground="white",
        border=0,
        width=3,
        height=1,
        command=root.destroy,
        cursor="hand2",
    )
    close_btn.place(relx=0.95, rely=0.5, anchor=tk.CENTER)

    # 内容区域
    content_frame = tk.Frame(root, bg=colors["bg"], padx=20, pady=15)
    content_frame.pack(fill=tk.BOTH, expand=True)

    # 状态指示器（大号彩色圆点）
    status_frame = tk.Frame(content_frame, bg=colors["bg"])
    status_frame.pack(fill=tk.X, pady=(0, 15))

    # 状态圆点（大号）
    status_canvas = tk.Canvas(
        status_frame, width=30, height=30, bg=colors["bg"], highlightthickness=0
    )
    status_canvas.pack(side=tk.LEFT, padx=(0, 10))
    status_canvas.create_oval(5, 5, 25, 25, fill=colors["accent"], outline=colors["accent"])

    status_label = tk.Label(
        status_frame,
        text=f"当前状态: {status_text}",
        font=("Arial", 12, "bold"),
        bg=colors["bg"],
        fg=colors["fg"],
    )
    status_label.pack(side=tk.LEFT)

    # 服务器地址
    url_label = tk.Label(
        content_frame,
        text=f"服务器地址: {SERVER_URL}",
        font=("Arial", 10),
        bg=colors["bg"],
        fg=colors["fg"],
    )
    url_label.pack(anchor=tk.W, pady=(0, 10))

    # 图标颜色说明
    color_label = tk.Label(
        content_frame,
        text=f"图标颜色: {color_desc.get(status, '未知')}",
        font=("Arial", 10, "bold"),
        bg=colors["bg"],
        fg=colors["accent"],
    )
    color_label.pack(anchor=tk.W, pady=(0, 15))

    # 服务状态（带颜色指示）
    services_frame = tk.LabelFrame(
        content_frame,
        text="服务状态",
        font=("Arial", 10, "bold"),
        bg=colors["bg"],
        fg=colors["fg"],
        padx=10,
        pady=10,
    )
    services_frame.pack(fill=tk.X, pady=(0, 15))

    # Freqtrade状态（带颜色）
    freq_status = detailed.get("freqtrade", "未知")
    freq_color = (
        "#10b981"
        if freq_status == "运行中"
        else "#ef4444"
        if freq_status == "检查失败"
        else "#6b7280"
    )
    freq_label = tk.Label(
        services_frame,
        text=f"• Freqtrade: {freq_status}",
        font=("Arial", 10),
        bg=colors["bg"],
        fg=freq_color,
    )
    freq_label.pack(anchor=tk.W, pady=2)

    # OKX状态（带颜色）
    okx_status = detailed.get("okx", "未知")
    okx_color = (
        "#10b981" if okx_status == "已连接" else "#ef4444" if "失败" in okx_status else "#6b7280"
    )
    okx_label = tk.Label(
        services_frame,
        text=f"• OKX连接: {okx_status}",
        font=("Arial", 10),
        bg=colors["bg"],
        fg=okx_color,
    )
    okx_label.pack(anchor=tk.W, pady=2)

    # 状态说明（带颜色圆点）
    legend_frame = tk.LabelFrame(
        content_frame,
        text="图标颜色说明",
        font=("Arial", 10, "bold"),
        bg=colors["bg"],
        fg=colors["fg"],
        padx=10,
        pady=10,
    )
    legend_frame.pack(fill=tk.X, pady=(0, 10))

    legend_items = [
        ("🟢", "绿色", "服务器正常运行，所有服务正常"),
        ("🟡", "黄色", "服务器运行但部分服务异常"),
        ("🔴", "红色", "服务器无法访问或严重错误"),
        ("⚪", "灰色", "服务器启动中或状态未知"),
    ]

    for icon, color_name, desc in legend_items:
        legend_item = tk.Label(
            legend_frame,
            text=f"{icon} {color_name}: {desc}",
            font=("Arial", 9),
            bg=colors["bg"],
            fg=colors["fg"],
            anchor=tk.W,
        )
        legend_item.pack(anchor=tk.W, pady=2)

    # 更新时间
    time_label = tk.Label(
        content_frame,
        text=f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        font=("Arial", 9),
        bg=colors["bg"],
        fg="#6b7280",
    )
    time_label.pack(anchor=tk.W, pady=(5, 0))

    # 确定按钮（带颜色）
    button_frame = tk.Frame(root, bg=colors["bg"], pady=15)
    button_frame.pack(fill=tk.X)

    ok_btn = tk.Button(
        button_frame,
        text="确定",
        font=("Arial", 10, "bold"),
        bg=colors["accent"],
        fg="white",
        activebackground=colors["fg"],
        activeforeground="white",
        border=0,
        width=10,
        height=2,
        command=root.destroy,
        cursor="hand2",
    )
    ok_btn.pack()

    # 绑定ESC键关闭
    root.bind("<Escape>", lambda e: root.destroy())
    root.focus_set()

    # 居中显示窗口
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = (root.winfo_screenwidth() // 2) - (width // 2)
    y = (root.winfo_screenheight() // 2) - (height // 2)
    root.geometry(f"{width}x{height}+{x}+{y}")

    # 显示窗口（模态）
    root.mainloop()


def update_tray_menu():
    """更新托盘菜单（动态更新状态）"""
    if not HAS_PYSTRAY or not tray_icon:
        return

    status_text = get_status_text()
    menu = pystray.Menu(
        pystray.MenuItem(f"状态: {status_text}", on_show_status),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("打开仪表板", on_open_dashboard),
        pystray.MenuItem("打开FreqUI", on_open_frequi),
        pystray.MenuItem("打开Web查看器", on_open_viewer),
        pystray.MenuItem("打开监控面板", on_open_monitoring),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_quit),
    )
    tray_icon.menu = menu


def setup_tray_menu():
    """设置系统托盘菜单"""
    if not HAS_PYSTRAY:
        return None

    status_text = get_status_text()
    menu = pystray.Menu(
        pystray.MenuItem(f"状态: {status_text}", on_show_status),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("打开仪表板", on_open_dashboard),
        pystray.MenuItem("打开FreqUI", on_open_frequi),
        pystray.MenuItem("打开Web查看器", on_open_viewer),
        pystray.MenuItem("打开监控面板", on_open_monitoring),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", on_quit),
    )

    # 初始图标（灰色，启动中）
    image = create_tray_icon("gray")
    if image:
        icon = pystray.Icon("MCP Server", image, f"MCP Bus Server\n启动中...\n{SERVER_URL}", menu)
        return icon
    return None


def main():
    """主函数"""
    global server_thread, tray_icon, status_check_thread, instance_mutex

    print("[INFO] Starting MCP Server with Enhanced System Tray...")
    print(f"[INFO] REPO_ROOT: {os.environ['REPO_ROOT']}")
    print(f"[INFO] Server URL: {SERVER_URL}")

    # 使用Windows命名互斥体检查单实例（最成熟和通用的方法）
    print("[INFO] Checking for existing server instance...")
    instance_mutex = SingleInstance()

    if instance_mutex.already_running:
        print("[WARN] Another server instance is already running")
        print("[WARN] Exiting to avoid duplicate instances and resource waste")
        print("[INFO] If you want to start a new instance, please stop the existing one first")

        # 尝试显示系统通知（如果可能）
        try:
            if HAS_PYSTRAY:
                # 创建一个临时图标显示通知
                temp_image = create_tray_icon("yellow")
                if temp_image:
                    temp_icon = pystray.Icon("MCP Server", temp_image, "服务器已在运行")
                    temp_icon.visible = True
                    time.sleep(2)
                    temp_icon.visible = False
                    temp_icon.stop()
        except:
            pass

        # 尝试显示Windows通知（可选，不强制）
        try:
            import win10toast

            toaster = win10toast.ToastNotifier()
            toaster.show_toast(
                "MCP Server", "服务器已在运行，避免重复启动", duration=3, icon_path=None
            )
        except ImportError:
            # win10toast未安装，忽略
            pass
        except:
            # 其他错误，忽略
            pass

        instance_mutex.release()
        sys.exit(0)

    print("[INFO] No existing server instance found, starting new server...")
    print("[INFO] Tray icon colors:")
    print("  🟢 Green: Server healthy, all services OK")
    print("  🟡 Yellow: Server running but some services abnormal")
    print("  🔴 Red: Server unreachable or error")
    print("  ⚪ Gray: Server starting or status unknown")

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
            print("[INFO] Icon color will change based on server status")

            # 启动状态检查线程
            status_check_thread = threading.Thread(target=status_check_loop, daemon=True)
            status_check_thread.start()
            print("[INFO] Status check thread started")

            # 运行托盘图标（阻塞，直到图标被停止）
            tray_icon.run()
        else:
            print("[WARN] Failed to create tray icon, running without tray")
            server_thread.join()
    else:
        print("[WARN] Running without system tray icon")
        print("[INFO] Install pystray and pillow for tray icon support")
        server_thread.join()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user")
        stop_server()
        if instance_mutex:
            instance_mutex.release()
    except Exception as e:
        print(f"[ERROR] Fatal error: {e}")
        import traceback

        traceback.print_exc()
        stop_server()
        if instance_mutex:
            instance_mutex.release()
        sys.exit(1)
