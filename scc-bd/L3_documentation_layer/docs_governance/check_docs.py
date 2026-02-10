#!/usr/bin/env python3
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

# 定义 REPORT 字段的严格校验规则
REPORT_FIELD_RULES = {
    "doc_id": {"type": str, "non_empty": True},
    "kind": {"type": str, "non_empty": True, "enum": ["REPORT", "ARCH", "SPEC", "LOG"]},
    "scope": {"type": str, "non_empty": True},
    "topic": {"type": str, "non_empty": True},
    "version": {"type": str, "non_empty": True, "pattern": r"^v?\d+\.\d+\.\d+$"},
    "status": {
        "type": str,
        "non_empty": True,
        "enum": ["DRAFT", "REVIEW", "ACTIVE", "DEPRECATED", "ARCHIVED", "DONE", "BLOCKED"],
    },
    "owner": {"type": str, "non_empty": True},
    "created": {"type": str, "non_empty": True, "pattern": r"^\d{4}-\d{2}-\d{2}$"},
    "updated": {"type": str, "non_empty": True, "pattern": r"^\d{4}-\d{2}-\d{2}$"},
    "law_ref": {"type": (list, str), "non_empty": True},
    "contracts_ref": {"type": list, "non_empty": False},
    "task_ref": {"type": list, "non_empty": False},
    "supersedes": {"type": list, "non_empty": False},
    "superseded_by": {"type": list, "non_empty": False},
    "evidence_paths": {"type": list, "non_empty": True},
    "blocked_by": {"type": (list, str), "non_empty": False},
}

REQUIRED_YAML_FIELDS = list(REPORT_FIELD_RULES.keys())

LAW_REF_POINTER = "law/QCC-README.md"

BLACKLIST_KEYWORDS = ["BEGIN QCC", "QCC-A：AI 协作宪法", "QCC-S：系统宪法", "QCC-E：工程文档宪法"]

BLACKLIST_EXCEPTIONS = ["黑名单关键字", "blacklist", "禁止"]

# Standard: Use lowercase for arch/ and spec/ directories (aligned with mkdocs.yml)
# REPORT and LOG remain uppercase for consistency with existing structure
# Windows is case-insensitive, Linux is case-sensitive - this ensures cross-platform compatibility
REQUIRED_INDEX_DIRS = ["arch", "spec", "REPORT", "LOG", "templates"]

REQUIRED_TEMPLATE_FILES = [
    "template_arch.md",
    "template_spec.md",
    "template_report.md",
    "template_log.md",
]

SCC_FRONTMATTER_REQUIRED_FIELDS = ["oid", "layer", "primary_unit", "status", "tags"]
SCC_OID_PLACEHOLDER_TOKENS = [
    "MINT_WITH_SCC_OID_GENERATOR",
    "<MINT_WITH_SCC_OID_GENERATOR>",
]


