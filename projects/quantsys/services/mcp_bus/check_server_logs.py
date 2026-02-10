#!/usr/bin/env python
"""检查服务器日志并调试Freqtrade自动启动问题"""

from datetime import datetime
from pathlib import Path

import requests


def check_server_status():
    """检查服务器状态"""
    print("=== 服务器状态检查 ===")
    try:
        r = requests.get("http://127.0.0.1:18788/health", timeout=5)
        if r.status_code == 200:
            print("[OK] 服务器正在运行")
            print(f"   响应: {r.json()}")
            return True
        else:
            print(f"[WARN] 服务器响应异常: {r.status_code}")
            return False
    except Exception as e:
        print(f"[ERROR] 服务器未运行: {e}")
        return False


def check_freqtrade_status():
    """检查Freqtrade状态"""
    print("\n=== Freqtrade状态检查 ===")
    try:
        r = requests.get("http://127.0.0.1:18788/api/freqtrade/status", timeout=5)
        status = r.json()
        webserver_running = status["webserver"]["running"]
        print(f"WebServer运行: {webserver_running}")
        if webserver_running:
            print(f"  PID: {status['webserver']['pid']}")
            print(f"  API URL: {status['webserver']['api_url']}")
            if status["webserver"].get("uptime_seconds"):
                print(f"  运行时间: {int(status['webserver']['uptime_seconds'])}秒")
        else:
            print("  [WARN] Freqtrade WebServer未运行")
            if status.get("last_error"):
                print(f"  最后错误: {status['last_error']}")
        return status
    except Exception as e:
        print(f"[ERROR] 无法获取Freqtrade状态: {e}")
        return None


def check_log_files():
    """检查日志文件"""
    print("\n=== 日志文件检查 ===")
    repo_root = Path("d:/quantsys")
    log_dir = repo_root / "logs"

    log_files = [
        ("mcp_server.log", "主服务器日志"),
        ("mcp_stdout.log", "服务器标准输出"),
        ("mcp_stderr.log", "服务器标准错误"),
        ("freqtrade_webserver.log", "Freqtrade WebServer日志"),
    ]

    for log_file, description in log_files:
        log_path = log_dir / log_file
        if log_path.exists():
            size = log_path.stat().st_size
            mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
            print(f"[OK] {description}: {log_path}")
            print(f"    大小: {size} 字节")
            print(f"    修改时间: {mtime}")

            # 读取最后几行
            try:
                with open(log_path, encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                    if lines:
                        print("    最后5行:")
                        for line in lines[-5:]:
                            print(f"      {line.rstrip()}")
            except Exception as e:
                print(f"    [ERROR] 读取失败: {e}")
        else:
            print(f"[NOT FOUND] {description}: {log_path}")


def check_startup_logs():
    """检查启动相关日志"""
    print("\n=== 启动日志检查 ===")
    repo_root = Path("d:/quantsys")
    log_dir = repo_root / "logs"

    # 检查mcp_stdout.log中的启动信息
    stdout_log = log_dir / "mcp_stdout.log"
    if stdout_log.exists():
        print("检查mcp_stdout.log中的启动信息...")
        try:
            with open(stdout_log, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                # 查找包含AUTO_START或Freqtrade的行
                relevant_lines = [
                    line
                    for line in lines
                    if "AUTO_START" in line or "Freqtrade" in line or "startup" in line.lower()
                ]
                if relevant_lines:
                    print(f"找到 {len(relevant_lines)} 条相关日志:")
                    for line in relevant_lines[-20:]:  # 最后20条
                        print(f"  {line.rstrip()}")
                else:
                    print("  未找到启动相关日志")
        except Exception as e:
            print(f"  [ERROR] 读取失败: {e}")
    else:
        print("  mcp_stdout.log不存在")


def check_env_file():
    """检查.env文件"""
    print("\n=== .env文件检查 ===")
    env_paths = [
        Path("d:/quantsys/tools/mcp_bus/.env"),
        Path("d:/quantsys/.env"),
    ]

    for env_path in env_paths:
        if env_path.exists():
            print(f"[OK] 找到.env文件: {env_path}")
            try:
                content = env_path.read_text(encoding="utf-8")
                print("  内容:")
                for line in content.split("\n"):
                    if line.strip() and not line.strip().startswith("#"):
                        print(f"    {line.rstrip()}")
            except Exception as e:
                print(f"  [ERROR] 读取失败: {e}")
            break
    else:
        print("[NOT FOUND] 未找到.env文件")


def main():
    print("=" * 60)
    print("服务器日志调试工具")
    print("=" * 60)
    print()

    if not check_server_status():
        print("\n服务器未运行，无法继续检查")
        return

    check_freqtrade_status()
    check_log_files()
    check_startup_logs()
    check_env_file()

    print("\n" + "=" * 60)
    print("调试完成")
    print("=" * 60)
    print("\n建议:")
    print("1. 如果Freqtrade未运行，检查启动日志中的错误信息")
    print("2. 检查.env文件是否正确配置")
    print("3. 重启服务器以应用新的配置")


if __name__ == "__main__":
    main()
