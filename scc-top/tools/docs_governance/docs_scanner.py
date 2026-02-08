#!/usr/bin/env python3
"""
文档治理扫描脚本 (Docs Governance Scanner)

检查规则：
1. 法源不复制：确保文档中不包含law/目录下的法源正文
2. 相对路径检查：确保文档中的链接使用相对路径
3. 构建产物检查：确保mkdocs构建不会复制法源文件
"""

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"
LAW_DIR = REPO_ROOT / "law"
SITE_DIR = REPO_ROOT / "site"

# 定义法源文件列表
LAW_FILES = ["QCC-A.v1.1.md", "QCC-E.v1.1.md", "QCC-S.v1.1.md", "QUANT宪法典.txt"]

# 法源文件内容缓存
law_contents: set[str] = set()


def load_law_contents():
    """加载法源文件内容，用于后续检查"""
    global law_contents
    for law_file in LAW_FILES:
        law_path = LAW_DIR / law_file
        if law_path.exists():
            content = law_path.read_text(encoding="utf-8")
            # 提取关键段落（超过100字符的连续文本）
            paragraphs = [p.strip() for p in content.split("\n\n") if len(p.strip()) > 100]
            law_contents.update(paragraphs)


def check_law_copy_in_docs() -> tuple[bool, list[str]]:
    """检查文档中是否包含法源正文复制"""
    print("[1/3] 检查法源不复制规则...")

    violations = []
    all_passed = True

    # 遍历所有文档文件
    for doc_path in DOCS_DIR.rglob("*.md"):
        if doc_path.is_file():
            content = doc_path.read_text(encoding="utf-8")

            # 检查是否包含法源段落
            for law_paragraph in law_contents:
                if law_paragraph in content:
                    violations.append(f"ERROR: {doc_path} 包含法源正文复制，来自法源文件")
                    all_passed = False
                    break

            # 检查是否直接链接到law/目录
            if re.search(r"\[.*\]\((\.\./)*law/", content):
                violations.append(f"ERROR: {doc_path} 直接链接到law/目录，应使用引用而非复制")
                all_passed = False

    return all_passed, violations


def check_relative_paths() -> tuple[bool, list[str]]:
    """检查文档中的链接是否使用相对路径"""
    print("[2/3] 检查相对路径规则...")

    violations = []
    all_passed = True

    for doc_path in DOCS_DIR.rglob("*.md"):
        if doc_path.is_file():
            content = doc_path.read_text(encoding="utf-8")

            # 提取所有链接
            links = re.findall(r"\[.*\]\(([^)]+)\)", content)

            for link in links:
                # 跳过外部链接
                if link.startswith("http://") or link.startswith("https://"):
                    continue

                # 跳过锚点链接
                if link.startswith("#"):
                    continue

                # 检查是否为绝对路径（不包含驱动器号的绝对路径）
                if link.startswith("/"):
                    violations.append(f"ERROR: {doc_path} 包含绝对路径链接: {link}")
                    all_passed = False

                # 检查链接是否指向实际存在的文件
                if not link.startswith("#") and not link.startswith("http"):
                    target_path = doc_path.parent / link
                    # 处理markdown链接省略.md扩展名的情况
                    if not target_path.exists() and not link.endswith(".md"):
                        target_path = target_path.with_suffix(".md")
                    if not target_path.exists() and not link.endswith("/"):
                        target_path = target_path / "index.md"
                    if not target_path.exists():
                        violations.append(f"WARNING: {doc_path} 包含无效链接: {link}")

    return all_passed, violations


def check_site_law_copy() -> tuple[bool, list[str]]:
    """检查构建产物中是否包含法源复制"""
    print("[3/3] 检查构建产物中的法源复制...")

    violations = []
    all_passed = True

    # 检查site目录是否存在
    if not SITE_DIR.exists():
        violations.append(f"WARNING: 构建产物目录不存在: {SITE_DIR}")
        return all_passed, violations

    # 遍历site目录下的所有HTML文件
    for html_path in SITE_DIR.rglob("*.html"):
        if html_path.is_file():
            content = html_path.read_text(encoding="utf-8")

            # 检查是否包含法源段落
            for law_paragraph in law_contents:
                # 检查简化版（去除多余空格和换行）
                simplified_content = re.sub(r"\s+", " ", content)
                simplified_law = re.sub(r"\s+", " ", law_paragraph)
                if len(simplified_law) > 100 and simplified_law in simplified_content:
                    violations.append(f"ERROR: {html_path} 包含法源正文复制")
                    all_passed = False
                    break

    return all_passed, violations


def run_scan() -> bool:
    """运行所有文档治理扫描规则"""
    print("=" * 80)
    print("DOCS GOVERNANCE SCANNER")
    print("=" * 80)
    print()

    # 加载法源内容
    load_law_contents()

    all_passed = True
    all_violations = []

    # 运行所有检查
    checks = [check_law_copy_in_docs, check_relative_paths, check_site_law_copy]

    for check_func in checks:
        passed, violations = check_func()
        all_passed &= passed
        all_violations.extend(violations)
        print()

    # 输出结果
    print("=" * 80)
    print("SCAN RESULTS")
    print("=" * 80)

    if all_violations:
        print(f"发现 {len(all_violations)} 个违规:")
        for violation in all_violations:
            print(f"  - {violation}")
    else:
        print("✓ 所有检查通过！")

    print()
    print("=" * 80)
    if all_passed:
        print("RESULT: PASS")
        print("EXIT_CODE=0")
    else:
        print("RESULT: FAIL")
        print("EXIT_CODE=1")
    print("=" * 80)

    return all_passed


def main():
    """主入口"""
    passed = run_scan()
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
