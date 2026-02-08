#!/usr/bin/env python3
"""
根目录文件整理脚本
根据 ROOT_DIRECTORY_GOVERNANCE.md 规范整理根目录文件
"""

import json
import re
import shutil

# 强制刷新输出
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent

# 允许保留在根目录的文件
ALLOWED_ROOT_FILES = {
    ".cursorrules",
    ".gitignore",
    ".pre-commit-config.yaml",
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
}

# 文档分类规则
DOC_CATEGORIES = {
    "arch": [
        r"架构",
        r"系统",
        r"设计",
        r"结构",
        r"overview",
        r"arch",
        r"导航",
        r"navigation",
        r"guide",
        r"指南",
        r"说明",
    ],
    "spec": [r"规范", r"spec", r"标准", r"标准", r"协议", r"contract"],
    "report": [
        r"报告",
        r"report",
        r"总结",
        r"完成",
        r"修复",
        r"fix",
        r"问题",
        r"证据",
        r"验证",
        r"检查",
        r"结果",
    ],
    "log": [r"日志", r"log", r"记录", r"历史"],
}

# 脚本分类规则
SCRIPT_CATEGORIES = {
    "tools": [
        r"check",
        r"generate",
        r"cleanup",
        r"organize",
        r"gate",
        r"verify",
        r"validate",
        r"scan",
        r"audit",
    ],
    "scripts": [r"deploy", r"start", r"stop", r"run", r"execute", r"install", r"setup", r"config"],
    "test": [r"test", r"debug", r"selftest", r"smoke"],
}


def classify_doc(filename: str) -> str:
    """根据文件名分类文档"""
    filename_lower = filename.lower()

    for category, patterns in DOC_CATEGORIES.items():
        for pattern in patterns:
            if re.search(pattern, filename_lower):
                return category

    # 默认归类为 report（临时文档）
    return "report"


def classify_script(filename: str) -> str:
    """根据文件名分类脚本"""
    filename_lower = filename.lower()

    for category, patterns in SCRIPT_CATEGORIES.items():
        for pattern in patterns:
            if re.search(pattern, filename_lower):
                return category

    # 默认归类为 tools
    return "tools"


def get_target_path(file_path: Path, file_type: str) -> tuple[Path, str]:
    """获取文件的目标路径"""
    filename = file_path.name

    if file_type == "doc":
        category = classify_doc(filename)
        if category == "arch":
            target_dir = REPO_ROOT / "docs" / "arch" / "misc"
        elif category == "spec":
            target_dir = REPO_ROOT / "docs" / "spec" / "misc"
        elif category == "report":
            target_dir = REPO_ROOT / "docs" / "REPORT" / "misc"
        else:  # log
            target_dir = REPO_ROOT / "docs" / "LOG" / "misc"

        return target_dir, category

    elif file_type == "script":
        category = classify_script(filename)
        if category == "tools":
            target_dir = REPO_ROOT / "tools" / "misc"
        elif category == "scripts":
            target_dir = REPO_ROOT / "scripts" / "misc"
        else:  # test
            target_dir = REPO_ROOT / "tools" / "test" / "misc"

        return target_dir, category

    elif file_type == "config":
        target_dir = REPO_ROOT / "configs" / "misc"
        return target_dir, "config"

    elif file_type == "data":
        target_dir = REPO_ROOT / "data" / "misc"
        return target_dir, "data"

    elif file_type == "artifact":
        target_dir = REPO_ROOT / "docs" / "REPORT" / "artifacts" / "misc"
        return target_dir, "artifact"

    else:
        # 临时文件
        target_dir = REPO_ROOT / "_staging" / "misc"
        return target_dir, "temp"


