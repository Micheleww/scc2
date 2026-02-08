#!/usr/bin/env python3
"""
导航可达性自检脚本 (Navigation Reachability Self-Check)

验证从总入口到控制面导航区的链接存在且路径有效。
失链则 FAIL (Exit Code: 1)，通过则 PASS (Exit Code: 0)。
"""

import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
# Use ACTIVE version, not DRAFT - ACTIVE is the single source of truth
# Standard: Use lowercase 'arch' directory (aligned with mkdocs.yml)
NAV_DOC = REPO_ROOT / "docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md"

CONTROL_PLANE_NAV_LINKS = [
    {
        "name": "Program Board",
        "path": "docs/arch/program_board__v0.1.0__ACTIVE__20260115.md",
        "description": "任务看板",
    },
    {"name": "今日 Inbox", "path": "docs/REPORT/inbox/2026-01-15.md", "description": "每日收件箱"},
    {
        "name": "Gate 规则说明",
        "path": "docs/spec/qcc_enforcement_spec_v1.0.0.md",
        "description": "门禁规则规范",
    },
    {
        "name": "REPORT 模板入口",
        "path": "docs/templates/template_report.md",
        "description": "报告模板",
    },
]


def check_link_exists(link_info: dict) -> tuple[bool, str]:
    """检查链接指向的文件是否存在"""
    path = REPO_ROOT / link_info["path"]
    if path.exists():
        return True, f"OK: {link_info['path']}"
    else:
        return False, f"BROKEN: {link_info['path']} (指向 {link_info['name']})"


def extract_markdown_links(content: str) -> list[str]:
    """从 markdown 内容中提取所有链接"""
    pattern = r"\[([^\]]+)\]\(([^)]+)\)"
    matches = re.findall(pattern, content)
    return [match[1] for match in matches]


def check_nav_doc_structure() -> tuple[bool, str]:
    """检查导航文档是否存在且结构正确"""
    if not NAV_DOC.exists():
        return False, f"导航文档不存在: {NAV_DOC}"

    content = NAV_DOC.read_text(encoding="utf-8")

    required_sections = [
        "控制面导航区",
        "Program Board",
        "今日 Inbox",
        "Gate 规则说明",
        "REPORT 模板入口",
    ]

    for section in required_sections:
        if section not in content:
            return False, f"导航文档缺少必要章节: {section}"

    return True, "导航文档结构正确"


def run_check() -> bool:
    """运行导航可达性检查"""
    print("=" * 80)
    print("NAVIGATION REACHABILITY SELF-CHECK")
    print("=" * 80)
    print()
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Repo Root: {REPO_ROOT}")
    print(f"Nav Doc: {NAV_DOC}")
    print()

    all_passed = True

    print("[1/2] 检查导航文档结构...")
    passed, msg = check_nav_doc_structure()
    if passed:
        print(f"  [OK] {msg}")
    else:
        print(f"  [FAIL] {msg}")
        all_passed = False
    print()

    print("[2/2] 检查控制面导航链接可达性...")
    broken_links = []
    for link_info in CONTROL_PLANE_NAV_LINKS:
        passed, msg = check_link_exists(link_info)
        if passed:
            print(f"  [OK] {msg}")
        else:
            print(f"  [FAIL] {msg}")
            broken_links.append(msg)
            all_passed = False
    print()

    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total Links Checked: {len(CONTROL_PLANE_NAV_LINKS)}")
    print(f"Passed: {len(CONTROL_PLANE_NAV_LINKS) - len(broken_links)}")
    print(f"Failed: {len(broken_links)}")
    print()

    if broken_links:
        print("BROKEN LINKS:")
        for link in broken_links:
            print(f"  - {link}")
        print()

    return all_passed


def main():
    """主入口"""
    passed = run_check()

    print("=" * 80)
    if passed:
        print("RESULT: ALL CHECKS PASSED")
        print("EXIT_CODE=0")
        print("=" * 80)
        sys.exit(0)
    else:
        print("RESULT: CHECKS FAILED")
        print("EXIT_CODE=1")
        print("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
