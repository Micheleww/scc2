#!/usr/bin/env python3
"""
验证Freqtrade自动启动功能
"""

import sys
import time
from pathlib import Path

import requests


def check_server_running():
    """检查MCP服务器是否运行"""
    try:
        r = requests.get("http://127.0.0.1:18788/health", timeout=2)
        if r.status_code == 200:
            return True, r.json()
        return False, None
    except Exception as e:
        return False, str(e)


def check_freqtrade_status():
    """检查Freqtrade状态"""
    try:
        r = requests.get("http://127.0.0.1:18788/api/freqtrade/status", timeout=5)
        if r.status_code == 200:
            return True, r.json()
        return False, None
    except Exception as e:
        return False, str(e)


def check_freqtrade_port():
    """检查Freqtrade端口"""
    import subprocess

    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=5)
        if ":8080" in result.stdout and "LISTENING" in result.stdout:
            return True
        return False
    except Exception:
        return False


def main():
    print("=" * 60)
    print("Freqtrade自动启动验证")
    print("=" * 60)
    print()

    # 1. 检查MCP服务器
    print("1. 检查MCP服务器状态...")
    server_ok, server_data = check_server_running()
    if server_ok:
        print("   [OK] MCP服务器运行中")
        print(f"   状态: {server_data.get('status', 'N/A')}")
    else:
        print(f"   [ERROR] MCP服务器未运行: {server_data}")
        print("   请先启动MCP服务器: .\\start_mcp_server.ps1")
        return False
    print()

    # 2. 检查Freqtrade状态
    print("2. 检查Freqtrade状态...")
    status_ok, status_data = check_freqtrade_status()
    if status_ok and status_data:
        webserver = status_data.get("webserver", {})
        running = webserver.get("running", False)
        pid = webserver.get("pid")

        if running:
            print("   [OK] Freqtrade WebServer运行中")
            print(f"   PID: {pid}")
            uptime = webserver.get("uptime_seconds")
            if uptime:
                print(f"   运行时长: {int(uptime)}秒")
        else:
            print("   [ERROR] Freqtrade WebServer未运行")
            print(f"   最后错误: {status_data.get('last_error', 'N/A')}")
            print()
            print("   尝试手动启动...")
            try:
                r = requests.post("http://127.0.0.1:18788/api/freqtrade/webserver/start", timeout=10)
                if r.status_code == 200:
                    print("   [OK] 手动启动成功")
                    time.sleep(3)
                    # 再次检查
                    status_ok2, status_data2 = check_freqtrade_status()
                    if status_ok2 and status_data2.get("webserver", {}).get("running"):
                        print("   [OK] 验证: Freqtrade现在运行中")
                    else:
                        print("   [WARN] 启动后验证失败")
                else:
                    print(f"   [ERROR] 手动启动失败: {r.status_code}")
            except Exception as e:
                print(f"   [ERROR] 手动启动异常: {e}")
    else:
        print(f"   [ERROR] 无法获取Freqtrade状态: {status_data}")
    print()

    # 3. 检查端口
    print("3. 检查Freqtrade端口(8080)...")
    port_ok = check_freqtrade_port()
    if port_ok:
        print("   [OK] 端口8080正在监听")
    else:
        print("   [ERROR] 端口8080未监听")
    print()

    # 4. 检查配置文件
    print("4. 检查配置文件...")
    repo_root = Path(__file__).parent.parent.parent
    config1 = repo_root / "configs" / "current" / "freqtrade_config.json"
    config2 = repo_root / "user_data" / "configs" / "freqtrade_live_config.json"

    if config1.exists():
        print(f"   [OK] 主配置文件存在: {config1}")
    else:
        print(f"   [WARN] 主配置文件不存在: {config1}")

    if config2.exists():
        print(f"   [OK] 备用配置文件存在: {config2}")
    else:
        print(f"   [WARN] 备用配置文件不存在: {config2}")
    print()

    # 总结
    print("=" * 60)
    if status_ok and status_data and status_data.get("webserver", {}).get("running"):
        print("[SUCCESS] Freqtrade自动启动功能正常！")
        return True
    else:
        print("[FAILED] Freqtrade未运行，请检查日志和配置")
        print()
        print("建议操作:")
        print("1. 检查日志: Get-Content d:\\quantsys\\logs\\freqtrade_webserver.log -Tail 50")
        print("2. 手动启动: curl -X POST http://127.0.0.1:18788/api/freqtrade/webserver/start")
        print("3. 重启MCP服务器以触发自动启动")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
