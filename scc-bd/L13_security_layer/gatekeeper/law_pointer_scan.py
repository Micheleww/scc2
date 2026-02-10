#!/usr/bin/env python3
import glob
import re
import subprocess

import yaml


def load_law_rules():
    rules_path = "configs/current/law_pointer_rules.yaml"
    try:
        with open(rules_path, encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        return rules
    except (OSError, yaml.YAMLError) as e:
        print(f"[ERROR] 无法加载 law 扫描规则文件 {rules_path}: {e}")
        return None


def get_scan_files():
    """
    Scope policy (SCC SSOT):
    - Scan only code + governance/canonical docs (tracked by git).
    - Do NOT scan raw inputs / evidence trees (docs/INPUTS, docs/REPORT, artifacts, etc.).
    """

    def _git_ls_files(args: list[str]) -> set[str]:
        try:
            p = subprocess.run(
                ["git", "ls-files", *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
            )
            if int(p.returncode or 0) != 0:
                return set()
            out = (p.stdout or "").splitlines()
            return set([x.strip().replace("\\", "/") for x in out if x.strip()])
        except Exception:
            return set()

    tracked = _git_ls_files(["src", "docs/ssot", "docs/CANONICAL", "docs/START_HERE.md", "docs/arch"])

    files: list[str] = []
    candidates: list[str] = []
    candidates.extend(glob.glob("src/**/*.py", recursive=True))
    candidates.append("docs/START_HERE.md")
    candidates.extend(glob.glob("docs/ssot/**/*.md", recursive=True))
    candidates.extend(glob.glob("docs/CANONICAL/**/*.md", recursive=True))
    candidates.extend(glob.glob("docs/arch/**/*.md", recursive=True))

    for f in candidates:
        f2 = (f or "").strip().replace("\\", "/")
        if not f2:
            continue
        if tracked and f2 not in tracked:
            continue
        files.append(f2)

    return sorted(set(files))


def check_pointer_compliance(file_path, content, rules):
    allow_patterns = rules.get("allow_patterns", [])
    deny_rules = rules.get("deny_rules", [])

    for pattern in allow_patterns:
        if re.search(pattern, content, re.IGNORECASE):
            return None

    for rule in deny_rules:
        pattern = rule.get("pattern", "")
        rule_id = rule.get("id", "unknown")
        reason = rule.get("reason", "")
        threshold = rule.get("threshold", 1)

        if pattern:
            matches = list(re.finditer(pattern, content, re.IGNORECASE))
            if len(matches) >= threshold:
                violation_lines = []
                for match in matches:
                    line_no = content[: match.start()].count("\n") + 1
                    violation_lines.append(line_no)

                lines = content.split("\n")
                context_lines = []
                for line_no in violation_lines[:10]:
                    start = max(0, line_no - 2)
                    end = min(len(lines), line_no + 1)
                    context_lines.extend(lines[start:end])

                return {
                    "file": file_path,
                    "rule_id": rule_id,
                    "reason": reason,
                    "violation_count": len(matches),
                    "violation_lines": violation_lines[:10],
                    "context": "\n".join(context_lines),
                }

    return None


def check_law_file(file_path, rules):
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        violation = check_pointer_compliance(file_path, content, rules)
        return violation
    except (OSError, UnicodeDecodeError) as e:
        print(f"[ERROR] 无法读取文件 {file_path}: {e}")
        return {
            "file": file_path,
            "rule_id": "READ_ERROR",
            "reason": f"无法读取文件: {e}",
            "violation_count": 1,
        }


def scan_law_pointers(scan_files=None, changed_files=None):
    rules = load_law_rules()
    if not rules:
        return 1

    if changed_files:
        files_to_scan = changed_files
        print(f"[INFO] 扫描 {len(files_to_scan)} 个变更文件...")
    else:
        files_to_scan = scan_files if scan_files else get_scan_files()
        if not files_to_scan:
            print("[INFO] 没有找到要扫描的文件")
            return 0
        print(f"[INFO] 扫描 {len(files_to_scan)} 个文件...")

    violations = []
    for file_path in files_to_scan:
        violation = check_law_file(file_path, rules)
        if violation:
            violations.append(violation)

    if violations:
        print(f"[ERROR] 发现 {len(violations)} 个 law 指针违规:")
        for violation in violations:
            file_path = violation["file"]
            rule_id = violation["rule_id"]
            reason = violation["reason"]
            violation_count = violation["violation_count"]
            violation_lines = violation["violation_lines"]

            print(
                f"{file_path}:{violation_lines[0] if violation_lines else '?'} [rule={rule_id}] {reason}"
            )
            print(f"  命中次数: {violation_count}")
            if violation_lines:
                print(f"  违规行号: {', '.join(map(str, violation_lines[:5]))}")
        return 1
    else:
        print("[SUCCESS] 没有发现 law 指针违规")
        return 0
