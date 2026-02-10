#!/usr/bin/env python3
"""
测试Agent协作API端点
"""

import io
import sys
from typing import Any

import requests

# 设置标准输出编码为UTF-8（Windows兼容）
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_URL = "http://127.0.0.1:18788/"


def test_endpoint(
    endpoint: str, method: str = "GET", data: dict[str, Any] = None
) -> dict[str, Any]:
    """测试API端点"""
    url = f"{BASE_URL}{endpoint}"
    try:
        if method == "GET":
            response = requests.get(url, timeout=5)
        else:
            response = requests.post(url, json=data, timeout=5)

        response.raise_for_status()
        return {"success": True, "status_code": response.status_code, "data": response.json()}
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "status_code": getattr(e.response, "status_code", None)
            if hasattr(e, "response")
            else None,
        }


def test_statistics():
    """测试统计API"""
    print("\n=== 测试统计API ===")
    result = test_endpoint("/api/collaboration/statistics")
    if result["success"]:
        data = result["data"]
        print("✅ 统计API正常")
        print(f"  Agents: {data.get('agents', {})}")
        print(f"  Tasks: {data.get('tasks', {})}")
        print(f"  Workflows: {data.get('workflows', {})}")
        return True
    else:
        print(f"❌ 统计API失败: {result['error']}")
        return False


def test_agents():
    """测试Agents API"""
    print("\n=== 测试Agents API ===")
    result = test_endpoint("/api/collaboration/agents")
    if result["success"]:
        data = result["data"]
        print("✅ Agents API正常")
        print(f"  总数: {data.get('total', 0)}")
        print(f"  Agents: {len(data.get('agents', []))} 个")
        return True
    else:
        print(f"❌ Agents API失败: {result['error']}")
        return False


def test_tasks():
    """测试Tasks API"""
    print("\n=== 测试Tasks API ===")
    result = test_endpoint("/api/collaboration/tasks")
    if result["success"]:
        data = result["data"]
        print("✅ Tasks API正常")
        print(f"  总数: {data.get('total', 0)}")
        print(f"  Tasks: {len(data.get('tasks', []))} 个")
        return True
    else:
        print(f"❌ Tasks API失败: {result['error']}")
        return False


def test_workflows():
    """测试Workflows API"""
    print("\n=== 测试Workflows API ===")
    result = test_endpoint("/api/collaboration/workflows")
    if result["success"]:
        data = result["data"]
        print("✅ Workflows API正常")
        print(f"  总数: {data.get('total', 0)}")
        print(f"  Workflows: {len(data.get('workflows', []))} 个")
        return True
    else:
        print(f"❌ Workflows API失败: {result['error']}")
        return False


def test_html_pages():
    """测试HTML页面"""
    print("\n=== 测试HTML页面 ===")
    pages = [
        ("/collaboration", "协作管理页面"),
        ("/dashboard", "Dashboard页面"),
        ("/viewer", "Web查看器页面"),
    ]

    all_passed = True
    for endpoint, name in pages:
        result = test_endpoint(endpoint)
        if result["success"]:
            # 检查是否是HTML响应
            if "text/html" in result.get("headers", {}).get("content-type", ""):
                print(f"✅ {name}正常加载")
            else:
                # 尝试检查内容
                url = f"{BASE_URL}{endpoint}"
                try:
                    response = requests.get(url, timeout=5)
                    if response.text.strip().startswith("<!DOCTYPE"):
                        print(f"✅ {name}正常加载")
                    else:
                        print(f"⚠️  {name}返回了非HTML内容")
                        all_passed = False
                except:
                    print(f"❌ {name}加载失败")
                    all_passed = False
        else:
            print(f"❌ {name}加载失败: {result['error']}")
            all_passed = False

    return all_passed


def main():
    """主测试函数"""
    print("=" * 60)
    print("Agent协作API测试")
    print("=" * 60)

    results = []
    results.append(("统计API", test_statistics()))
    results.append(("Agents API", test_agents()))
    results.append(("Tasks API", test_tasks()))
    results.append(("Workflows API", test_workflows()))
    results.append(("HTML页面", test_html_pages()))

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  有 {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
