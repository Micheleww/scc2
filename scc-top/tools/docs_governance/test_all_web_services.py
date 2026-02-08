#!/usr/bin/env python3
"""
测试所有Web服务功能
"""

import sys
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent


def test_service(name, url, timeout=5):
    """测试服务是否可用"""
    try:
        response = requests.get(url, timeout=timeout, allow_redirects=True)
        return {
            "name": name,
            "url": url,
            "status": "ok" if response.status_code == 200 else "error",
            "status_code": response.status_code,
            "error": None,
        }
    except requests.exceptions.ConnectionError:
        return {
            "name": name,
            "url": url,
            "status": "not_running",
            "status_code": None,
            "error": "Connection refused",
        }
    except requests.exceptions.Timeout:
        return {
            "name": name,
            "url": url,
            "status": "timeout",
            "status_code": None,
            "error": "Request timeout",
        }
    except Exception as e:
        return {"name": name, "url": url, "status": "error", "status_code": None, "error": str(e)}


def main():
    """主函数"""
    print("=" * 80)
    print("Web服务功能测试")
    print("=" * 80)
    print()

    services = [
        ("MCP服务器（统一管理平台）", "http://127.0.0.1:18788/"),
        ("Dashboard（直接访问）", "http://127.0.0.1:8051"),
        ("Dashboard（通过MCP代理）", "http://127.0.0.1:18788/dashboard"),
        ("Web Viewer", "http://127.0.0.1:18788/viewer"),
        ("Agent协作", "http://127.0.0.1:18788/collaboration"),
        ("FreqUI", "http://127.0.0.1:18788/frequi"),
        ("健康检查", "http://127.0.0.1:18788/health"),
        ("MCP API端点", "http://127.0.0.1:18788/mcp"),
    ]

    results = []
    for name, url in services:
        print(f"测试 {name}...", end=" ")
        result = test_service(name, url)
        results.append(result)

        if result["status"] == "ok":
            print(f"✅ OK (HTTP {result['status_code']})")
        elif result["status"] == "not_running":
            print("❌ 未运行")
        elif result["status"] == "timeout":
            print("⏱️ 超时")
        else:
            print(f"❌ 错误: {result['error']}")

    print()
    print("=" * 80)
    print("测试总结")
    print("=" * 80)

    ok_count = sum(1 for r in results if r["status"] == "ok")
    total_count = len(results)

    print(f"通过: {ok_count}/{total_count}")
    print()

    if ok_count == 0:
        print("⚠️ 所有服务都未运行")
        print()
        print("启动建议:")
        print("1. 启动MCP服务器:")
        print("   python tools/mcp_bus/start_local_mcp.ps1")
        print("   或")
        print(
            "   cd tools/mcp_bus && python -m uvicorn server.main:app --host 127.0.0.1 --port 8000"
        )
        print()
        print("2. Dashboard会自动启动（如果DASHBOARD_ENABLED=true）")
        print()
    elif ok_count < total_count:
        print("⚠️ 部分服务未运行")
        print()
        print("未运行的服务:")
        for r in results:
            if r["status"] != "ok":
                print(f"  - {r['name']}: {r['url']}")
                if r["error"]:
                    print(f"    错误: {r['error']}")
        print()
    else:
        print("✅ 所有服务正常运行")
        print()
        print("访问地址:")
        print("  - 统一管理平台: http://127.0.0.1:18788/")
        print("  - Dashboard: http://127.0.0.1:18788/dashboard")
        print("  - Dashboard（直接）: http://127.0.0.1:8051")

    return 0 if ok_count == total_count else 1


if __name__ == "__main__":
    exit(main())
