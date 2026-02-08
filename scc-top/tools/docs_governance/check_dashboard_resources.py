#!/usr/bin/env python3
"""
检查Dashboard资源加载问题
"""

import re

import requests


def check_dashboard():
    """检查Dashboard资源"""
    print("检查Dashboard资源加载...")
    print()

    # 检查直接访问
    print("1. 直接访问Dashboard (8051):")
    try:
        r = requests.get("http://127.0.0.1:8051", timeout=5)
        print(f"   Status: {r.status_code}")
        print(f"   Content-Length: {len(r.content)}")

        # 查找资源路径
        content = r.text
        js_files = re.findall(r'src=["\']([^"\']*\.js[^"\']*)["\']', content)
        css_files = re.findall(r'href=["\']([^"\']*\.css[^"\']*)["\']', content)
        dash_files = re.findall(r'["\'](_dash-[^"\']*)["\']', content)

        print(f"   JS文件数: {len(js_files)}")
        print(f"   CSS文件数: {len(css_files)}")
        print(f"   Dash端点: {len(dash_files)}")

        if js_files:
            print(f"   示例JS: {js_files[0]}")
        if dash_files:
            print(f"   示例Dash端点: {dash_files[0]}")
    except Exception as e:
        print(f"   错误: {e}")

    print()

    # 检查代理访问
    print("2. 通过代理访问Dashboard (8000/dashboard):")
    try:
        r = requests.get("http://127.0.0.1:18788/dashboard", timeout=5)
        print(f"   Status: {r.status_code}")
        print(f"   Content-Length: {len(r.content)}")

        content = r.text
        js_files = re.findall(r'src=["\']([^"\']*\.js[^"\']*)["\']', content)
        css_files = re.findall(r'href=["\']([^"\']*\.css[^"\']*)["\']', content)
        dash_files = re.findall(r'["\'](_dash-[^"\']*)["\']', content)

        print(f"   JS文件数: {len(js_files)}")
        print(f"   CSS文件数: {len(css_files)}")
        print(f"   Dash端点: {len(dash_files)}")

        if js_files:
            print(f"   示例JS: {js_files[0]}")
        if dash_files:
            print(f"   示例Dash端点: {dash_files[0]}")
    except Exception as e:
        print(f"   错误: {e}")

    print()

    # 检查关键资源
    print("3. 检查关键资源:")
    resources = [
        ("/_dash-layout", "http://127.0.0.1:8051/_dash-layout"),
        ("/_dash-layout", "http://127.0.0.1:18788/dashboard/_dash-layout"),
        ("/_dash-dependencies", "http://127.0.0.1:8051/_dash-dependencies"),
        ("/_dash-dependencies", "http://127.0.0.1:18788/dashboard/_dash-dependencies"),
    ]

    for name, url in resources:
        try:
            r = requests.get(url, timeout=3)
            status = "✅" if r.status_code == 200 else "❌"
            print(f"   {status} {name}: {r.status_code} ({len(r.content)} bytes)")
        except Exception as e:
            print(f"   ❌ {name}: {e}")


if __name__ == "__main__":
    check_dashboard()
