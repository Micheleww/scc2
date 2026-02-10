#!/usr/bin/env python3
"""
查找所有编码问题的文件
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def check_file(file_path: Path):
    """检查文件编码"""
    try:
        file_path.read_text(encoding="utf-8")
        return None
    except UnicodeDecodeError as e:
        return str(e)


def main():
    """主函数"""
    print("查找编码问题文件...")
    print("=" * 80)

    problem_files = []

    # 扫描所有markdown文件
    for md_file in DOCS_DIR.rglob("*.md"):
        error = check_file(md_file)
        if error:
            rel_path = md_file.relative_to(REPO_ROOT)
            problem_files.append((rel_path, error))
            print(f"[{len(problem_files)}] {rel_path}")
            print(f"      Error: {error[:100]}")

    print("\n" + "=" * 80)
    print(f"总计发现 {len(problem_files)} 个编码问题文件")

    # 保存列表
    report_file = REPO_ROOT / "docs" / "REPORT" / "docs_gov" / "ENCODING_ISSUES__20260120.txt"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        for rel_path, error in problem_files:
            f.write(f"{rel_path}\n")
            f.write(f"  Error: {error}\n\n")

    print(f"\n问题列表已保存: {report_file.relative_to(REPO_ROOT)}")

    return len(problem_files)


if __name__ == "__main__":
    exit(main())
