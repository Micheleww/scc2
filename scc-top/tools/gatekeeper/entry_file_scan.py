#!/usr/bin/env python3
"""
入口文件侦测门禁脚本
TaskCode: GATE-NO-NEW-ENTRYFILE-v0.2__20260115
硬约束: Fail-Closed
"""

import glob
import os
import re
from datetime import datetime

import yaml


def load_gate_rules():
    """加载入口文件侦测规则"""
    rules_path = "configs/current/gate_rules_entryfile.yaml"
    try:
        with open(rules_path, encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        return rules
    except (OSError, yaml.YAMLError) as e:
        print(f"[ERROR] 无法加载入口文件侦测规则文件 {rules_path}: {e}")
        return None


def get_changed_files():
    """获取本次变更的文件列表（包括暂存和未暂存的更改）"""
    import subprocess

    try:
        all_files = set()

        # 获取未暂存的更改
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            for f in result.stdout.strip().split("\n"):
                if f:
                    all_files.add(f)

        # 获取暂存的更改
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            for f in result.stdout.strip().split("\n"):
                if f:
                    all_files.add(f)

        return [f for f in all_files if f and os.path.exists(f)]
    except Exception as e:
        print(f"[WARNING] 无法获取变更文件列表: {e}")
        return []


def is_entry_file(file_path, rules):
    """判断文件是否为入口类文件"""
    entry_patterns = rules.get("entry_file_scan", {}).get("entry_patterns", [])

    # 将文件名转换为小写进行大小写不敏感匹配
    file_path_lower = file_path.lower()

    # 检查文件名模式
    for pattern in entry_patterns:
        # 转换模式为小写进行大小写不敏感匹配
        pattern_lower = pattern.lower()

        if pattern.startswith("**/"):
            # 匹配任意目录前缀
            suffix = pattern[3:].lower()
            if glob.fnmatch.fnmatch(file_path_lower, pattern_lower):
                return True
        elif pattern.endswith("**"):
            # 匹配目录前缀
            prefix = pattern[:-2].lower()
            if file_path_lower.startswith(prefix):
                return True
        elif "*" in pattern:
            if glob.fnmatch.fnmatch(file_path_lower, pattern_lower):
                return True
        else:
            if pattern_lower in file_path_lower:
                return True

    # 特殊情况：检查文件名是否包含"entry"关键词
    if "entry" in file_path_lower:
        return True

    # 检查文件内容中的入口标记
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
        for pattern in entry_patterns:
            if "kind.*" in pattern:
                kind_pattern = pattern.replace("kind.*", "kind:")
                if re.search(kind_pattern, content, re.IGNORECASE):
                    return True
    except Exception:
        pass

    return False


def is_in_allowlist(file_path, rules):
    """判断文件是否在允许列表中"""
    allowlist = rules.get("entry_file_scan", {}).get("allowlist", [])

    for allowed in allowlist:
        if allowed.endswith("**"):
            prefix = allowed[:-2]
            if file_path.startswith(prefix):
                return True
        elif "*" in allowed:
            if glob.fnmatch.fnmatch(file_path, allowed):
                return True
        else:
            if file_path == allowed:
                return True

    return False


def scan_new_entry_files(rules):
    """扫描新增的入口类文件"""
    if not rules:
        return 0, []

    if not rules.get("entry_file_scan", {}).get("enabled", True):
        print("[INFO] 入口文件侦测已禁用")
        return 0, []

    changed_files = get_changed_files()
    violations = []

    print(f"[INFO] 扫描 {len(changed_files)} 个变更文件")

    for file_path in changed_files:
        print(f"[DEBUG] 检查文件: {file_path}")

        # 检查是否为入口文件
        if is_entry_file(file_path, rules):
            print(f"[DEBUG] 是入口文件: {file_path}")

            # 检查是否在允许列表中
            if not is_in_allowlist(file_path, rules):
                print(f"[DEBUG] 不在允许列表中: {file_path}")
                violations.append(file_path)
            else:
                print(f"[DEBUG] 在允许列表中: {file_path}")

    if violations:
        print("[FAIL] 发现新增未授权入口文件:")
        for f in violations:
            print(f"  - {f}")
        print("RESULT=FAIL")
        print("REASON_CODE=NEW_ENTRYFILE")
        return 1, violations

    print("[PASS] 未发现新增未授权入口文件")
    return 0, []


def run_gate():
    """运行入口文件侦测门禁"""
    print("=" * 60)
    print("GATE-NO-NEW-ENTRYFILE-v0.2__20260115")
    print("入口文件侦测门禁")
    print("=" * 60)
    print(f"时间: {datetime.now().isoformat()}")
    print()

    rules = load_gate_rules()
    if rules is None:
        print("[FAIL] 无法加载规则文件")
        return 1, []

    exit_code, violations = scan_new_entry_files(rules)

    print()
    print("=" * 60)
    print(f"门禁结果: {'FAIL' if exit_code != 0 else 'PASS'}")
    print(f"EXIT_CODE={exit_code}")
    print("=" * 60)

    return exit_code, violations


if __name__ == "__main__":
    exit_code, _ = run_gate()
    exit(exit_code)
