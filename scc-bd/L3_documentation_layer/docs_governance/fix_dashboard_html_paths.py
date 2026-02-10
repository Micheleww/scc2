#!/usr/bin/env python3
"""
修复Dashboard HTML中的资源路径，将绝对路径改为相对路径
"""

import re
import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fix_dashboard_html_paths():
    """修复Dashboard HTML中的资源路径"""
    print("=" * 80)
    print("修复Dashboard HTML资源路径")
    print("=" * 80)
    print()

    # 获取Dashboard HTML
    try:
        r = requests.get("http://127.0.0.1:8051", timeout=5)
        if r.status_code != 200:
            print(f"[FAIL] 无法获取Dashboard HTML: {r.status_code}")
            return False

        html_content = r.text
        print(f"[OK] 获取Dashboard HTML: {len(html_content)} bytes")

        # 查找需要修复的路径
        # Dashboard的资源路径通常是绝对路径，需要改为相对路径或通过代理访问

        # 检查是否有绝对路径的资源
        absolute_paths = re.findall(r'src=["\'](http://[^"\']+)["\']', html_content)
        dash_paths = re.findall(r'src=["\'](/_dash[^"\']*)["\']', html_content)
        component_paths = re.findall(
            r'src=["\'](/_dash-component-suites[^"\']*)["\']', html_content
        )

        print(f"[INFO] 绝对路径资源: {len(absolute_paths)}")
        print(f"[INFO] _dash路径: {len(dash_paths)}")
        print(f"[INFO] component-suites路径: {len(component_paths)}")

        if absolute_paths:
            print("[WARN] 发现绝对路径资源，可能需要修复")
            for path in absolute_paths[:3]:
                print(f"  示例: {path}")

        # 检查代理是否正确返回HTML
        proxy_r = requests.get("http://127.0.0.1:18788/dashboard", timeout=5)
        if proxy_r.status_code == 200:
            proxy_html = proxy_r.text
            print(f"[OK] 代理返回HTML: {len(proxy_html)} bytes")

            # 检查代理HTML中的资源路径
            proxy_dash_paths = re.findall(r'src=["\'](/_dash[^"\']*)["\']', proxy_html)
            proxy_component_paths = re.findall(
                r'src=["\'](/_dash-component-suites[^"\']*)["\']', proxy_html
            )

            print(f"[INFO] 代理HTML中的_dash路径: {len(proxy_dash_paths)}")
            print(f"[INFO] 代理HTML中的component-suites路径: {len(proxy_component_paths)}")

            # 检查资源是否可以访问
            print()
            print("检查资源可访问性:")
            test_paths = [
                "/_dash-layout",
                "/_dash-dependencies",
            ]
            if proxy_component_paths:
                test_paths.append(proxy_component_paths[0])

            all_ok = True
            for path in test_paths:
                try:
                    test_r = requests.get(f"http://127.0.0.1:18788/{path}", timeout=3)
                    status = "[OK]" if test_r.status_code == 200 else "[FAIL]"
                    print(f"   {status} {path}: {test_r.status_code}")
                    if test_r.status_code != 200:
                        all_ok = False
                except Exception as e:
                    print(f"   [FAIL] {path}: {e}")
                    all_ok = False

            return all_ok
        else:
            print(f"[FAIL] 代理无法返回HTML: {proxy_r.status_code}")
            return False

    except Exception as e:
        print(f"[FAIL] 错误: {e}")
        return False


if __name__ == "__main__":
    exit(0 if fix_dashboard_html_paths() else 1)
