#!/usr/bin/env python3
"""
启动所有Web服务
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent


def check_port(port):
    """检查端口是否被占用"""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("127.0.0.1", port))
    sock.close()
    return result == 0


def start_mcp_server():
    """启动MCP服务器"""
    print("启动MCP服务器...")

    if check_port(8000):
        print("⚠️ 端口8000已被占用，跳过启动")
        return None

    # 设置环境变量
    env = os.environ.copy()
    env["REPO_ROOT"] = str(REPO_ROOT)
    env["MCP_BUS_HOST"] = "127.0.0.1"
    env["MCP_BUS_PORT"] = "8000"
    env["AUTH_MODE"] = "none"
    env["DASHBOARD_ENABLED"] = "true"

    # 启动服务器
    mcp_dir = REPO_ROOT / "tools" / "mcp_bus"
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "server.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ]

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(mcp_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        # 等待服务器启动
        print("等待MCP服务器启动...")
        for i in range(30):
            time.sleep(1)
            try:
                response = requests.get("http://127.0.0.1:18788/health", timeout=2)
                if response.status_code == 200:
                    print("✅ MCP服务器启动成功")
                    return proc
            except:
                pass
            if i % 5 == 0:
                print(f"  等待中... ({i + 1}/30)")

        print("⚠️ MCP服务器启动超时")
        return proc
    except Exception as e:
        print(f"❌ 启动MCP服务器失败: {e}")
        return None


def check_dashboard():
    """检查Dashboard是否运行"""
    try:
        response = requests.get("http://127.0.0.1:8051", timeout=2)
        if response.status_code == 200:
            print("✅ Dashboard已运行")
            return True
    except:
        pass

    print("⚠️ Dashboard未运行（MCP服务器会自动启动）")
    return False


def main():
    """主函数"""
    print("=" * 80)
    print("启动所有Web服务")
    print("=" * 80)
    print()

    # 检查Dashboard
    check_dashboard()
    print()

    # 启动MCP服务器
    mcp_proc = start_mcp_server()

    if mcp_proc:
        print()
        print("=" * 80)
        print("服务启动完成")
        print("=" * 80)
        print()
        print("访问地址:")
        print("  - 统一管理平台: http://127.0.0.1:18788/")
        print("  - Dashboard: http://127.0.0.1:18788/dashboard")
        print("  - Dashboard（直接）: http://127.0.0.1:8051")
        print()
        print("按 Ctrl+C 停止服务器")
        print()

        try:
            mcp_proc.wait()
        except KeyboardInterrupt:
            print("\n正在停止服务器...")
            mcp_proc.terminate()
            mcp_proc.wait()
            print("服务器已停止")
    else:
        print()
        print("=" * 80)
        print("服务启动失败")
        print("=" * 80)
        print()
        print("请手动启动MCP服务器:")
        print("  python tools/mcp_bus/start_local_mcp.ps1")
        print("  或")
        print(
            "  cd tools/mcp_bus && python -m uvicorn server.main:app --host 127.0.0.1 --port 8000"
        )
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
