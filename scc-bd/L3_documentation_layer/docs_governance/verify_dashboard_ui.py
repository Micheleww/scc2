#!/usr/bin/env python3
"""
验证Dashboard UI是否正常加载
"""

import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def check_dashboard_ui():
    """检查Dashboard UI资源"""
    print("=" * 80)
    print("验证Dashboard UI资源加载")
    print("=" * 80)
    print()

    # 1. 检查Dashboard HTML
    print("1. 检查Dashboard HTML页面:")
    try:
        r = requests.get("http://127.0.0.1:18788/dashboard", timeout=5)
        if r.status_code == 200:
            print(f"   [OK] HTML页面: {r.status_code} ({len(r.content)} bytes)")

            # 检查关键内容
            content = r.text
            has_react = "react" in content.lower()[:2000]
            has_dash = "_dash" in content[:2000]
            has_layout = "_dash-layout" in content[:2000]

            print(f"   [INFO] 包含React: {has_react}")
            print(f"   [INFO] 包含_dash: {has_dash}")
            print(f"   [INFO] 包含_dash-layout: {has_layout}")
        else:
            print(f"   [FAIL] HTML页面: {r.status_code}")
            return False
    except Exception as e:
        print(f"   [FAIL] HTML页面: {e}")
        return False

    print()

    # 2. 检查关键资源
    print("2. 检查关键资源:")
    resources = [
        ("/_dash-layout", "http://127.0.0.1:18788/_dash-layout"),
        ("/_dash-dependencies", "http://127.0.0.1:18788/_dash-dependencies"),
        (
            "/_dash-component-suites/...",
            "http://127.0.0.1:18788/_dash-component-suites/dash/deps/polyfill@7.v3_3_0m1767941296.12.1.min.js",
        ),
    ]

    all_ok = True
    for name, url in resources:
        try:
            r = requests.get(url, timeout=3)
            if r.status_code == 200:
                print(f"   [OK] {name}: {r.status_code} ({len(r.content)} bytes)")
            else:
                print(f"   [FAIL] {name}: {r.status_code}")
                all_ok = False
        except Exception as e:
            print(f"   [FAIL] {name}: {e}")
            all_ok = False

    print()

    # 3. 检查iframe配置
    print("3. 检查iframe配置:")
    try:
        dashboard_html_path = r"d:\quantsys\tools\mcp_bus\web_viewer\dashboard.html"
        with open(dashboard_html_path, encoding="utf-8") as f:
            content = f.read()

        # 检查Dashboard iframe
        if 'src="/dashboard"' in content:
            print("   [OK] Dashboard iframe使用代理路由: /dashboard")
        elif 'src="http://127.0.0.1:8051"' in content:
            print("   [WARN] Dashboard iframe使用直接端口，建议改为代理路由")
        else:
            print("   [WARN] 无法找到Dashboard iframe配置")

        # 检查是否有_dash资源引用
        if "_dash-component-suites" in content:
            print("   [INFO] HTML中包含_dash-component-suites引用")
    except Exception as e:
        print(f"   [FAIL] 检查iframe配置: {e}")

    print()
    print("=" * 80)
    if all_ok:
        print("[OK] Dashboard UI资源检查通过")
        print()
        print("访问地址:")
        print("  - 统一管理平台: http://127.0.0.1:18788/")
        print("  - Dashboard: http://127.0.0.1:18788/dashboard")
    else:
        print("[FAIL] Dashboard UI资源检查失败")
        print()
        print("问题:")
        print("  - 某些资源无法通过代理访问")
        print("  - 请检查MCP服务器的代理路由配置")

    return all_ok


if __name__ == "__main__":
    exit(0 if check_dashboard_ui() else 1)
