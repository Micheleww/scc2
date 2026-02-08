#!/usr/bin/env python3
"""
批量修复docs/ARCH/引用为docs/arch/
"""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def fix_file(file_path: Path) -> int:
    """修复单个文件中的docs/ARCH/引用"""
    try:
        content = file_path.read_text(encoding="utf-8")
        original_content = content

        # 替换docs/ARCH/为docs/arch/（但保留docs/ARCH/ops等特殊情况）
        # 只替换docs/ARCH/开头的路径，不替换docs/ARCH/ops等
        content = re.sub(r"docs/ARCH/(?!ops/)", "docs/arch/", content)
        content = re.sub(r"docs/ARCH/ops/", "docs/arch/ops/", content)

        if content != original_content:
            file_path.write_text(content, encoding="utf-8")
            count = original_content.count("docs/ARCH/") - content.count("docs/ARCH/")
            return count
        return 0
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return 0


def main():
    """主函数"""
    print("=" * 80)
    print("批量修复docs/ARCH/引用")
    print("=" * 80)

    # 扫描所有markdown文件
    md_files = list(DOCS_DIR.rglob("*.md"))

    fixed_count = 0
    total_replacements = 0

    for md_file in md_files:
        # 跳过某些目录
        if any(skip in str(md_file) for skip in ["_backup", "legacy", ".git"]):
            continue

        replacements = fix_file(md_file)
        if replacements > 0:
            fixed_count += 1
            total_replacements += replacements
            rel_path = md_file.relative_to(REPO_ROOT)
            print(f"[{fixed_count}] {rel_path}: {replacements} replacements")

    print("\n" + "=" * 80)
    print(f"总计修复: {fixed_count} 个文件，{total_replacements} 处引用")

    # 重新构建MkDocs
    print("\n重新构建MkDocs...")
    import subprocess

    result = subprocess.run(
        ["python", "-m", "mkdocs", "build", "--clean"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode == 0:
        print("✓ MkDocs构建成功")
    else:
        print("✗ MkDocs构建失败")
        print(result.stderr[-300:] if result.stderr else result.stdout[-300:])

    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    exit(main())
