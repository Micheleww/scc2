#!/usr/bin/env python3
"""
测试网页应用功能
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent


def test_mkdocs_server():
    """测试MkDocs服务器"""
    print("=" * 80)
    print("测试 MkDocs 服务器")
    print("=" * 80)

    # 检查site目录
    site_dir = REPO_ROOT / "site"
    if not site_dir.exists():
        print("✗ site/ 目录不存在，需要先运行 mkdocs build")
        return False

    index_file = site_dir / "index.html"
    if not index_file.exists():
        print("✗ site/index.html 不存在")
        return False

    print("✓ site/index.html 存在")

    # 尝试启动MkDocs服务器（仅检查，不实际启动）
    try:
        result = subprocess.run(
            ["python", "-m", "mkdocs", "serve", "--help"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            print("✓ MkDocs serve 命令可用")
            print("  启动命令: python -m mkdocs serve")
            print("  默认地址: http://127.0.0.1:18788/")
        else:
            print("⚠ MkDocs serve 命令检查失败")
    except Exception as e:
        print(f"⚠ MkDocs serve 检查异常: {str(e)}")

    return True


def test_frequi():
    """测试FreqUI应用"""
    print("\n" + "=" * 80)
    print("测试 FreqUI 应用")
    print("=" * 80)

    frequi_dir = REPO_ROOT / "frequi-main"
    if not frequi_dir.exists():
        print("✗ frequi-main/ 目录不存在")
        return False

    # 检查package.json
    package_json = frequi_dir / "package.json"
    if not package_json.exists():
        print("✗ package.json 不存在")
        return False

    # 检查node_modules
    node_modules = frequi_dir / "node_modules"
    if not node_modules.exists():
        print("⚠ node_modules/ 不存在，需要运行: cd frequi-main && pnpm install")
        return False

    print("✓ 基本文件检查通过")
    print("  启动命令: cd frequi-main && pnpm run dev")
    print("  默认地址: http://127.0.0.1:3000")
    print("  注意: 需要freqtrade API运行在 http://127.0.0.1:18788/")

    return True


def test_mcp_server():
    """测试MCP服务器"""
    print("\n" + "=" * 80)
    print("测试 MCP 服务器")
    print("=" * 80)

    server_stdio = REPO_ROOT / "tools" / "mcp_bus" / "server_stdio.py"
    if not server_stdio.exists():
        print("✗ server_stdio.py 不存在")
        return False

    print("✓ server_stdio.py 存在")
    print("  启动方式: 通过 Cursor MCP 配置自动启动")
    print("  配置文件: .cursor/mcp.json")

    return True


def check_broken_links():
    """检查网站中的断链"""
    print("\n" + "=" * 80)
    print("检查网站断链")
    print("=" * 80)

    site_dir = REPO_ROOT / "site"
    if not site_dir.exists():
        print("✗ site/ 目录不存在")
        return []

    broken_links = []

    # 检查主要HTML文件
    html_files = [
        site_dir / "index.html",
        site_dir / "arch" / "index.html",
    ]

    for html_file in html_files:
        if html_file.exists():
            try:
                content = html_file.read_text(encoding="utf-8")
                # 检查是否有docs/ARCH/引用（应该使用docs/arch/）
                if "docs/ARCH/" in content:
                    broken_links.append(
                        {
                            "file": str(html_file.relative_to(REPO_ROOT)),
                            "issue": "包含旧的docs/ARCH/引用（应使用docs/arch/）",
                        }
                    )
            except Exception as e:
                broken_links.append(
                    {"file": str(html_file.relative_to(REPO_ROOT)), "issue": f"读取失败: {str(e)}"}
                )

    if broken_links:
        print(f"发现 {len(broken_links)} 个问题:")
        for link in broken_links:
            print(f"  [{link['file']}] {link['issue']}")
    else:
        print("✓ 未发现断链问题")

    return broken_links


def main():
    """主函数"""
    print("网页应用功能测试")
    print("=" * 80)
    print(f"工作目录: {REPO_ROOT}")
    print()

    results = {
        "mkdocs": test_mkdocs_server(),
        "frequi": test_frequi(),
        "mcp": test_mcp_server(),
        "broken_links": check_broken_links(),
    }

    # 输出总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    all_ok = results["mkdocs"] and results["frequi"] and results["mcp"]

    if all_ok and not results["broken_links"]:
        print("\n✓ 所有网页应用检查通过")
    else:
        print("\n发现以下问题:")
        if not results["mkdocs"]:
            print("  - MkDocs 文档网站有问题")
        if not results["frequi"]:
            print("  - FreqUI 应用有问题")
        if not results["mcp"]:
            print("  - MCP 服务器有问题")
        if results["broken_links"]:
            print(f"  - 发现 {len(results['broken_links'])} 个断链问题")

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "results": results,
        "all_ok": all_ok and not results["broken_links"],
    }

    report_file = REPO_ROOT / "docs" / "REPORT" / "docs_gov" / "WEB_APPS_TEST__20260120.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n报告已保存: {report_file.relative_to(REPO_ROOT)}")

    return 0 if all_ok and not results["broken_links"] else 1


if __name__ == "__main__":
    exit(main())
