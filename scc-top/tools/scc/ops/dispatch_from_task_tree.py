#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _date_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")

def _contract_looks_hardened(path: Path) -> bool:
    """
    Heuristic: a generated contract is "hardened" if it contains extra acceptance checks
    beyond the generator baseline (python_version + top_validator + oid_validator).
    """
    try:
        d = _read_json(path)
    except Exception:
        return False
    acc = d.get("acceptance") if isinstance(d.get("acceptance"), dict) else {}
    checks = acc.get("checks") if isinstance(acc.get("checks"), list) else []
    names = [str(c.get("name") or "").strip() for c in checks if isinstance(c, dict)]
    s = set([n for n in names if n])
    baseline = {"python_version", "top_validator", "oid_validator"}
    if not s or s == baseline:
        return False
    if any(n in s for n in ["contract_json_valid", "contract_required_fields", "contract_json_sanity", "artifacts_dir_exists"]):
        return True
    return len(s) > len(baseline)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8", errors="replace")


def _to_repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _safe_id(task_id: str, *, max_len: int = 64) -> str:
    s = (task_id or "").strip()
    s = s.replace(":", "_").replace("/", "_").replace("\\", "_")
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "task"
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s


def _iter_task_items(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    epics = tree.get("epics") if isinstance(tree.get("epics"), list) else []
    for e in epics:
        if not isinstance(e, dict):
            continue
        caps = e.get("capabilities") if isinstance(e.get("capabilities"), list) else []
        for c in caps:
            if not isinstance(c, dict):
                continue
            tasks = c.get("tasks") if isinstance(c.get("tasks"), list) else []
            for t in tasks:
                if isinstance(t, dict):
                    out.append(t)
    return out


def _normalize_scope_allow(scope_allow: Any) -> Optional[List[str]]:
    if isinstance(scope_allow, list):
        items = [str(x).strip().replace("\\", "/") for x in scope_allow if str(x).strip()]
        return items or None
    if isinstance(scope_allow, str):
        s = scope_allow.strip()
        if not s or s.lower().startswith("tbd"):
            return None
        parts = [p.strip().replace("\\", "/") for p in s.splitlines() if p.strip()]
        return parts or None
    return None


def _is_trivial_contract_only_scope(*, scope_allow: List[str], contract_ref: str) -> bool:
    items = [str(x).strip().replace("\\", "/") for x in (scope_allow or []) if str(x).strip()]
    cref = (contract_ref or "").strip().replace("\\", "/")
    if not items or not cref:
        return True
    # If scope only includes the contract file itself, it's not executable yet.
    if len(items) == 1 and items[0] == cref:
        return True
    # If all allowlist entries are within generated contract dir, treat as non-executable.
    if all(p.startswith("docs/ssot/04_contracts/generated/") for p in items):
        return True
    return False


def _artifacts_dir(area: str, task_code: str) -> Path:
    return (_REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / task_code).resolve()


def _report_path(area: str, task_code: str) -> Path:
    return (_REPO_ROOT / "docs" / "REPORT" / area / f"REPORT__{task_code}__{_date_utc()}.md").resolve()

def _maybe_repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _ssot_search_paths(*, task_text: str, limit: int = 6) -> List[str]:
    """
    Deterministic, low-token: pick a small SSOT context set from registry.json.
    """
    cmd = [
        sys.executable,
        "tools/scc/ops/ssot_search.py",
        "--task-text",
        str(task_text or ""),
        "--limit",
        str(int(limit or 6)),
    ]
    p = subprocess.run(cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)
    if int(p.returncode or 0) != 0:
        return []
    try:
        j = json.loads(p.stdout or "{}")
    except Exception:
        return []
    picked = j.get("picked") if isinstance(j.get("picked"), list) else []
    out: List[str] = []
    for it in picked:
        if not isinstance(it, dict):
            continue
        path0 = str(it.get("path") or "").strip().replace("\\", "/")
        if path0:
            out.append(path0)
    return out[: max(0, int(limit or 6))]


def _build_snippet_pack(
    *,
    area: str,
    task_code: str,
    parent_id: str,
    task_text: str,
    allowed_globs: List[str],
    embed_paths: List[str],
    max_total_chars: int,
) -> str:
    """
    Generate a deterministic snippet pack under docs/REPORT/... to reduce token usage.
    Returns repo-relative path to the pack.
    """
    artifacts = _artifacts_dir(area, task_code)
    artifacts.mkdir(parents=True, exist_ok=True)
    out_path = (artifacts / f"snippet_pack__{_safe_id(parent_id)}.md").resolve()
    args = [sys.executable, "tools/scc/ops/deterministic_snippet_pack.py", "--task-text", str(task_text or ""), "--out", _maybe_repo_rel(out_path)]
    for g in (allowed_globs or []):
        gg = str(g).strip().replace("\\", "/")
        if gg:
            args.extend(["--allowed-glob", gg])
    for p in (embed_paths or []):
        pp = str(p).strip().replace("\\", "/")
        if pp:
            args.extend(["--embed-path", pp])
    # Keep scope-harden context very small to control token burn.
    args.extend(["--max-total-chars", str(int(max_total_chars or 6000)), "--max-files", "4"])
    subprocess.run(args, cwd=str(_REPO_ROOT), check=False)
    return _to_repo_rel(out_path)


def build_parent_description(*, task_id: str, task_label: str, contract_ref: str) -> str:
    return "\n".join(
        [
            f"TASK: CONTRACT_SCOPE_HARDEN",
            "",
            f"task_id: {task_id}",
            f"contract_ref: {contract_ref}",
            "",
            "Goal:",
            "- Harden this contract so it becomes executable: fill scope_allow + acceptance + stop_condition + commands_hint.",
            "",
            "Rules (mandatory):",
            "- You MUST ONLY edit the allowlisted contract file.",
            "- Do NOT search the repo. Do NOT open other files unless absolutely necessary.",
            "- Keep changes minimal and deterministic.",
            "- Acceptance must be executable commands; verifier judges only by acceptance outcomes.",
            "- Preferred: edit the allowlisted file directly in the worktree (no patch output).",
            "- If you cannot write files, output ONE `git apply` compatible unified diff patch (no markdown/code fences, no narration).",
            "- If outputting a patch: it MUST start with `diff --git a/<path> b/<path>` and touch exactly ONE file (the allowlisted contract file).",
            "- If outputting a patch: inside hunks, every line MUST start with exactly one of: ` ` (context), `+` (add), `-` (remove).",
            "",
            "Minimum required fields to ensure:",
            "- goal / scope_allow / constraints / acceptance.checks[] / stop_condition / commands_hint / inputs_ref / outputs_expected",
            "",
            f"Task label / hint: {task_label}",
        ]
    ).strip() + "\n"


def build_config(
    *,
    parents: List[Dict[str, Any]],
    model: str,
    timeout_s: int,
    max_outstanding: int,
) -> Dict[str, Any]:
    # Match run_batches.py expectations: top-level {"max_outstanding", "batches":[{name, parents:{parents:[...]}}]}
    return {
        "schema_version": "v0.1.0",
        "generated_by": "tools/scc/ops/dispatch_from_task_tree.py",
        "generated_utc": _iso_now(),
        "max_outstanding": int(max_outstanding),
        "timeout_s": int(timeout_s),
        "defaults": {"model": str(model)},
        "batches": [{"name": "contract_scope_harden_v0_1_0", "parents": {"parents": parents}}],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a safe dispatch config from docs/DERIVED/task_tree.json")
    ap.add_argument("--task-tree", default="docs/DERIVED/task_tree.json")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="CONTRACTIZE_DISPATCH_CONFIG_V010")
    ap.add_argument("--out-config", default="", help="Output config path (default configs/scc/contractize_dispatch__<TaskCode>__YYYYMMDD.json)")
    ap.add_argument("--include-hardened", action="store_true", help="Include contracts that already look hardened (default: skip).")
    ap.add_argument("--model", default=os.environ.get("A2A_CODEX_MODEL", "gpt-5.2"))
    ap.add_argument("--timeout-s", type=int, default=1800)
    ap.add_argument("--max-outstanding", type=int, default=3)
    ap.add_argument("--emit-report", action="store_true", default=True)
    ap.add_argument("--run-mvm", action="store_true", help="Run mvm-verdict basic (proof of readiness)")
    ap.add_argument(
        "--embed-extra",
        action="append",
        default=[],
        help="Extra repo-relative paths to embed as read-only context (does NOT grant write access). Can be repeated.",
    )
    args = ap.parse_args()

    area = str(args.area).strip() or "control_plane"
    task_code = str(args.taskcode).strip() or "CONTRACTIZE_DISPATCH_CONFIG_V010"

    tree_path = Path(args.task_tree)
    if not tree_path.is_absolute():
        tree_path = (_REPO_ROOT / tree_path).resolve()
    if not tree_path.exists():
        print(json.dumps({"ok": False, "error": "missing_task_tree", "path": _to_repo_rel(tree_path)}, ensure_ascii=False))
        return 2

    tree = _read_json(tree_path)
    items = _iter_task_items(tree)

    picked: List[Dict[str, Any]] = []
    for t in items:
        task_id = str(t.get("task_id") or "").strip()
        contract_ref = str(t.get("contract_ref") or "").strip().replace("\\", "/")
        if not task_id or not contract_ref:
            continue
        # Prefer generated contracts (SSOT canonical).
        if not contract_ref.startswith("docs/ssot/04_contracts/"):
            continue
        abs_contract = (_REPO_ROOT / contract_ref).resolve()
        if not abs_contract.exists():
            continue
        # Prefer contracts that need scope widening: hardened baseline but trivial scope_allow.
        try:
            c = _read_json(abs_contract)
            sa = _normalize_scope_allow(c.get("scope_allow"))
            trivial = _is_trivial_contract_only_scope(scope_allow=sa or [], contract_ref=contract_ref) if sa else True
        except Exception:
            trivial = True
        hardened = _contract_looks_hardened(abs_contract)
        if not args.include_hardened and hardened:
            continue
        if args.include_hardened and (not trivial):
            # If it's already non-trivial scope, no need to scope-harden.
            continue
        picked.append(t)
        if len(picked) >= max(1, int(args.limit or 5)):
            break

    parents: List[Dict[str, Any]] = []
    extra_embed = [str(x).strip().replace("\\", "/") for x in (args.embed_extra or []) if str(x).strip()]
    for t in picked:
        task_id = str(t.get("task_id") or "").strip()
        task_label = str(t.get("task_label") or "").strip()
        contract_ref = str(t.get("contract_ref") or "").strip().replace("\\", "/")
        pid = f"SCOPE_{_safe_id(task_id)}"
        # Deterministic context (low token): SSOT search + snippet pack.
        task_text = build_parent_description(task_id=task_id, task_label=task_label, contract_ref=contract_ref)
        ssot_paths = _ssot_search_paths(task_text=task_text, limit=6)
        embed_paths = [
            contract_ref,
            "docs/START_HERE.md",
            "docs/ssot/registry.json",
            *ssot_paths,
            *extra_embed,
        ]
        # Prefer GOAL_BRIEF__LATEST if present (secretary output).
        gb = (_REPO_ROOT / "docs" / "DERIVED" / "secretary" / "GOAL_BRIEF__LATEST.md").resolve()
        if gb.exists():
            embed_paths.append(_to_repo_rel(gb))
        snippet_pack = _build_snippet_pack(
            area=area,
            task_code=task_code,
            parent_id=pid,
            task_text=task_text,
            allowed_globs=[contract_ref],
            embed_paths=embed_paths,
            max_total_chars=6000,
        )
        parents.append(
            {
                "id": pid,
                "title": f"Contract scope harden: {task_id}",
                "description": task_text,
                "role_id": "executor",
                "skills_required": ["PATCH_APPLY", "SELFTEST"],
                "isolate_worktree": True,
                "allowed_globs": [contract_ref],
                "embed_allowlisted_files": True,
                "embed_paths": [snippet_pack],
                "context_max_files": 1,
                "context_max_total_chars": 6000,
                "context_head_lines": 120,
                "context_tail_lines": 80,
                "require_changes": True,
            }
        )

    if not parents:
        print(json.dumps({"ok": False, "error": "no_tasks_with_contract_ref_found", "task_tree": _to_repo_rel(tree_path)}, ensure_ascii=False))
        return 3

    out_cfg = str(args.out_config).strip()
    if not out_cfg:
        out_cfg = f"configs/scc/contractize_dispatch__{task_code}__{_date_utc()}.json"
    out_cfg_path = Path(out_cfg)
    if not out_cfg_path.is_absolute():
        out_cfg_path = (_REPO_ROOT / out_cfg_path).resolve()

    cfg = build_config(parents=parents, model=str(args.model), timeout_s=int(args.timeout_s), max_outstanding=int(args.max_outstanding))
    _write_json(out_cfg_path, cfg)

    result = {
        "ok": True,
        "task_code": task_code,
        "area": area,
        "task_tree": _to_repo_rel(tree_path),
        "out_config": _to_repo_rel(out_cfg_path),
        "picked": [{"task_id": str(t.get("task_id")), "contract_ref": str(t.get("contract_ref"))} for t in picked],
        "parents_count": len(parents),
        "ts_utc": _iso_now(),
    }

    if args.emit_report:
        artifacts = _artifacts_dir(area, task_code)
        artifacts.mkdir(parents=True, exist_ok=True)
        # copy config into artifacts as evidence
        cfg_copy = artifacts / out_cfg_path.name
        try:
            shutil.copyfile(out_cfg_path, cfg_copy)
        except Exception:
            cfg_copy = None
        _write_json(artifacts / "dispatch_from_task_tree_summary.json", result)
        _write_text(artifacts / "selftest.log", f"{task_code} dispatch_from_task_tree\nEXIT_CODE=0\n")

        report_evidence = [
            f"docs/REPORT/{area}/artifacts/{task_code}/dispatch_from_task_tree_summary.json",
            f"docs/REPORT/{area}/artifacts/{task_code}/selftest.log",
        ]
        if cfg_copy is not None:
            report_evidence.append(f"docs/REPORT/{area}/artifacts/{task_code}/{cfg_copy.name}")

        report = _report_path(area, task_code)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            "\n".join(
                [
                    f"# REPORT__{task_code}",
                    "",
                    f"- TaskCode: {task_code}",
                    f"- Area: {area}",
                    f"- Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                    "",
                    "## Evidence Paths",
                    *[f"- {p}" for p in report_evidence],
                    "",
                    "## Next",
                    f"- Run dispatch: `python tools/scc/automation/run_batches.py --config {_to_repo_rel(out_cfg_path)}`",
                    "",
                ]
            ),
            encoding="utf-8",
            errors="replace",
        )

    if args.run_mvm:
        env = dict(os.environ)
        env["TASK_CODE"] = task_code
        env["AREA"] = area
        p = subprocess.run([sys.executable, "tools/ci/mvm-verdict.py", "--case", "basic"], cwd=str(_REPO_ROOT), env=env)
        return int(p.returncode)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
