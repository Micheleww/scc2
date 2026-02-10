#!/usr/bin/env python3
"""
检查网页应用状态和问题
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent


def check_mkdocs():
    """检查MkDocs文档网站"""
    print("=" * 80)
    print("检查 MkDocs 文档网站")
    print("=" * 80)

    issues = []

    # 检查mkdocs.yml
    mkdocs_yml = REPO_ROOT / "mkdocs.yml"
    if not mkdocs_yml.exists():
        issues.append("mkdocs.yml 不存在")
    else:
        print("✓ mkdocs.yml 存在")

    # 检查site目录
    site_dir = REPO_ROOT / "site"
    if not site_dir.exists():
        issues.append("site/ 目录不存在（需要运行 mkdocs build）")
    else:
        index_file = site_dir / "index.html"
        if index_file.exists():
            print("✓ site/index.html 存在")
        else:
            issues.append("site/index.html 不存在")

    # 检查mkdocs是否安装
    try:
        result = subprocess.run(
            ["python", "-m", "mkdocs", "--version"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            print(f"✓ MkDocs 已安装: {result.stdout.strip()}")
        else:
            issues.append(f"MkDocs 检查失败: {result.stderr}")
    except Exception as e:
        issues.append(f"MkDocs 检查异常: {str(e)}")

    # 检查导航配置
    if mkdocs_yml.exists():
        try:
            import yaml

            with open(mkdocs_yml, encoding="utf-8") as f:
                config = yaml.safe_load(f)

            nav = config.get("nav", [])
            if not nav:
                issues.append("mkdocs.yml 中 nav 配置为空")
            else:
                print(f"✓ 导航配置存在，包含 {len(nav)} 个条目")

                # 检查导航路径是否存在
                for item in nav:
                    if isinstance(item, dict):
                        for key, value in item.items():
                            if isinstance(value, str) and value.endswith(".md"):
                                doc_path = REPO_ROOT / "docs" / value
                                if not doc_path.exists():
                                    issues.append(f"导航文档不存在: {value}")
        except Exception as e:
            issues.append(f"读取 mkdocs.yml 失败: {str(e)}")

    return issues


def check_frequi():
    """检查FreqUI应用"""
    print("\n" + "=" * 80)
    print("检查 FreqUI 应用")
    print("=" * 80)

    issues = []
    frequi_dir = REPO_ROOT / "frequi-main"

    if not frequi_dir.exists():
        issues.append("frequi-main/ 目录不存在")
        return issues

    print("✓ frequi-main/ 目录存在")

    # 检查package.json
    package_json = frequi_dir / "package.json"
    if not package_json.exists():
        issues.append("frequi-main/package.json 不存在")
    else:
        print("✓ package.json 存在")

    # 检查node_modules
    node_modules = frequi_dir / "node_modules"
    if not node_modules.exists():
        issues.append("frequi-main/node_modules/ 不存在（需要运行 npm install 或 pnpm install）")
    else:
        print("✓ node_modules/ 存在")

    # 检查vite.config.ts
    vite_config = frequi_dir / "vite.config.ts"
    if not vite_config.exists():
        issues.append("vite.config.ts 不存在")
    else:
        print("✓ vite.config.ts 存在")

    # 检查src目录
    src_dir = frequi_dir / "src"
    if not src_dir.exists():
        issues.append("frequi-main/src/ 目录不存在")
    else:
        main_ts = src_dir / "main.ts"
        if main_ts.exists():
            print("✓ src/main.ts 存在")
        else:
            issues.append("src/main.ts 不存在")

    # 检查dist目录（构建产物）
    dist_dir = frequi_dir / "dist"
    if not dist_dir.exists():
        print("⚠ dist/ 目录不存在（需要运行 npm run build）")
    else:
        print("✓ dist/ 目录存在")

    return issues


def check_mcp_server():
    """检查MCP服务器"""
    print("\n" + "=" * 80)
    print("检查 MCP 服务器")
    print("=" * 80)

    issues = []

    # 检查server_stdio.py
    server_stdio = REPO_ROOT / "tools" / "mcp_bus" / "server_stdio.py"
    if not server_stdio.exists():
        issues.append("tools/mcp_bus/server_stdio.py 不存在")
    else:
        print("✓ server_stdio.py 存在")

    # 检查server/main.py
    server_main = REPO_ROOT / "tools" / "mcp_bus" / "server" / "main.py"
    if not server_main.exists():
        issues.append("tools/mcp_bus/server/main.py 不存在")
    else:
        print("✓ server/main.py 存在")

    return issues


def main():
    """主函数"""
    print("网页应用状态检查")
    print("=" * 80)
    print(f"工作目录: {REPO_ROOT}")
    print()

    all_issues = []

    # 检查各个应用
    mkdocs_issues = check_mkdocs()
    all_issues.extend([("MkDocs", issue) for issue in mkdocs_issues])

    frequi_issues = check_frequi()
    all_issues.extend([("FreqUI", issue) for issue in frequi_issues])

    mcp_issues = check_mcp_server()
    all_issues.extend([("MCP Server", issue) for issue in mcp_issues])

    # 输出总结
    print("\n" + "=" * 80)
    print("检查总结")
    print("=" * 80)

    if all_issues:
        print(f"\n发现 {len(all_issues)} 个问题:\n")
        for app, issue in all_issues:
            print(f"  [{app}] {issue}")
    else:
        print("\n✓ 所有检查通过，未发现问题")

    # 保存报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "issues": [{"app": app, "issue": issue} for app, issue in all_issues],
        "total_issues": len(all_issues),
    }

    report_file = REPO_ROOT / "docs" / "REPORT" / "docs_gov" / "WEB_APPS_CHECK__20260120.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n报告已保存: {report_file.relative_to(REPO_ROOT)}")

    return len(all_issues)


if __name__ == "__main__":
    exit(main())
