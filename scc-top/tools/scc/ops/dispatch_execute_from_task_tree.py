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


def _contract_looks_hardened(path: Path) -> bool:
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


def _normalize_scope_allow(scope_allow: Any) -> Optional[List[str]]:
    if isinstance(scope_allow, list):
        items = [str(x).strip().replace("\\", "/") for x in scope_allow if str(x).strip()]
        return items or None
    if isinstance(scope_allow, str):
        s = scope_allow.strip()
        if not s or s.lower().startswith("tbd"):
            return None
        parts = [p.strip() for p in s.replace("\\", "/").split(",")]
        items = [p for p in parts if p]
        return items or None
    return None


def _is_trivial_contract_only_scope(*, scope_allow: List[str], contract_ref: str) -> bool:
    items = [str(x).strip().replace("\\", "/") for x in (scope_allow or []) if str(x).strip()]
    if not items:
        return True
    cref = str(contract_ref or "").strip().replace("\\", "/")
    if not cref:
        return False
    # If scope only includes the contract file itself, it's not an executable code task yet.
    if len(items) == 1 and items[0] == cref:
        return True
    # If all allowlist entries are within generated contract dir, treat as non-executable.
    if all(x.startswith("docs/ssot/04_contracts/generated/") for x in items):
        return True
    return False


def _filter_scope_allow_for_executor(scope_allow: List[str]) -> List[str]:
    """
    Executor MUST NOT write verdict artifacts directly.

    Keep evidence directory globs, but remove explicit verdict.json targets so only
    deterministic verifier (or designated verifier role) can write the verdict file.
    """
    out: List[str] = []
    for p in scope_allow or []:
        p2 = str(p).strip().replace("\\", "/")
        if not p2:
            continue
        if p2.endswith("/verdict.json"):
            continue
        if p2.startswith("docs/REPORT/"):
            continue
        out.append(p2)
    # stable de-dupe
    seen = set()
    return [p for p in out if not (p in seen or seen.add(p))]


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
    artifacts = _artifacts_dir(area, task_code)
    artifacts.mkdir(parents=True, exist_ok=True)
    out_path = (artifacts / f"snippet_pack__{_safe_id(parent_id)}.md").resolve()
    args = [sys.executable, "tools/scc/ops/deterministic_snippet_pack.py", "--task-text", str(task_text or ""), "--out", _maybe_repo_rel(out_path)]
    for g in (allowed_globs or []):
        gg = str(g).strip().replace("\\", "/")
        if gg:
            args.extend(["--allowed-glob", gg])
    for p0 in (embed_paths or []):
        pp = str(p0).strip().replace("\\", "/")
        if pp:
            args.extend(["--embed-path", pp])
    # Keep executor/verifier context small to control token burn.
    args.extend(["--max-total-chars", str(int(max_total_chars or 12000)), "--max-files", "6"])
    subprocess.run(args, cwd=str(_REPO_ROOT), check=False)
    return _to_repo_rel(out_path)


def _build_execute_description(*, task_id: str, contract_ref: str) -> str:
    return "\n".join(
        [
            "TASK: CONTRACT_EXECUTE",
            "",
            f"task_id: {task_id}",
            f"contract_ref: {contract_ref}",
            "",
            "Goal:",
            "- Implement the contract goal by editing only within contract.scope_allow.",
            "- Do NOT run any shell/PowerShell commands; deterministic verifier will run acceptance checks.",
            "",
            "Rules (mandatory):",
            "- MUST stay within allowlisted paths (scope_allow).",
            "- MUST NOT write under `docs/REPORT/**` (evidence is verifier-owned).",
            "- MUST NOT create or modify any `*/verdict.json` (verdict is verifier-owned).",
            "- MUST follow SSOT: read `docs/START_HERE.md` then `docs/ssot/registry.json` when unsure.",
            "- MUST NOT create a second docs entrypoint.",
            "- If acceptance is not deterministic, STOP and report (do not guess).",
            "- You CANNOT edit the repo directly. You MUST either:",
            "  1) Output EXACTLY `NO_CHANGES` (no other text) if no changes are needed, OR",
            "  2) Output ONE `git apply` compatible unified diff patch.",
            "- If outputting a patch:",
            "  - Output ONLY the patch (no narration, no markdown/code fences).",
            "  - First line MUST be `diff --git a/<path> b/<path>`.",
            "  - Patch MUST be valid unified diff hunks and MUST end with a newline.",
            "",
            "Outputs (mandatory):",
            "- Changes must stay within scope_allow; verifier will run acceptance and write verdict/evidence.",
        ]
    ).strip() + "\n"


