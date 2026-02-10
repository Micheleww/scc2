#!/usr/bin/env python3
"""
测试Dashboard集成到MCP服务器
"""

import sys
import time
from pathlib import Path

import requests

# 添加项目路径
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def test_dashboard_integration():
    """测试Dashboard集成"""
    print("=" * 60)
    print("Dashboard集成测试")
    print("=" * 60)

    mcp_url = "http://127.0.0.1:18788/"
    dashboard_url = "http://127.0.0.1:8051"

    # 测试1: MCP服务器健康检查
    print("\n--- 测试1: MCP服务器健康检查 ---")
    try:
        response = requests.get(f"{mcp_url}/health", timeout=5)
        if response.status_code == 200:
            print("[OK] MCP服务器运行正常")
        else:
            print(f"[FAIL] MCP服务器响应状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"[FAIL] MCP服务器未运行: {e}")
        print("请先启动MCP服务器: python -m tools.mcp_bus.server.main")
        return False

    # 测试2: Dashboard代理路由
    print("\n--- 测试2: Dashboard代理路由 ---")
    try:
        response = requests.get(f"{mcp_url}/dashboard/", timeout=10)
        if response.status_code == 200:
            print("[OK] Dashboard代理路由正常")
            print(f"    响应长度: {len(response.text)} 字节")
            if "Quant Control Center" in response.text or "Dashboard" in response.text:
                print("[OK] Dashboard内容正确")
            else:
                print("[WARN] Dashboard内容可能不正确")
        elif response.status_code == 503:
            print("[WARN] Dashboard服务未启动，等待启动...")
            # 等待Dashboard启动
            for i in range(10):
                time.sleep(2)
                try:
                    check_response = requests.get(f"{dashboard_url}/", timeout=2)
                    if check_response.status_code == 200:
                        print("[OK] Dashboard已启动")
                        break
                except:
                    pass
            # 再次测试代理
            response = requests.get(f"{mcp_url}/dashboard/", timeout=10)
            if response.status_code == 200:
                print("[OK] Dashboard代理路由正常（重试后）")
            else:
                print(f"[FAIL] Dashboard代理路由失败: {response.status_code}")
        else:
            print(f"[FAIL] Dashboard代理路由响应状态码: {response.status_code}")
    except Exception as e:
        print(f"[FAIL] Dashboard代理路由错误: {e}")

    # 测试3: Dashboard直接访问
    print("\n--- 测试3: Dashboard直接访问 ---")
    try:
        response = requests.get(f"{dashboard_url}/", timeout=5)
        if response.status_code == 200:
            print("[OK] Dashboard直接访问正常")
        else:
            print(f"[WARN] Dashboard直接访问状态码: {response.status_code}")
    except Exception as e:
        print(f"[WARN] Dashboard直接访问失败（可能未启动）: {e}")

    # 测试4: OKX连接Tab
    print("\n--- 测试4: OKX连接Tab ---")
    try:
        response = requests.get(f"{mcp_url}/dashboard/#tab-okx-connection", timeout=10)
        if response.status_code == 200:
            if "tab-okx-connection" in response.text or "OKX" in response.text:
                print("[OK] OKX连接Tab存在")
            else:
                print("[WARN] OKX连接Tab可能不存在")
        else:
            print(f"[WARN] 无法访问OKX连接Tab: {response.status_code}")
    except Exception as e:
        print(f"[WARN] OKX连接Tab访问错误: {e}")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n访问地址:")
    print(f"  MCP服务器: {mcp_url}")
    print(f"  Dashboard (通过MCP): {mcp_url}/dashboard")
    print(f"  Dashboard (直接访问): {dashboard_url}")
    print(f"  OKX连接Tab: {mcp_url}/dashboard/#tab-okx-connection")


if __name__ == "__main__":
    test_dashboard_integration()
