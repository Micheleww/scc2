#!/usr/bin/env python3
"""
Dashboard最终检查 - 确保所有功能正常
"""

import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def check_all():
    """检查所有Dashboard功能"""
    print("=" * 80)
    print("Dashboard最终检查")
    print("=" * 80)
    print()

    all_ok = True

    # 1. 检查MCP服务器
    print("1. 检查MCP服务器:")
    try:
        r = requests.get("http://127.0.0.1:18788/", timeout=5)
        if r.status_code == 200:
            print("   [OK] MCP服务器运行正常")
        else:
            print(f"   [FAIL] MCP服务器: {r.status_code}")
            all_ok = False
    except Exception as e:
        print(f"   [FAIL] MCP服务器: {e}")
        all_ok = False

    # 2. 检查Dashboard HTML
    print("2. 检查Dashboard HTML:")
    try:
        r = requests.get("http://127.0.0.1:18788/dashboard", timeout=5)
        if r.status_code == 200:
            print(f"   [OK] Dashboard HTML: {r.status_code} ({len(r.content)} bytes)")
            if len(r.content) > 1000:
                print("   [OK] HTML内容完整")
            else:
                print("   [WARN] HTML内容可能不完整")
        else:
            print(f"   [FAIL] Dashboard HTML: {r.status_code}")
            all_ok = False
    except Exception as e:
        print(f"   [FAIL] Dashboard HTML: {e}")
        all_ok = False

    # 3. 检查关键资源
    print("3. 检查关键资源:")
    resources = [
        ("/_dash-layout", "Dashboard布局数据"),
        ("/_dash-dependencies", "Dashboard依赖数据"),
        (
            "/_dash-component-suites/dash/deps/polyfill@7.v3_3_0m1767941296.12.1.min.js",
            "Dashboard JS资源",
        ),
    ]

    for path, desc in resources:
        try:
            r = requests.get(f"http://127.0.0.1:18788/{path}", timeout=3)
            if r.status_code == 200:
                print(f"   [OK] {desc}: {r.status_code} ({len(r.content)} bytes)")
            else:
                print(f"   [FAIL] {desc}: {r.status_code}")
                all_ok = False
        except Exception as e:
            print(f"   [FAIL] {desc}: {e}")
            all_ok = False

    # 4. 检查Dashboard直接访问
    print("4. 检查Dashboard直接访问:")
    try:
        r = requests.get("http://127.0.0.1:8051", timeout=5)
        if r.status_code == 200:
            print(f"   [OK] Dashboard直接访问: {r.status_code}")
        else:
            print(f"   [FAIL] Dashboard直接访问: {r.status_code}")
            all_ok = False
    except Exception as e:
        print(f"   [FAIL] Dashboard直接访问: {e}")
        all_ok = False

    print()
    print("=" * 80)
    if all_ok:
        print("[OK] 所有检查通过")
        print()
        print("访问地址:")
        print("  - 统一管理平台: http://127.0.0.1:18788/")
        print("  - Dashboard: http://127.0.0.1:18788/dashboard")
        print()
        print("如果Dashboard UI仍然显示Loading，请:")
        print("  1. 刷新浏览器页面（Ctrl+F5强制刷新）")
        print("  2. 清除浏览器缓存")
        print("  3. 检查浏览器控制台是否有错误")
    else:
        print("[FAIL] 部分检查失败")
        print()
        print("请检查:")
        print("  1. MCP服务器是否运行")
        print("  2. Dashboard服务是否运行")
        print("  3. 端口是否被占用")

    return all_ok


if __name__ == "__main__":
    exit(0 if check_all() else 1)