def _build_verify_description(*, task_id: str, contract_ref: str) -> str:
    return "\n".join(
        [
            "TASK: CONTRACT_VERIFY",
            "",
            f"task_id: {task_id}",
            f"contract_ref: {contract_ref}",
            "",
            "Goal:",
            "- Run contract.acceptance.checks exactly and report pass/fail with evidence.",
            "",
            "Rules (mandatory):",
            "- Do NOT edit code.",
            "- If checks are not executable, STOP and report.",
        ]
    ).strip() + "\n"


def build_config(*, parents: List[Dict[str, Any]], model: str, timeout_s: int, max_outstanding: int) -> Dict[str, Any]:
    return {
        "schema_version": "v0.1.0",
        "generated_by": "tools/scc/ops/dispatch_execute_from_task_tree.py",
        "max_outstanding": int(max_outstanding),
        "timeout_s": int(timeout_s),
        "batches": [{"name": "execute_from_task_tree_v0_1_0", "parents": {"parents": parents}}],
        "defaults": {"model": str(model)},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a safe EXECUTE+VERIFY dispatch config from docs/DERIVED/task_tree.json (v0.1.0)")
    ap.add_argument("--task-tree", default="docs/DERIVED/task_tree.json")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="DISPATCH_EXECUTE_FROM_TASK_TREE_V010")
    ap.add_argument("--limit", type=int, default=2, help="How many tasks to pick (default: 2).")
    ap.add_argument("--model", default=os.environ.get("A2A_CODEX_MODEL", "gpt-5.2"))
    ap.add_argument("--timeout-s", type=int, default=int(os.environ.get("A2A_CODEX_TIMEOUT_SEC", "1800")))
    ap.add_argument("--max-outstanding", type=int, default=int(os.environ.get("SCC_AUTOMATION_MAX_OUTSTANDING", "2")))
    ap.add_argument("--out-config", default="", help="Output config path (default configs/scc/execute_dispatch__<TaskCode>__YYYYMMDD.json).")
    ap.add_argument("--emit-report", action="store_true", default=True)
    ap.add_argument("--embed-extra", action="append", default=[], help="Extra repo-relative embed paths (read-only). Can be repeated.")
    ap.add_argument(
        "--include-llm-verify",
        action="store_true",
        default=False,
        help="Also emit a LLM verifier parent. Default is off because deterministic run_contract_task.py is the baseline verifier.",
    )
    args = ap.parse_args()

    area = str(args.area).strip() or "control_plane"
    task_code = str(args.taskcode).strip() or "DISPATCH_EXECUTE_FROM_TASK_TREE_V010"

    tree_path = Path(args.task_tree)
    if not tree_path.is_absolute():
        tree_path = (_REPO_ROOT / tree_path).resolve()
    if not tree_path.exists():
        print(json.dumps({"ok": False, "error": "missing_task_tree", "path": _to_repo_rel(tree_path)}, ensure_ascii=False))
        return 2

    tree = _read_json(tree_path)
    items = _iter_task_items(tree)

    picked: List[Tuple[str, str, List[str]]] = []
    for t in items:
        task_id = str(t.get("task_id") or "").strip()
        contract_ref = str(t.get("contract_ref") or "").strip().replace("\\", "/")
        if not task_id or not contract_ref:
            continue
        if not contract_ref.startswith("docs/ssot/04_contracts/"):
            continue
        abs_contract = (_REPO_ROOT / contract_ref).resolve()
        if not abs_contract.exists():
            continue
        if not _contract_looks_hardened(abs_contract):
            continue
        contract = _read_json(abs_contract)
        scope_allow = _normalize_scope_allow(contract.get("scope_allow"))
        if not scope_allow:
            continue
        if _is_trivial_contract_only_scope(scope_allow=scope_allow, contract_ref=contract_ref):
            continue
        picked.append((task_id, contract_ref, _filter_scope_allow_for_executor(scope_allow)))
        if len(picked) >= max(1, int(args.limit or 1)):
            break

    if not picked:
        print(json.dumps({"ok": False, "error": "no_executable_contracts_found", "task_tree": _to_repo_rel(tree_path)}, ensure_ascii=False))
        return 3

    extra_embed = [str(x).strip().replace("\\", "/") for x in (args.embed_extra or []) if str(x).strip()]

    parents: List[Dict[str, Any]] = []
    for task_id, contract_ref, scope_allow in picked:
        sid = _safe_id(task_id)
        exec_desc = _build_execute_description(task_id=task_id, contract_ref=contract_ref)
        ssot_paths = _ssot_search_paths(task_text=exec_desc, limit=6)
        # Embed a deterministic, minimal context set. Always include the contract + SSOT pointers.
        scope_embed: List[str] = []
        for p in scope_allow:
            p2 = str(p).strip().replace("\\", "/")
            if not p2 or "*" in p2:
                continue
            ap = (_REPO_ROOT / p2).resolve()
            if ap.exists() and ap.is_file():
                scope_embed.append(p2)
            if len(scope_embed) >= 4:
                break
        embed_paths = [contract_ref, "docs/START_HERE.md", "docs/ssot/registry.json", *ssot_paths, *scope_embed, *extra_embed]
        allowed_globs_ctx = [
            contract_ref,
            "docs/START_HERE.md",
            "docs/ssot/**",
            "docs/CANONICAL/**",
            *scope_allow,
        ]
        gb = (_REPO_ROOT / "docs" / "DERIVED" / "secretary" / "GOAL_BRIEF__LATEST.md").resolve()
        if gb.exists():
            embed_paths.append(_to_repo_rel(gb))
        snippet_pack = _build_snippet_pack(
            area=area,
            task_code=task_code,
            parent_id=f"EXEC_{sid}",
            task_text=exec_desc,
            allowed_globs=allowed_globs_ctx,
            embed_paths=embed_paths,
            max_total_chars=12000,
        )
        parents.append(
            {
                "id": f"EXEC_{sid}",
                "title": f"Execute contract: {task_id}",
                "description": exec_desc,
                "role_id": "executor",
                "skills_required": ["SHELL_READONLY", "SHELL_WRITE", "PATCH_APPLY", "SELFTEST"],
                "isolate_worktree": True,
                "allowed_globs": scope_allow,
                "embed_allowlisted_files": True,
                "embed_paths": [snippet_pack],
                "context_max_files": 1,
                "context_max_total_chars": 12000,
                "context_head_lines": 100,
                "context_tail_lines": 60,
                "require_changes": False,
            }
        )
        if bool(args.include_llm_verify):
            verify_desc = _build_verify_description(task_id=task_id, contract_ref=contract_ref)
            ssot_paths_v = _ssot_search_paths(task_text=verify_desc, limit=6)
            embed_paths_v = [contract_ref, "docs/START_HERE.md", "docs/ssot/registry.json", *ssot_paths_v, *scope_embed, *extra_embed]
            snippet_pack_v = _build_snippet_pack(
                area=area,
                task_code=task_code,
                parent_id=f"VERIFY_{sid}",
                task_text=verify_desc,
                allowed_globs=allowed_globs_ctx,
                embed_paths=embed_paths_v,
                max_total_chars=8000,
            )
            parents.append(
                {
                    "id": f"VERIFY_{sid}",
                    "title": f"Verify contract acceptance: {task_id}",
                    "description": verify_desc,
                    "role_id": "verifier",
                    "skills_required": ["SHELL_READONLY", "SELFTEST"],
                    "isolate_worktree": True,
                    "allowed_globs": scope_allow,
                    "embed_allowlisted_files": True,
                    "embed_paths": [snippet_pack_v],
                    "context_max_files": 1,
                    "context_max_total_chars": 8000,
                    "context_head_lines": 80,
                    "context_tail_lines": 50,
                    "require_changes": False,
                }
            )

    out_cfg = str(args.out_config).strip()
    if not out_cfg:
        out_cfg = f"configs/scc/execute_dispatch__{task_code}__{_date_utc()}.json"
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
        "picked": [{"task_id": tid, "contract_ref": cref, "scope_allow": scope} for tid, cref, scope in picked],
        "parents_count": len(parents),
        "ts_utc": _iso_now(),
    }

    if args.emit_report:
        artifacts = _artifacts_dir(area, task_code)
        artifacts.mkdir(parents=True, exist_ok=True)
        cfg_copy = artifacts / out_cfg_path.name
        try:
            shutil.copyfile(out_cfg_path, cfg_copy)
        except Exception:
            cfg_copy = None
        _write_json(artifacts / "dispatch_execute_from_task_tree_summary.json", result)
        _write_text(artifacts / "selftest.log", f"{task_code} dispatch_execute_from_task_tree\nEXIT_CODE=0\n")

        report_evidence = [
            f"docs/REPORT/{area}/artifacts/{task_code}/dispatch_execute_from_task_tree_summary.json",
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

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
