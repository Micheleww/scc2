#!/usr/bin/env python3
"""
检查代码中是否有在根目录创建文件的习惯
扫描Python代码，查找可能违反根目录治理规范的代码模式
"""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent

# 允许的文件名（符合规范）
ALLOWED_ROOT_FILES = {
    "README.md",
    "package.json",
    "package-lock.json",
    "requirements.txt",
    "requirements-docs.txt",
    "mkdocs.yml",
    "justfile",
    "pyproject.toml",
    "Dockerfile",
    "docker-compose.yml",
    "Makefile",
    ".env.example",
    ".gitignore",
    ".pre-commit-config.yaml",
}

# 可疑的文件操作模式
SUSPICIOUS_PATTERNS = [
    # 直接打开根目录文件（非相对路径）
    (r"open\(['\"]([^/].*\.(md|txt|json|log|py|yaml|yml))['\"]", "直接打开根目录文件"),
    # Path 创建根目录文件
    (r"Path\(['\"]([^/].*\.(md|txt|json|log|py|yaml|yml))['\"]", "Path创建根目录文件"),
    # 使用当前目录创建文件
    (r"(Path\(['\"]\.\/[^/]|Path\(['\"]\.['\"])/.*\.(md|txt|json|log|py)", "使用./创建文件"),
    # os.path.join(os.getcwd(), ...) 创建文件
    (r"os\.path\.join\(os\.getcwd\(\),.*\.(md|txt|json|log|py)", "使用getcwd创建文件"),
    # 写入根目录
    (r"\.write\(.*['\"]([^/].*\.(md|txt|json|log))['\"]", "写入根目录文件"),
]

# 正确的模式（应该使用的）
CORRECT_PATTERNS = [
    r"docs/",
    r"logs/",
    r"configs/",
    r"tools/",
    r"scripts/",
    r"taskhub/",
    r"reports/",
    r"_staging/",
]


def check_file_for_violations(file_path: Path) -> list[dict]:
    """检查单个文件中的违规模式"""
    violations = []

    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")

        for line_num, line in enumerate(lines, 1):
            # 跳过注释和字符串
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue

            # 检查可疑模式
            for pattern, description in SUSPICIOUS_PATTERNS:
                matches = re.finditer(pattern, line, re.IGNORECASE)
                for match in matches:
                    # 检查是否匹配允许的文件
                    matched_file = match.group(1) if match.groups() else match.group(0)
                    if matched_file and matched_file not in ALLOWED_ROOT_FILES:
                        # 检查是否使用了正确的目录
                        is_correct = any(
                            re.search(correct, line, re.IGNORECASE) for correct in CORRECT_PATTERNS
                        )

                        if not is_correct:
                            violations.append(
                                {
                                    "file": str(file_path.relative_to(REPO_ROOT)),
                                    "line": line_num,
                                    "code": line.strip(),
                                    "pattern": description,
                                    "matched": matched_file,
                                }
                            )

    except Exception:
        # 忽略无法读取的文件（二进制文件等）
        pass

    return violations


def check_python_files() -> list[dict]:
    """检查所有Python文件"""
    violations = []

    # 扫描Python文件
    python_files = list(REPO_ROOT.rglob("*.py"))

    # 排除一些目录（第三方库、备份、缓存等）
    exclude_dirs = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        "venv",
        ".venv",
        "node_modules",
        "site",
        "build",
        "dist",
        "_staging",
        ".cursor",
        "_backup",
        "corefiles",
        "legacy",
        "ai_collaboration",  # 历史代码，暂时排除
        "experiments",  # 实验代码
    }

    for py_file in python_files:
        # 跳过排除的目录
        if any(exclude in str(py_file) for exclude in exclude_dirs):
            continue

        file_violations = check_file_for_violations(py_file)
        violations.extend(file_violations)

    return violations


def main():
    """主函数"""
    print("=" * 80)
    print("根目录违规检查工具")
    print("=" * 80)
    print(f"工作目录: {REPO_ROOT}")
    print()

    violations = check_python_files()

    if violations:
        print(f"\n发现 {len(violations)} 个可能的违规:")
        print("-" * 80)

        # 按文件分组
        by_file = {}
        for v in violations:
            file = v["file"]
            if file not in by_file:
                by_file[file] = []
            by_file[file].append(v)

        for file, file_violations in sorted(by_file.items()):
            print(f"\n{file}:")
            for v in file_violations:
                print(f"  行 {v['line']}: {v['pattern']}")
                print(f"    代码: {v['code']}")
                print(f"    匹配: {v['matched']}")
                print()
    else:
        print("\n✓ 未发现明显的根目录违规模式")

    print("=" * 80)
    print(f"总计: {len(violations)} 个可能的违规")

    # 保存报告
    report_file = REPO_ROOT / "docs" / "REPORT" / "docs_gov" / "ROOT_VIOLATION_CHECK__20260120.json"
    report_file.parent.mkdir(parents=True, exist_ok=True)

    import json

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(
            {"violations": violations, "total": len(violations)}, f, ensure_ascii=False, indent=2
        )

    print(f"\n报告已保存: {report_file.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