def organize_root_directory(dry_run: bool = True) -> dict:
    """整理根目录文件"""
    results = {
        "docs": [],
        "scripts": [],
        "configs": [],
        "data": [],
        "artifacts": [],
        "temp": [],
        "errors": [],
        "skipped": [],
    }

    # 扫描根目录文件
    root_files = [f for f in REPO_ROOT.iterdir() if f.is_file() and not f.name.startswith(".")]

    for file_path in root_files:
        filename = file_path.name

        # 跳过允许保留的文件
        if filename in ALLOWED_ROOT_FILES:
            results["skipped"].append({"file": filename, "reason": "allowed_root_file"})
            continue

        # 分类文件
        suffix = file_path.suffix.lower()

        try:
            if suffix in [".md", ".txt"]:
                target_dir, category = get_target_path(file_path, "doc")
                file_type = "doc"
            elif suffix in [".py", ".ps1", ".sh", ".bat"]:
                target_dir, category = get_target_path(file_path, "script")
                file_type = "script"
            elif suffix in [".json", ".yaml", ".yml"]:
                target_dir, category = get_target_path(file_path, "config")
                file_type = "config"
            elif suffix in [".csv", ".xlsx"]:
                target_dir, category = get_target_path(file_path, "data")
                file_type = "data"
            elif "artifact" in filename.lower() or "evidence" in filename.lower():
                target_dir, category = get_target_path(file_path, "artifact")
                file_type = "artifact"
            else:
                # 其他文件归类为临时文件
                target_dir, category = get_target_path(file_path, "temp")
                file_type = "temp"

            # 创建目标目录
            target_dir.mkdir(parents=True, exist_ok=True)

            # 目标文件路径
            target_file = target_dir / filename

            # 如果目标文件已存在，添加时间戳
            if target_file.exists():
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                stem = file_path.stem
                target_file = target_dir / f"{stem}_{timestamp}{file_path.suffix}"

            move_info = {
                "file": filename,
                "source": str(file_path.relative_to(REPO_ROOT)),
                "target": str(target_file.relative_to(REPO_ROOT)),
                "category": category,
                "type": file_type,
            }

            if not dry_run:
                # 执行移动
                shutil.move(str(file_path), str(target_file))
                move_info["moved"] = True
            else:
                move_info["moved"] = False

            # 修正键名
            key_map = {
                "doc": "docs",
                "script": "scripts",
                "config": "configs",
                "data": "data",
                "artifact": "artifacts",
                "temp": "temp",
            }
            results[key_map[file_type]].append(move_info)

        except Exception as e:
            results["errors"].append({"file": filename, "error": str(e)})

    return results


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="整理根目录文件")
    parser.add_argument("--execute", action="store_true", help="执行移动（默认是dry-run）")
    args = parser.parse_args()

    dry_run = not args.execute

    print("=" * 80)
    print("根目录文件整理工具")
    print("=" * 80)
    print(f"工作目录: {REPO_ROOT}")
    print(f"模式: {'DRY-RUN (预览)' if dry_run else 'EXECUTE (执行移动)'}")
    print()

    results = organize_root_directory(dry_run=dry_run)

    # 输出结果
    print("\n整理结果:")
    print("-" * 80)

    total_moved = 0
    for category in ["docs", "scripts", "configs", "data", "artifacts", "temp"]:
        files = results[category]
        if files:
            print(f"\n{category.upper()} ({len(files)} 个文件):")
            for item in files[:10]:  # 只显示前10个
                status = "✓" if item.get("moved") else "[预览]"
                print(f"  {status} {item['file']}")
                print(f"      → {item['target']}")
            if len(files) > 10:
                print(f"  ... 还有 {len(files) - 10} 个文件")
            total_moved += len(files)

    if results["skipped"]:
        print(f"\n跳过 ({len(results['skipped'])} 个文件):")
        for item in results["skipped"]:
            print(f"  - {item['file']} ({item['reason']})")

    if results["errors"]:
        print(f"\n错误 ({len(results['errors'])} 个文件):")
        for item in results["errors"]:
            print(f"  ✗ {item['file']}: {item['error']}")

    print("\n" + "=" * 80)
    print(f"总计: {total_moved} 个文件需要移动")
    print(f"跳过: {len(results['skipped'])} 个文件")
    print(f"错误: {len(results['errors'])} 个文件")

    if dry_run:
        print("\n提示: 使用 --execute 参数执行实际移动")

    # 保存结果到文件
    report_file = (
        REPO_ROOT
        / "docs"
        / "REPORT"
        / "docs_gov"
        / f"ROOT_CLEANUP_REPORT__{datetime.now().strftime('%Y%m%d')}.json"
    )
    report_file.parent.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n报告已保存: {report_file.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
