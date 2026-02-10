#!/usr/bin/env python
"""测试Freqtrade自动启动功能"""

import time

import requests


def test_freqtrade_autostart():
    """测试Freqtrade自动启动功能"""
    base_url = "http://127.0.0.1:18788/"

    print("=== 测试Freqtrade自动启动功能 ===\n")

    # 1. 检查MCP服务器状态
    print("1. 检查MCP服务器状态...")
    try:
        r = requests.get(f"{base_url}/health", timeout=5)
        if r.status_code == 200:
            print("   [OK] MCP服务器正在运行\n")
        else:
            print(f"   [WARN] MCP服务器响应异常: {r.status_code}\n")
    except Exception as e:
        print(f"   [ERROR] MCP服务器未运行或无法访问: {e}\n")
        return False

    # 2. 检查Freqtrade状态
    print("2. 检查Freqtrade服务状态...")
    try:
        r = requests.get(f"{base_url}/api/freqtrade/status", timeout=5)
        status = r.json()

        webserver_running = status["webserver"]["running"]
        print(f"   WebServer运行: {webserver_running}")
        print(f"   Trade进程运行: {status['trade']['running']}")

        if webserver_running:
            print(f"   WebServer PID: {status['webserver']['pid']}")
            print(f"   API URL: {status['webserver']['api_url']}")
            if status["webserver"].get("uptime_seconds"):
                print(f"   运行时间: {int(status['webserver']['uptime_seconds'])}秒")
        print()

        # 3. 测试Freqtrade API连接
        print("3. 测试Freqtrade API连接...")
        api_url = status["webserver"].get("api_url")
        if api_url:
            try:
                ping_r = requests.get(f"{api_url}/api/v1/ping", timeout=5)
                print("   [OK] Freqtrade API连接正常")
                print(f"   响应: {ping_r.json()}")
            except Exception as e:
                print(f"   [WARN] Freqtrade API连接失败: {e}")
                print("   这可能是因为Freqtrade WebServer刚启动，需要等待几秒钟")
        else:
            print("   [WARN] Freqtrade WebServer未运行，无法测试API")
        print()

        # 4. 检查FreqUI是否可访问
        print("4. 检查FreqUI是否可访问...")
        try:
            frequi_r = requests.get(f"{base_url}/frequi", timeout=5)
            if frequi_r.status_code == 200:
                print("   [OK] FreqUI可访问")
            else:
                print(f"   [WARN] FreqUI响应异常: {frequi_r.status_code}")
        except Exception as e:
            print(f"   [WARN] FreqUI无法访问: {e}")
        print()

        # 5. 测试启动/停止功能
        print("5. 测试启动/停止功能...")
        # 先停止（如果正在运行）
        if webserver_running:
            print("   停止Freqtrade WebServer...")
            stop_r = requests.post(f"{base_url}/api/freqtrade/webserver/stop", timeout=5)
            print(f"   停止结果: {stop_r.json()}")
            time.sleep(2)

        # 检查状态
        status_r = requests.get(f"{base_url}/api/freqtrade/status", timeout=5)
        status_after_stop = status_r.json()
        print(f"   停止后状态: WebServer运行={status_after_stop['webserver']['running']}")

        # 启动
        print("   启动Freqtrade WebServer...")
        start_r = requests.post(f"{base_url}/api/freqtrade/webserver/start", timeout=5)
        print(f"   启动结果: {start_r.json()}")
        time.sleep(5)

        # 验证启动状态
        status_r2 = requests.get(f"{base_url}/api/freqtrade/status", timeout=5)
        status_after_start = status_r2.json()
        print(f"   启动后状态: WebServer运行={status_after_start['webserver']['running']}")
        if status_after_start["webserver"]["running"]:
            print(f"   PID: {status_after_start['webserver']['pid']}")
            print(f"   API URL: {status_after_start['webserver']['api_url']}")
        print()

        # 总结
        print("=== 测试总结 ===")
        if status_after_start["webserver"]["running"]:
            print("[SUCCESS] Freqtrade WebServer自动启动功能正常！")
            print("   可以通过以下方式访问:")
            print(f"   - FreqUI: {base_url}/frequi")
            print(f"   - Freqtrade API: {status_after_start['webserver']['api_url']}")
            return True
        else:
            print("[FAILED] Freqtrade WebServer未运行")
            print("   可能的原因:")
            print("   1. AUTO_START_FREQTRADE环境变量未设置")
            print("   2. Freqtrade命令未找到（需要安装freqtrade）")
            print("   3. 配置文件路径错误")
            return False

    except Exception as e:
        print(f"   [ERROR] 无法获取Freqtrade状态: {e}")
        print("\n可能的原因:")
        print("  1. MCP服务器未启动")
        print("  2. API端点需要认证（需要登录）")
        print("  3. Freqtrade服务模块未正确加载")
        return False


if __name__ == "__main__":
    success = test_freqtrade_autostart()
    exit(0 if success else 1)
