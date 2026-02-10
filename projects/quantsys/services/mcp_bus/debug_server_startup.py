#!/usr/bin/env python
"""调试服务器启动和Freqtrade自动启动问题"""

import subprocess
from pathlib import Path

import psutil
import requests


def check_process_env(pid):
    """检查进程的环境变量"""
    try:
        p = psutil.Process(pid)
        env = p.environ()
        relevant = {
            k: v
            for k, v in env.items()
            if "FREQTRADE" in k or "AUTO_START" in k or "REPO_ROOT" in k or "MCP_BUS" in k
        }
        return relevant
    except Exception as e:
        return {"error": str(e)}


def check_freqtrade_process():
    """检查Freqtrade进程"""
    print("=== 检查Freqtrade进程 ===")
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if "freqtrade" in cmdline.lower() and "webserver" in cmdline.lower():
                print("找到Freqtrade进程:")
                print(f"  PID: {proc.info['pid']}")
                print(f"  命令: {cmdline[:100]}")
                print(f"  状态: {proc.status()}")
                return proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    print("  未找到Freqtrade进程")
    return None


def check_server_process():
    """检查服务器进程"""
    print("\n=== 检查服务器进程 ===")
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        lines = result.stdout.split("\n")
        for line in lines:
            if ":8000" in line and "LISTENING" in line:
                parts = line.split()
                pid = parts[-1]
                print(f"服务器PID: {pid}")
                try:
                    p = psutil.Process(int(pid))
                    print(f"  进程名: {p.name()}")
                    print(f"  命令行: {' '.join(p.cmdline()[:5])}...")
                    print(f"  启动时间: {p.create_time()}")
                    env = check_process_env(int(pid))
                    if env:
                        print("  相关环境变量:")
                        for k, v in env.items():
                            print(f"    {k}={v}")
                    else:
                        print("  未找到相关环境变量")
                    return int(pid)
                except Exception as e:
                    print(f"  错误: {e}")
    except Exception as e:
        print(f"检查失败: {e}")
    return None


def check_api_status():
    """检查API状态"""
    print("\n=== 检查API状态 ===")
    try:
        r = requests.get("http://127.0.0.1:18788/api/freqtrade/status", timeout=5)
        status = r.json()
        print("Freqtrade状态:")
        print(f"  WebServer运行: {status['webserver']['running']}")
        print(f"  PID: {status['webserver']['pid']}")
        if status["webserver"]["pid"]:
            pid = status["webserver"]["pid"]
            if psutil.pid_exists(pid):
                p = psutil.Process(pid)
                print(f"  PID {pid} 进程存在: {p.status()}")
            else:
                print(f"  PID {pid} 进程不存在（已退出）")
        return status
    except Exception as e:
        print(f"API检查失败: {e}")
        return None


def check_port_8080():
    """检查8080端口"""
    print("\n=== 检查8080端口 ===")
    try:
        result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
        lines = result.stdout.split("\n")
        found = False
        for line in lines:
            if ":8080" in line and "LISTENING" in line:
                print(f"  找到监听: {line.strip()}")
                found = True
        if not found:
            print("  8080端口未被占用（Freqtrade未运行）")
    except Exception as e:
        print(f"检查失败: {e}")


def check_env_file():
    """检查.env文件"""
    print("\n=== 检查.env文件 ===")
    env_paths = [
        Path("d:/quantsys/tools/mcp_bus/.env"),
        Path("d:/quantsys/.env"),
    ]
    for env_path in env_paths:
        if env_path.exists():
            print(f"找到: {env_path}")
            content = env_path.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.strip() and not line.strip().startswith("#"):
                    print(f"  {line.rstrip()}")
            return True
    print("未找到.env文件")
    return False


def main():
    print("=" * 60)
    print("服务器启动调试工具")
    print("=" * 60)
    print()

    server_pid = check_server_process()
    freqtrade_pid = check_freqtrade_process()
    check_port_8080()
    status = check_api_status()
    check_env_file()

    print("\n" + "=" * 60)
    print("诊断结果")
    print("=" * 60)

    if status and not status["webserver"]["running"]:
        print("\n[问题] Freqtrade WebServer未运行")
        if status["webserver"]["pid"]:
            print(f"  记录的PID: {status['webserver']['pid']}")
            if not psutil.pid_exists(status["webserver"]["pid"]):
                print("  进程已退出（可能启动后立即崩溃）")
        print("\n可能的原因:")
        print("  1. 服务器启动时环境变量未设置")
        print("  2. Freqtrade进程启动后立即退出")
        print("  3. 配置文件错误")
        print("\n建议:")
        print("  1. 检查服务器启动日志")
        print("  2. 检查freqtrade_webserver.log查看错误")
        print("  3. 重启服务器使用正确的启动脚本")


if __name__ == "__main__":
    main()
