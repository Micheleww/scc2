#!/usr/bin/env python3
"""
修复文档编码问题
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"


def fix_file_encoding(file_path: Path) -> bool:
    """修复单个文件的编码问题"""
    try:
        # 尝试读取文件
        try:
            content = file_path.read_text(encoding="utf-8")
            # 如果成功，检查是否有BOM
            if content.startswith("\ufeff"):
                content = content[1:]
                file_path.write_text(content, encoding="utf-8")
                return True
            return False
        except UnicodeDecodeError:
            # UTF-8失败，尝试GBK
            try:
                content = file_path.read_text(encoding="gbk")
                file_path.write_text(content, encoding="utf-8")
                return True
            except:
                # GBK也失败，尝试latin-1然后转换
                try:
                    content = file_path.read_bytes().decode("latin-1")
                    # 尝试转换为UTF-8
                    file_path.write_text(content, encoding="utf-8")
                    return True
                except:
                    return False
    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False


def main():
    """主函数"""
    print("=" * 80)
    print("修复文档编码问题")
    print("=" * 80)

    # 已知有问题的文件
    problem_files = [
        DOCS_DIR
        / "REPORT"
        / "ci"
        / "REPORT__TOKEN-ROTATION-REPLAY-PROTECT-v0.1__20260115__20260115.md",
        DOCS_DIR / "taskhub_system_manifest.md",
        DOCS_DIR / "taskhub_system_overview.md",
    ]

    fixed_count = 0
    for file_path in problem_files:
        if file_path.exists():
            print(f"修复: {file_path.relative_to(REPO_ROOT)}")
            if fix_file_encoding(file_path):
                fixed_count += 1
                print("  ✓ 已修复")
            else:
                print("  ✗ 修复失败")
        else:
            print(f"跳过（不存在）: {file_path.relative_to(REPO_ROOT)}")

    print(f"\n总计修复: {fixed_count} 个文件")

    # 测试MkDocs构建
    print("\n测试MkDocs构建...")
    import subprocess

    result = subprocess.run(
        ["python", "-m", "mkdocs", "build"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode == 0:
        print("✓ MkDocs构建成功")
    else:
        print("✗ MkDocs构建失败")
        print(result.stderr[-500:] if result.stderr else result.stdout[-500:])

    return 0 if result.returncode == 0 else 1


if __name__ == "__main__":
    exit(main())
