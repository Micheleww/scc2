#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Evidence Triplet Helper (v0.1.0)

Produces the mandatory "triplet" for fail-closed guard:
- docs/REPORT/<area>/REPORT__<TaskCode>__YYYYMMDD.md
- docs/REPORT/<area>/artifacts/<TaskCode>/selftest.log (must include EXIT_CODE=0)
- docs/REPORT/<area>/artifacts/<TaskCode>/evidence_hashes.json

Design:
- deterministic, no network, no LLM
- does not scan the whole repo: hashes only artifacts dir and the report itself
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _sha256_file(path: Path) -> Tuple[str, int]:
    h = hashlib.sha256()
    b = path.read_bytes()
    h.update(b)
    return h.hexdigest(), len(b)


def _norm_rel(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _artifacts_dir(repo_root: Path, *, area: str, taskcode: str) -> Path:
    return (repo_root / "docs" / "REPORT" / area / "artifacts" / taskcode).resolve()


def _report_path(repo_root: Path, *, area: str, taskcode: str, date_yyyymmdd: str) -> Path:
    return (repo_root / "docs" / "REPORT" / area / f"REPORT__{taskcode}__{date_yyyymmdd}.md").resolve()


def _write_selftest_log(path: Path, *, exit_code: int) -> None:
    lines = [
        f"TS_UTC={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"EXIT_CODE={int(exit_code)}",
    ]
    _write_text(path, "\n".join(lines).strip() + "\n")


def _hash_dir(repo_root: Path, artifacts_dir: Path) -> Dict[str, Dict[str, Any]]:
    hashes: Dict[str, Dict[str, Any]] = {}
    if not artifacts_dir.exists():
        return hashes
    for p in artifacts_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = _norm_rel(repo_root, p)
        sha, size = _sha256_file(p)
        hashes[rel] = {"sha256": sha, "size": size}
    return hashes


def _maybe_run_parent_task_hook(repo_root: Path, report_path: Path) -> None:
    cfg_path = repo_root / "tools" / "scc" / "ops" / "report_hook_config.json"
    hook_script = repo_root / "tools" / "scc" / "ops" / "report_to_parent_tasks_hook.py"
    goal_hook = repo_root / "tools" / "scc" / "ops" / "goal_status_to_parent_tasks.py"
    rollup_hook = repo_root / "tools" / "scc" / "ops" / "goal_status_rollup.py"
    board_hook = repo_root / "tools" / "scc" / "ops" / "parent_tasks_to_board_hook.py"
    scan_hook = repo_root / "tools" / "scc" / "ops" / "scan_hook_runner.py"
    if not cfg_path.exists() or not hook_script.exists():
        return
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return
    if not bool(cfg.get("enabled", False)):
        return
    if not bool(cfg.get("parent_tasks", True)):
        return

    cmd = [sys.executable, str(hook_script), "--report-path", str(report_path)]
    if bool(cfg.get("apply", True)):
        cmd.append("--apply")
    max_new = cfg.get("max_new")
    if isinstance(max_new, int) and max_new > 0:
        cmd += ["--max-new", str(max_new)]
    default_risk = cfg.get("default_risk")
    if isinstance(default_risk, str) and default_risk.strip():
        cmd += ["--default-risk", default_risk.strip().upper()]

    try:
        subprocess.run(cmd, cwd=str(repo_root), check=False, capture_output=True, text=True, timeout=30)
    except Exception:
        return

    # Optional: goal/status -> parent tasks flow (no dispatch)
    if bool(cfg.get("goal_review_on_report", False)) and goal_hook.exists():
        match_list = cfg.get("goal_review_match") or []
        try:
            cmd2 = [sys.executable, str(goal_hook), "--report-path", str(report_path)]
            if bool(cfg.get("apply", True)):
                cmd2.append("--apply")
            for m in match_list:
                if isinstance(m, str) and m.strip():
                    cmd2 += ["--match", m.strip()]
            subprocess.run(cmd2, cwd=str(repo_root), check=False, capture_output=True, text=True, timeout=30)
        except Exception:
            return

    # Optional: status rollup trigger (only rollup report can trigger goal->parent tasks)
    if bool(cfg.get("status_rollup_on_report", False)) and rollup_hook.exists():
        try:
            patterns = cfg.get("status_rollup_match") or []
            report_text = report_path.read_text(encoding="utf-8", errors="replace")
            target = (str(report_path) + "\n" + report_text[:2000]).lower()
            if patterns:
                hit = any(str(p).lower() in target for p in patterns)
            else:
                hit = False
            if hit:
                cmd3 = [sys.executable, str(rollup_hook), "--apply", "--trigger"]
                subprocess.run(cmd3, cwd=str(repo_root), check=False, capture_output=True, text=True, timeout=60)
        except Exception:
            pass

    # Optional: parent_tasks -> board + split + dispatch
    if bool(cfg.get("board_hook_on_report", False)) and board_hook.exists():
        try:
            cmd4 = [
                sys.executable,
                str(board_hook),
                "--parents",
                str(cfg.get("parents", r"C:\scc\scc-top\docs\TASKS\backlog\parent_tasks.json")),
                "--base",
                str(cfg.get("board_hook_base", "http://127.0.0.1:18788")),
                "--max-new",
                str(cfg.get("board_hook_max_new", 50)),
                "--area",
                str(cfg.get("board_hook_area", "control_plane")),
                "--runner",
                str(cfg.get("board_hook_runner", "external")),
                "--role",
                str(cfg.get("board_hook_role", "designer")),
            ]
            if bool(cfg.get("board_hook_apply", True)):
                cmd4.append("--apply")
            if bool(cfg.get("board_hook_split", True)):
                cmd4.append("--split")
            if bool(cfg.get("board_hook_dispatch", True)):
                cmd4.append("--dispatch")
            for ex in (cfg.get("board_hook_allowed_executors") or []):
                cmd4 += ["--allowed-executors", str(ex)]
            for model in (cfg.get("board_hook_allowed_models") or []):
                cmd4 += ["--allowed-models", str(model)]
            subprocess.run(cmd4, cwd=str(repo_root), check=False, capture_output=True, text=True, timeout=60)
        except Exception:
            return

    # Optional: scan hook runner (deterministic audits triggered by reports)
    if bool(cfg.get("scan_hook_on_report", False)) and scan_hook.exists():
        try:
            scan_cfg = cfg.get("scan_hook_config") or str(repo_root / "tools" / "scc" / "ops" / "scan_hook_config.json")
            cmd5 = [
                sys.executable,
                str(scan_hook),
                "--report-path",
                str(report_path),
                "--config",
                str(scan_cfg),
            ]
            subprocess.run(cmd5, cwd=str(repo_root), check=False, capture_output=True, text=True, timeout=120)
        except Exception:
            return


def main() -> int:
    ap = argparse.ArgumentParser(description="Create/refresh the evidence triplet (fail-closed)")
    ap.add_argument("--taskcode", required=True)
    ap.add_argument("--area", default=os.environ.get("AREA", "control_plane"))
    ap.add_argument("--title", default="")
    ap.add_argument("--notes", default="")
    ap.add_argument("--evidence", action="append", default=[], help="Add an evidence path bullet (must be under docs/REPORT/<area>/artifacts/<TaskCode>/)")
    ap.add_argument("--exit-code", type=int, default=0)
    ap.add_argument("--artifacts-dir", default="", help="Override artifacts dir (repo-relative). Default uses docs/REPORT/<area>/artifacts/<TaskCode>/")
    ap.add_argument("--report-path", default="", help="Override report path (repo-relative). Default uses docs/REPORT/<area>/REPORT__<TaskCode>__YYYYMMDD.md")
    args = ap.parse_args()

    repo_root = _repo_root()
    taskcode = str(args.taskcode).strip()
    area = str(args.area).strip() or "control_plane"
    date_yyyymmdd = time.strftime("%Y%m%d", time.gmtime())

    artifacts_dir = _artifacts_dir(repo_root, area=area, taskcode=taskcode)
    if str(args.artifacts_dir or "").strip():
        artifacts_dir = Path(str(args.artifacts_dir))
        if not artifacts_dir.is_absolute():
            artifacts_dir = (repo_root / artifacts_dir).resolve()

    report_path = _report_path(repo_root, area=area, taskcode=taskcode, date_yyyymmdd=date_yyyymmdd)
    if str(args.report_path or "").strip():
        report_path = Path(str(args.report_path))
        if not report_path.is_absolute():
            report_path = (repo_root / report_path).resolve()

    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Always write/update selftest.log
    _write_selftest_log(artifacts_dir / "selftest.log", exit_code=int(args.exit_code))

    # Build report that references evidence paths (guard requires referenced docs/REPORT paths to be in evidence list).
    title = str(args.title).strip() or f"REPORT__{taskcode}"
    notes = str(args.notes).strip()
    evidence_paths: List[str] = []
    for ev in (args.evidence or []):
        evs = str(ev).strip().replace("\\", "/")
        if not evs:
            continue
        evidence_paths.append(evs)

    # Default evidence: list key files under artifacts dir.
    default_evidence = [
        f"docs/REPORT/{area}/artifacts/{taskcode}/selftest.log",
        f"docs/REPORT/{area}/artifacts/{taskcode}/evidence_hashes.json",
    ]
    evidence_paths = default_evidence + [p for p in evidence_paths if p not in set(default_evidence)]

    md: List[str] = []
    md.append(f"# {title}")
    md.append("")
    md.append(f"- TaskCode: {taskcode}")
    md.append(f"- Area: {area}")
    md.append(f"- Date: {time.strftime('%Y-%m-%d', time.gmtime())}")
    md.append("")
    md.append("## Evidence Paths")
    for p in evidence_paths:
        md.append(f"- {p}")
    if notes:
        md.append("")
        md.append("## Notes")
        md.append(notes)
    _write_text(report_path, "\n".join(md).strip() + "\n")

    # Hash manifest (artifacts dir + report file)
    hashes = _hash_dir(repo_root, artifacts_dir)
    try:
        rel_report = _norm_rel(repo_root, report_path)
        sha, size = _sha256_file(report_path)
        hashes[rel_report] = {"sha256": sha, "size": size}
    except Exception:
        pass
    _write_json(artifacts_dir / "evidence_hashes.json", hashes)

    _maybe_run_parent_task_hook(repo_root, report_path)

    print(str(report_path))
    print(str(artifacts_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
