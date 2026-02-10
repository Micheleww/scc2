#!/usr/bin/env python
"""检查Freqtrade自动启动配置和状态"""

import os
from pathlib import Path

import requests


def check_environment():
    """检查环境变量"""
    print("=== 环境变量检查 ===")
    auto_start = os.getenv("AUTO_START_FREQTRADE", "NOT SET")
    print(f"AUTO_START_FREQTRADE: {auto_start}")
    print(f"REPO_ROOT: {os.getenv('REPO_ROOT', 'NOT SET')}")
    print(f"MCP_BUS_HOST: {os.getenv('MCP_BUS_HOST', 'NOT SET')}")
    print(f"MCP_BUS_PORT: {os.getenv('MCP_BUS_PORT', 'NOT SET')}")
    print()


def check_server_status():
    """检查服务器状态"""
    print("=== 服务器状态检查 ===")
    try:
        r = requests.get("http://127.0.0.1:18788/health", timeout=5)
        if r.status_code == 200:
            print("[OK] MCP服务器正在运行")
            print(f"   响应: {r.json()}")
        else:
            print(f"[WARN] MCP服务器响应异常: {r.status_code}")
    except Exception as e:
        print(f"[ERROR] MCP服务器未运行或无法访问: {e}")
        return False
    print()
    return True


def check_freqtrade_status():
    """检查Freqtrade状态"""
    print("=== Freqtrade状态检查 ===")
    try:
        r = requests.get("http://127.0.0.1:18788/api/freqtrade/status", timeout=5)
        status = r.json()
        print(f"WebServer运行: {status['webserver']['running']}")
        print(f"Trade进程运行: {status['trade']['running']}")
        if status["webserver"]["running"]:
            print(f"PID: {status['webserver']['pid']}")
            print(f"API URL: {status['webserver']['api_url']}")
            if status["webserver"].get("uptime_seconds"):
                print(f"运行时间: {int(status['webserver']['uptime_seconds'])}秒")
        else:
            print("[WARN] Freqtrade WebServer未运行")
            if status.get("last_error"):
                print(f"   最后错误: {status['last_error']}")
    except Exception as e:
        print(f"[ERROR] 无法获取Freqtrade状态: {e}")
    print()


def check_startup_script():
    """检查启动脚本配置"""
    print("=== 启动脚本检查 ===")
    script_path = Path("d:/quantsys/tools/mcp_bus/start_mcp_server.ps1")
    if script_path.exists():
        content = script_path.read_text(encoding="utf-8")
        if "AUTO_START_FREQTRADE" in content:
            print("[OK] 启动脚本包含AUTO_START_FREQTRADE配置")
            # 查找相关行
            for i, line in enumerate(content.split("\n"), 1):
                if "AUTO_START_FREQTRADE" in line:
                    print(f"   第{i}行: {line.strip()}")
        else:
            print("[ERROR] 启动脚本未包含AUTO_START_FREQTRADE配置")
    else:
        print(f"⚠️ 启动脚本不存在: {script_path}")
    print()


def main():
    print("=" * 60)
    print("Freqtrade自动启动诊断工具")
    print("=" * 60)
    print()

    check_environment()
    check_startup_script()

    if check_server_status():
        check_freqtrade_status()

    print("=" * 60)
    print("诊断完成")
    print("=" * 60)
    print()
    print("建议:")
    print("1. 如果AUTO_START_FREQTRADE未设置，请使用start_mcp_server.ps1启动服务器")
    print("2. 如果服务器已运行但Freqtrade未启动，请重启服务器")
    print("3. 检查服务器日志以查看详细的启动信息")


if __name__ == "__main__":
    main()
