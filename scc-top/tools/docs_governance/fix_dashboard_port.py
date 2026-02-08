#!/usr/bin/env python3
"""
修复Dashboard端口配置问题
统一管理平台应该连接到8051端口，而不是8000端口
"""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent


def fix_html_files():
    """修复HTML文件中的端口配置"""
    fixed_count = 0

    # 查找所有HTML文件
    html_files = []
    for pattern in ["**/*.html", "**/*.htm"]:
        html_files.extend(REPO_ROOT.glob(pattern))

    for html_file in html_files:
        # 跳过某些目录
        if any(
            skip in str(html_file) for skip in ["node_modules", "_backup", "site", ".git", "dist"]
        ):
            continue

        try:
            content = html_file.read_text(encoding="utf-8", errors="ignore")
            original_content = content

            # 修复iframe中的端口配置
            # 查找类似 iframe src="http://127.0.0.1:18788/" 或类似模式
            # 但只修复Dashboard相关的iframe
            if "dashboard" in content.lower() or "量化控制中心" in content:
                # 替换 Dashboard iframe 中的8000端口为8051
                content = re.sub(
                    r'(iframe[^>]*src=["\']http://127\.0\.0\.1:8000[^"\']*["\'])',
                    lambda m: m.group(1).replace(":8000", ":8051"),
                    content,
                    flags=re.IGNORECASE,
                )
                # 替换其他可能的端口引用
                content = re.sub(
                    r'(http://127\.0\.0\.1:8000)(?=[^"\']*dashboard)',
                    "http://127.0.0.1:8051",
                    content,
                    flags=re.IGNORECASE,
                )

            if content != original_content:
                html_file.write_text(content, encoding="utf-8")
                fixed_count += 1
                rel_path = html_file.relative_to(REPO_ROOT)
                print(f"[修复] {rel_path}")
        except Exception as e:
            print(f"Error fixing {html_file}: {e}")

    return fixed_count


def fix_js_files():
    """修复JavaScript/Vue文件中的端口配置"""
    fixed_count = 0

    js_files = []
    for pattern in ["**/*.js", "**/*.ts", "**/*.vue"]:
        js_files.extend(REPO_ROOT.glob(pattern))

    for js_file in js_files:
        # 跳过某些目录
        if any(
            skip in str(js_file) for skip in ["node_modules", "_backup", "site", ".git", "dist"]
        ):
            continue

        try:
            content = js_file.read_text(encoding="utf-8", errors="ignore")
            original_content = content

            # 修复Dashboard相关的端口配置
            if (
                "dashboard" in content.lower()
                or "量化控制中心" in content
                or "统一管理平台" in content
            ):
                # 替换8000端口为8051（但只在Dashboard相关上下文中）
                content = re.sub(
                    r'(http://127\.0\.0\.1:8000)(?=[^"\']*dashboard)',
                    "http://127.0.0.1:8051",
                    content,
                    flags=re.IGNORECASE,
                )
                # 替换变量中的端口配置
                content = re.sub(
                    r"(dashboard.*?port.*?[:=]\s*)(8000)",
                    r"\g<1>8051",
                    content,
                    flags=re.IGNORECASE,
                )

            if content != original_content:
                js_file.write_text(content, encoding="utf-8")
                fixed_count += 1
                rel_path = js_file.relative_to(REPO_ROOT)
                print(f"[修复] {rel_path}")
        except Exception as e:
            print(f"Error fixing {js_file}: {e}")

    return fixed_count


def main():
    """主函数"""
    print("=" * 80)
    print("修复Dashboard端口配置")
    print("=" * 80)
    print("查找并修复统一管理平台中Dashboard的端口配置（8000 -> 8051）")
    print()

    html_count = fix_html_files()
    js_count = fix_js_files()

    print()
    print("=" * 80)
    print(f"总计修复: {html_count} 个HTML文件，{js_count} 个JS/TS/Vue文件")
    print()
    print("注意：如果统一管理平台是独立应用，请手动检查并更新配置")
    print("Dashboard服务运行在: http://127.0.0.1:8051")
    print("MkDocs服务运行在: http://127.0.0.1:18788/")

    return 0


if __name__ == "__main__":
    exit(main())
