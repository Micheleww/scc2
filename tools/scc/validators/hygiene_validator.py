#!/usr/bin/env python
import json
import pathlib
import re
import sys

ALLOWED_ART_ROOT = pathlib.Path("artifacts")
REQUIRED_ARTIFACT_KEYS = ["report_md", "selftest_log", "evidence_dir", "patch_diff", "submit_json"]

_FORBIDDEN_REL_PATTERNS = [
    r"(^|/)(tmp|debug)(/)",  # forbidden dir segments
    r"\.bak$",
]


from tools.scc.lib.utils import norm_rel as _norm_rel


def load_submit(path: pathlib.Path):
    try:
        # Windows PowerShell may write UTF-8 with BOM; accept it.
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None


def validate_submit(submit: dict, repo: pathlib.Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(submit, dict):
        return ["missing submit.json or invalid json"]

    task_id = submit.get("task_id")
    if not task_id or not isinstance(task_id, str):
        errors.append("missing task_id")
        task_id = "unknown"

    changed = submit.get("changed_files") or []
    new_files = submit.get("new_files") or []

    art = submit.get("artifacts") or {}
    allowed_root = (repo / ALLOWED_ART_ROOT).resolve()
    for key in REQUIRED_ARTIFACT_KEYS:
        if not art.get(key):
            errors.append(f"missing artifact {key}")
            continue
        rel = norm_rel(str(art[key]))
        expected_prefix = f"artifacts/{task_id}/"
        if not rel.startswith(expected_prefix):
            errors.append(f"artifact {key} must be under {expected_prefix}")
            continue
        p = (repo / rel).resolve()
        if allowed_root not in p.parents and p != allowed_root:
            errors.append(f"artifact {key} not under artifacts/")

    allow = submit.get("allow_paths") or {}
    write_allow = [str(x) for x in (allow.get("write") or []) if isinstance(x, str)]
    if write_allow:
        for f in changed + new_files:
            rel = norm_rel(str(f))
            if not any(rel.startswith(norm_rel(a)) for a in write_allow):
                errors.append(f"changed file {rel} outside write_allow_paths")

    for f in changed + new_files:
        rel = _norm_rel(str(f))
        if rel.startswith("artifacts/"):
            continue
        for pat in _FORBIDDEN_REL_PATTERNS:
            if re.search(pat, rel):
                errors.append(f"forbidden path pattern: {rel}")
                break

    return errors


def main() -> int:
    repo = pathlib.Path.cwd()
    submit_path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else (repo / "submit.json")
    if not submit_path.is_absolute():
        submit_path = repo / submit_path

    submit = load_submit(submit_path)
    errors = validate_submit(submit, repo)
    if errors:
        for e in errors:
            print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