class DocsGovernanceChecker:
    def __init__(self, repo_root: str, staged_only: bool = True):
        self.repo_root = Path(repo_root)
        self.docs_dir = self.repo_root / "docs"
        self.staged_only = staged_only
        self.violations: list[tuple[str, str]] = []
        self.warnings: list[tuple[str, str]] = []
        self.rules = self._load_rules()

    def _load_rules(self) -> dict[str, Any]:
        rules_file = self.repo_root / "tools" / "docs_governance" / "rules.yaml"
        if not rules_file.exists():
            self.add_warning(str(rules_file), "Rules file not found, using default checks only")
            return {}

        try:
            with open(rules_file, encoding="utf-8") as f:
                return yaml.safe_load(f)
        except Exception as e:
            self.add_warning(str(rules_file), f"Failed to load rules: {str(e)}")
            return {}

    def _get_staged_files(self) -> set[str]:
        try:
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            staged_files = (
                set(result.stdout.strip().split("\n")) if result.stdout.strip() else set()
            )
            return staged_files
        except Exception as e:
            self.add_warning(
                "git", f"Failed to get staged files: {str(e)}, falling back to full check"
            )
            return None

    def _get_file_content_from_git(self, file_path: str, ref: str = "HEAD") -> str | None:
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{file_path}"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout
        except Exception:
            return None

    def _parse_yaml_frontmatter(self, content: str) -> dict[str, Any] | None:
        if not content.startswith("---"):
            return None

        yaml_end = content.find("---", 3)
        if yaml_end == -1:
            return None

        yaml_content = content[3:yaml_end]
        try:
            return yaml.safe_load(yaml_content)
        except yaml.YAMLError:
            return None

    def _compare_versions(self, v1: str, v2: str) -> int:
        try:
            parts1 = [int(x) for x in v1.lstrip("v").split(".")]
            parts2 = [int(x) for x in v2.lstrip("v").split(".")]

            for p1, p2 in zip(parts1, parts2):
                if p1 > p2:
                    return 1
                elif p1 < p2:
                    return -1

            if len(parts1) > len(parts2):
                return 1
            elif len(parts1) < len(parts2):
                return -1

            return 0
        except:
            return 0

    def add_violation(self, file_path: str, message: str):
        self.violations.append((file_path, message))

    def add_warning(self, file_path: str, message: str):
        self.warnings.append((file_path, message))

    def check_yaml_frontmatter(self, file_path: Path) -> bool:
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            if not content.startswith("---"):
                return True

            yaml_end = content.find("---", 3)
            if yaml_end == -1:
                self.add_violation(str(file_path), "Invalid YAML frontmatter: missing closing ---")
                return False

            yaml_content = content[3:yaml_end]
            try:
                frontmatter = yaml.safe_load(yaml_content)
                if not isinstance(frontmatter, dict):
                    self.add_violation(str(file_path), "YAML frontmatter is not a dictionary")
                    return False

                # SCC SSOT / Canonical docs use an OID-based frontmatter schema.
                # This prevents "double truth" between legacy docflow schema and SSOT trunk.
                rel = file_path.relative_to(self.repo_root).as_posix()
                is_ssot_tree = rel.startswith("docs/ssot/") or rel.startswith("docs/CANONICAL/")
                is_index_doc = file_path.name in {"START_HERE.md", "00_index.md", "index.md"}
                is_inputs_or_derived = (
                    rel.startswith("docs/INPUTS/")
                    or rel.startswith("docs/DERIVED/")
                    or rel.startswith("docs/PROGRESS/")
                )
                looks_like_scc = "oid" in frontmatter or "primary_unit" in frontmatter or is_ssot_tree

                # Raw/derived/progress docs may embed lightweight frontmatter; do not enforce legacy schema here.
                if is_inputs_or_derived:
                    return True

                if looks_like_scc:
                    # Allow index docs to be schema-light; but if they embed SCC frontmatter,
                    # it must be minimally valid.
                    file_ok = True
                    missing = [k for k in SCC_FRONTMATTER_REQUIRED_FIELDS if k not in frontmatter]
                    if missing and not is_index_doc:
                        self.add_violation(str(file_path), f"SCC frontmatter missing fields: {', '.join(missing)}")
                        file_ok = False

                    oid = str(frontmatter.get("oid") or "").strip()
                    if oid:
                        ulid_ok = bool(re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{26}", oid))
                        placeholder_ok = any(tok in oid for tok in SCC_OID_PLACEHOLDER_TOKENS)
                        if not (ulid_ok or placeholder_ok):
                            self.add_violation(str(file_path), "SCC frontmatter field 'oid' must be a ULID or placeholder token")
                            file_ok = False
                    elif not is_index_doc:
                        self.add_violation(str(file_path), "SCC frontmatter field 'oid' is required")
                        file_ok = False

                    tags = frontmatter.get("tags")
                    if tags is not None and not isinstance(tags, list):
                        self.add_violation(str(file_path), "SCC frontmatter field 'tags' must be a list")
                        file_ok = False

                    # For SCC docs, do not enforce legacy `law_ref` pointer.
                    return file_ok

                doc_kind = frontmatter.get("kind", "")
                is_log = doc_kind == "LOG" or "log_id" in frontmatter

                if is_log:
                    # LOG 文档有不同的要求，这里暂时保留原有逻辑
                    required_fields = [
                        "log_id",
                        "type",
                        "task_ref",
                        "env",
                        "owner",
                        "time_start",
                        "time_end",
                        "inputs",
                        "outputs",
                        "result",
                        "evidence",
                        "law_ref",
                    ]
                    for field in required_fields:
                        if field not in frontmatter:
                            self.add_violation(str(file_path), f"Missing required field: {field}")
                else:
                    # REPORT/ARCH/SPEC 文档使用严格校验规则
                    # 1. 检查所有必填字段是否存在
                    for field, rules in REPORT_FIELD_RULES.items():
                        if field not in frontmatter:
                            self.add_violation(str(file_path), f"Missing required field: {field}")
                            continue

                        value = frontmatter[field]

                        # 2. 类型检查
                        expected_type = rules.get("type")
                        if expected_type and not isinstance(value, expected_type):
                            self.add_violation(
                                str(file_path),
                                f"Field '{field}' must be of type {expected_type.__name__ if isinstance(expected_type, type) else str(expected_type)}",
                            )
                            continue

                        # 3. 非空检查
                        if rules.get("non_empty"):
                            if isinstance(value, str) and not value.strip():
                                self.add_violation(
                                    str(file_path), f"Field '{field}' cannot be empty"
                                )
                            elif isinstance(value, list) and len(value) == 0:
                                self.add_violation(
                                    str(file_path), f"Field '{field}' cannot be empty list"
                                )

                        # 4. 枚举值检查
                        enum_values = rules.get("enum")
                        if enum_values and value not in enum_values:
                            self.add_violation(
                                str(file_path),
                                f"Field '{field}' must be one of: {', '.join(enum_values)}",
                            )

                        # 5. 正则表达式匹配检查
                        pattern = rules.get("pattern")
                        if pattern and isinstance(value, str) and not re.match(pattern, value):
                            self.add_violation(
                                str(file_path),
                                f"Field '{field}' does not match required pattern: {pattern}",
                            )

                    # 6. 特殊处理：status=BLOCKED 时必须有 blocked_by 字段
                    status = frontmatter.get("status")
                    if status == "BLOCKED":
                        blocked_by = frontmatter.get("blocked_by")
                        if not blocked_by:
                            self.add_violation(
                                str(file_path),
                                "Field 'blocked_by' is required when status is BLOCKED",
                            )
                        elif isinstance(blocked_by, list) and len(blocked_by) == 0:
                            self.add_violation(
                                str(file_path),
                                "Field 'blocked_by' cannot be empty list when status is BLOCKED",
                            )
                        elif isinstance(blocked_by, str) and not blocked_by.strip():
                            self.add_violation(
                                str(file_path),
                                "Field 'blocked_by' cannot be empty string when status is BLOCKED",
                            )

                # 7. 检查 law_ref 必须包含 LAW_REF_POINTER
                if "law_ref" in frontmatter:
                    law_ref = frontmatter["law_ref"]
                    if isinstance(law_ref, list):
                        if LAW_REF_POINTER not in law_ref:
                            self.add_violation(
                                str(file_path), f"law_ref must contain {LAW_REF_POINTER}"
                            )
                    elif isinstance(law_ref, str):
                        if law_ref != LAW_REF_POINTER:
                            self.add_violation(str(file_path), f"law_ref must be {LAW_REF_POINTER}")

            except yaml.YAMLError as e:
                self.add_violation(str(file_path), f"Invalid YAML: {str(e)}")
                return False

        except Exception as e:
            self.add_violation(str(file_path), f"Error reading file: {str(e)}")
            return False

        return not any(v[0] == str(file_path) for v in self.violations)


    def check_blacklist_keywords(self, file_path: Path) -> bool:
        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            for keyword in BLACKLIST_KEYWORDS:
                if keyword in content:
                    for exception in BLACKLIST_EXCEPTIONS:
                        if exception in content:
                            return True
                    self.add_violation(str(file_path), f"Contains blacklisted keyword: {keyword}")
                    return False

        except Exception as e:
            self.add_warning(str(file_path), f"Error checking blacklist: {str(e)}")

        return True

    def check_required_index_files(self) -> bool:
        """Check required index files according to standard (lowercase arch/spec, uppercase REPORT/LOG)"""
        all_exist = True

        for dir_name in REQUIRED_INDEX_DIRS:
            index_file = self.docs_dir / dir_name / "00_index.md"
            if not index_file.exists():
                self.add_violation(
                    str(index_file), f"Required index file missing: docs/{dir_name}/00_index.md"
                )
                all_exist = False

        return all_exist

    def check_required_template_files(self) -> bool:
        all_exist = True
        templates_dir = self.docs_dir / "templates"
        for template_file in REQUIRED_TEMPLATE_FILES:
            template_path = templates_dir / template_file
            if not template_path.exists():
                self.add_violation(str(template_path), "Required template file missing")
                all_exist = False

        return all_exist

    def check_report_tasks_structure(self) -> bool:
        tasks_dir = self.docs_dir / "REPORT" / "tasks"
        if not tasks_dir.exists():
            self.add_warning(str(tasks_dir), "REPORT/tasks directory does not exist yet")
            return True

        has_valid_structure = False
        for year_dir in tasks_dir.iterdir():
            if year_dir.is_dir() and year_dir.name.isdigit():
                for task_dir in year_dir.iterdir():
                    if task_dir.is_dir():
                        report_files = list(task_dir.glob("REPORT_*.md"))
                        if report_files:
                            has_valid_structure = True
                        else:
                            self.add_warning(str(task_dir), "No REPORT_*.md file found")

        return has_valid_structure

    def check_all_markdown_files(self, staged_files: set[str] | None = None) -> bool:
        all_valid = True
        for md_file in self.docs_dir.rglob("*.md"):
            if staged_files is not None:
                rel_path = md_file.relative_to(self.repo_root).as_posix()
                if rel_path not in staged_files:
                    continue

            if not self.check_yaml_frontmatter(md_file):
                all_valid = False
            if not self.check_blacklist_keywords(md_file):
                all_valid = False

        return all_valid

    def check_staged_changes(self, staged_files: set[str]) -> bool:
        if not self.rules:
            return True

        all_passed = True

        triggers = self.rules.get("triggers", [])
        report_or_log_rule = self.rules.get("require_report_or_log_on_code_change", {})

        code_paths_in_staged = set()
        docs_paths_in_staged = set()

        for file_path in staged_files:
            for code_path in report_or_log_rule.get("code_paths", []):
                if file_path.startswith(code_path):
                    code_paths_in_staged.add(file_path)
                    break

            for trigger in triggers:
                for code_path in trigger.get("code_paths", []):
                    if file_path.startswith(code_path):
                        code_paths_in_staged.add(file_path)
                        break

            for docs_path in report_or_log_rule.get("docs_paths", []):
                if file_path.startswith(docs_path):
                    docs_paths_in_staged.add(file_path)
                    break

            for trigger in triggers:
                for docs_path in trigger.get("require_any_docs_paths", []):
                    if file_path.startswith(docs_path):
                        docs_paths_in_staged.add(file_path)
                        break

        for trigger in triggers:
            trigger_name = trigger.get("name", "unknown")
            trigger_code_paths = trigger.get("code_paths", [])
            required_docs_paths = trigger.get("require_any_docs_paths", [])

            has_code_change = any(
                any(staged_file.startswith(cp) for cp in trigger_code_paths)
                for staged_file in staged_files
            )

            if has_code_change:
                has_docs_change = any(
                    any(staged_file.startswith(dp) for dp in required_docs_paths)
                    for staged_file in staged_files
                )

                if not has_docs_change:
                    trigger_files = [
                        f
                        for f in staged_files
                        if any(f.startswith(cp) for cp in trigger_code_paths)
                    ]
                    for tf in trigger_files:
                        self.add_violation(
                            tf,
                            f"Rule '{trigger_name}' triggered: code change requires documentation in one of: {', '.join(required_docs_paths)}",
                        )
                    all_passed = False

        report_or_log_code_paths = report_or_log_rule.get("code_paths", [])
        report_or_log_docs_paths = report_or_log_rule.get("docs_paths", [])

        has_code_change = any(
            any(staged_file.startswith(cp) for cp in report_or_log_code_paths)
            for staged_file in staged_files
        )

        if has_code_change:
            has_report_or_log = any(
                any(staged_file.startswith(dp) for dp in report_or_log_docs_paths)
                for staged_file in staged_files
            )

            if not has_report_or_log:
                trigger_files = [
                    f
                    for f in staged_files
                    if any(f.startswith(cp) for cp in report_or_log_code_paths)
                ]
                for tf in trigger_files:
                    self.add_violation(
                        tf,
                        f"Code change requires REPORT or LOG documentation in one of: {', '.join(report_or_log_docs_paths)}",
                    )
                all_passed = False

        return all_passed

    def check_version_overlap(self, staged_files: set[str]) -> bool:
        all_passed = True

        for file_path in staged_files:
            if not file_path.startswith("docs/") or not file_path.endswith(".md"):
                continue

            abs_path = self.repo_root / file_path
            if not abs_path.exists():
                continue

            with open(abs_path, encoding="utf-8") as f:
                staged_content = f.read()

            staged_frontmatter = self._parse_yaml_frontmatter(staged_content)
            if not staged_frontmatter:
                continue

            staged_status = staged_frontmatter.get("status", "")
            staged_version = staged_frontmatter.get("version", "")

            head_content = self._get_file_content_from_git(file_path, "HEAD")
            if head_content is None:
                continue

            head_frontmatter = self._parse_yaml_frontmatter(head_content)
            if not head_frontmatter:
                continue

            head_status = head_frontmatter.get("status", "")
            head_version = head_frontmatter.get("version", "")

            if head_status == "ACTIVE" or staged_status == "ACTIVE":
                if staged_status not in ["DEPRECATED", "ARCHIVED"]:
                    if staged_version == head_version:
                        self.add_violation(
                            file_path,
                            f"Version overlap detected: Cannot modify ACTIVE document (version {staged_version}) without creating a new version or marking as DEPRECATED/ARCHIVED",
                        )
                        all_passed = False

        return all_passed

    def run_all_checks(self) -> bool:
        print("Running docs governance checks...")
        print()

        all_passed = True
        staged_files = None

        if self.staged_only:
            print("Checking staged changes only...")
            staged_files = self._get_staged_files()
            if staged_files is None:
                print("  Failed to get staged files, falling back to full check")
                print()
            elif len(staged_files) == 0:
                print("  No staged files found, skip")
                print()
                return True
            else:
                has_docs_files = any(f.startswith("docs/") for f in staged_files)
                if not has_docs_files:
                    print(f"  Found {len(staged_files)} staged file(s), but no docs files, skip")
                    print()
                    return True
                print(f"  Found {len(staged_files)} staged file(s)")
                print()
        else:
            print("Checking all files (no git or full check requested)...")
            print()

        print("1. Checking required index files...")
        if not self.check_required_index_files():
            all_passed = False
        print("   Done.")
        print()

        print("2. Checking required template files...")
        if not self.check_required_template_files():
            all_passed = False
        print("   Done.")
        print()

        print("3. Checking REPORT/tasks structure...")
        self.check_report_tasks_structure()
        print("   Done.")
        print()

        if staged_files is not None:
            print("4. Checking staged changes against rules...")
            if not self.check_staged_changes(staged_files):
                all_passed = False
            print("   Done.")
            print()

            print("5. Checking version overlap...")
            if not self.check_version_overlap(staged_files):
                all_passed = False
            print("   Done.")
            print()

        print("6. Checking all markdown files for YAML frontmatter and blacklist keywords...")
        if not self.check_all_markdown_files(staged_files):
            all_passed = False
        print("   Done.")
        print()

        return all_passed

    def print_results(self):
        if self.violations:
            print("=" * 80)
            print("VIOLATIONS FOUND:")
            print("=" * 80)
            for file_path, message in self.violations:
                print(f"  {file_path}")
                print(f"    {message}")
            print()

        if self.warnings:
            print("=" * 80)
            print("WARNINGS:")
            print("=" * 80)
            for file_path, message in self.warnings:
                print(f"  {file_path}")
                print(f"    {message}")
            print()

        if not self.violations and not self.warnings:
            print("=" * 80)
            print("ALL CHECKS PASSED!")
            print("=" * 80)
            print()


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Docs governance checker")
    parser.add_argument(
        "--staged",
        action="store_true",
        default=True,
        help="Check only staged files (default: True)",
    )
    parser.add_argument("--full", action="store_true", help="Check all files, ignore staged status")

    args = parser.parse_args()

    staged_only = args.staged and not args.full

    mode = "staged" if staged_only else "full"

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    checker = DocsGovernanceChecker(repo_root, staged_only=staged_only)

    all_passed = checker.run_all_checks()

    print(f"\nMode: {mode}")
    if checker.rules:
        triggers = checker.rules.get("triggers", [])
        if triggers:
            print("Active triggers:")
            for trigger in triggers:
                print(f"  - {trigger.get('name', 'unknown')}")
        else:
            print("No triggers configured")
    print()

    checker.print_results()

    if not all_passed:
        print("Docs governance checks FAILED.")
        print()
        print("Please fix the violations above before committing.")
        sys.exit(1)
    else:
        print("Docs governance checks PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
