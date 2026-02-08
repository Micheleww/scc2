#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")


def _find_latest_automation_run(repo_root: Path) -> Optional[Path]:
    base = repo_root / "artifacts" / "scc_state" / "automation_runs"
    if not base.exists():
        return None
    dirs = [p for p in base.iterdir() if p.is_dir() and p.name.isdigit()]
    if not dirs:
        return None
    return sorted(dirs, key=lambda p: p.name)[-1]


def _extract_codex_run_id(resp: Dict[str, Any]) -> Optional[str]:
    r = resp.get("response") if isinstance(resp.get("response"), dict) else {}
    rid = r.get("run_id")
    return str(rid) if rid else None


def _parse_workspace_diff_files(diff_text: str) -> List[str]:
    files: List[str] = []
    for m in re.finditer(r"^diff --git a/(.+?) b/(.+?)$", diff_text, flags=re.M):
        a = m.group(1).strip()
        b = m.group(2).strip()
        # prefer b path
        files.append(b or a)
    return sorted(set(files))


def _try_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _try_read_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(_try_read_text(path) or "{}")
    except Exception:
        return {}


def _git_head() -> str:
    try:
        p = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return (p.stdout or "").strip()
    except Exception:
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="SCC delegation audit (CodexCLI parent batches)")
    ap.add_argument("--automation-run-id", default="", help="artifacts/scc_state/automation_runs/<run_id>")
    ap.add_argument("--response-file", default="", help="Path to 01__*__response.json")
    ap.add_argument("--out", default="", help="Output report path (md)")
    args = ap.parse_args()

    repo_root = _repo_root()
    run_dir: Optional[Path] = None
    resp_file: Optional[Path] = None

    if args.response_file.strip():
        resp_file = Path(args.response_file).resolve()
    elif args.automation_run_id.strip():
        run_dir = (repo_root / "artifacts" / "scc_state" / "automation_runs" / args.automation_run_id.strip()).resolve()
        resp_file = run_dir / "01__ssot_autonomy_v0_1_0__response.json"
    else:
        run_dir = _find_latest_automation_run(repo_root)
        if run_dir is not None:
            resp_file = run_dir / "01__ssot_autonomy_v0_1_0__response.json"

    if resp_file is None or not resp_file.exists():
        print("delegation_audit: response file not found", flush=True)
        return 2

    resp = _read_json(resp_file)
    response = resp.get("response") if isinstance(resp.get("response"), dict) else {}
    codex_run_id = _extract_codex_run_id(resp)
    codex_dir = None
    if codex_run_id:
        codex_dir = (repo_root / "artifacts" / "codexcli_remote_runs" / codex_run_id).resolve()

    workspace_diff = ""
    workspace_files: List[str] = []
    if codex_dir is not None:
        diff_path = codex_dir / "workspace.diff"
        workspace_diff = _try_read_text(diff_path)
        workspace_files = _parse_workspace_diff_files(workspace_diff)

    stamp = _now_stamp()
    out_path = Path(args.out).resolve() if args.out.strip() else (repo_root / "artifacts" / "scc_state" / "delegation_audits" / f"delegation_audit__{stamp}.md")
    _safe_mkdir(out_path.parent)

    head = _git_head()
    lines: List[str] = []
    lines.append("# Delegation Audit Report")
    lines.append("")
    lines.append(f"- generated_utc: `{datetime.now(timezone.utc).isoformat()}`")
    lines.append(f"- git_head: `{head}`")
    lines.append(f"- automation_response: `{resp_file}`")
    if codex_dir is not None:
        lines.append(f"- codex_run_dir: `{codex_dir}`")
    lines.append("")

    # Parent results (exit codes)
    results = response.get("results") if isinstance(response.get("results"), list) else []
    lines.append("## Parent Results")
    if not results:
        lines.append("- (no results found in response)")
    else:
        for it in results:
            if not isinstance(it, dict):
                continue
            pid = str(it.get("id") or "")
            ec = it.get("exit_code")
            ad = it.get("artifacts_dir")
            lines.append(f"- {pid}: exit_code={ec} artifacts_dir=`{ad}`")
    lines.append("")

    # Scope enforcement (worktree isolation + allowlist)
    lines.append("## Scope Enforcement")
    if not results:
        lines.append("- (no results to audit)")
    else:
        any_scope = False
        for it in results:
            if not isinstance(it, dict):
                continue
            pid = str(it.get("id") or "")
            ad = str(it.get("artifacts_dir") or "")
            if not ad:
                lines.append(f"- {pid}: (missing artifacts_dir)")
                continue
            scope_path = Path(ad) / "scope_enforcement.json"
            if not scope_path.exists():
                lines.append(f"- {pid}: (no scope_enforcement.json)")
                continue
            any_scope = True
            meta = _try_read_json(scope_path)
            allowed = meta.get("allowed_globs") if isinstance(meta.get("allowed_globs"), list) else []
            violations = meta.get("violations") if isinstance(meta.get("violations"), list) else []
            apply_ok = meta.get("apply_ok", None)
            copied = meta.get("copied_untracked_files") if isinstance(meta.get("copied_untracked_files"), list) else []
            copy_failures = meta.get("copy_failures") if isinstance(meta.get("copy_failures"), list) else []
            lines.append(
                f"- {pid}: isolate={bool(meta.get('isolate_worktree'))} allowed_globs={len(allowed)} "
                f"violations={len(violations)} apply_ok={apply_ok} copied_untracked={len(copied)}"
            )
            if violations:
                for v in violations[:40]:
                    lines.append(f"  - violation: `{v}`")
                if len(violations) > 40:
                    lines.append(f"  - ...(truncated) total={len(violations)}")
            if copy_failures:
                for v in copy_failures[:20]:
                    lines.append(f"  - copy_failure: `{v}`")
                if len(copy_failures) > 20:
                    lines.append(f"  - ...(truncated) total={len(copy_failures)}")
        if not any_scope:
            lines.append("- (no scope_enforcement.json found)")
    lines.append("")

    lines.append("## Workspace Diff Files")
    if not workspace_files:
        lines.append("- (no workspace.diff or no diff entries)")
    else:
        for f in workspace_files:
            lines.append(f"- `{f}`")
    lines.append("")

    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(str(out_path), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
