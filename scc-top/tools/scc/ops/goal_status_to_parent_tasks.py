#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Goal + Status Report -> Parent Tasks

Trigger:
- Invoked by evidence_triplet.py when a matching status report is generated.

Behavior:
- Marks active goals with no evidence as needs_followup.
- Runs parent_task_goal_review.py to add follow-up parent tasks.
- Writes a small audit report (docs/REPORT/control_plane).

Design:
- deterministic, no network, no LLM
- does NOT split/dispatch board tasks
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_lenient_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(text)
    except Exception:
        last_obj = text.rfind("}")
        last_arr = text.rfind("]")
        cut = max(last_obj, last_arr)
        if cut > 0:
            return json.loads(text[: cut + 1])
        raise


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _match_report(report_path: Path, report_text: str, patterns: List[str]) -> bool:
    target = (str(report_path) + "\n" + (report_text or "")[:2000]).lower()
    return any((p or "").lower() in target for p in patterns)


def _extract_scope(report_path: Path, report_text: str) -> str:
    name = report_path.name.lower()
    if "full" in name or "__full__" in name:
        return "full"
    if "block" in name or "__block__" in name:
        return "block"

    for line in (report_text or "").splitlines():
        line_l = line.strip().lower()
        if line_l.startswith("- scope:") or line_l.startswith("scope:"):
            if "full" in line_l:
                return "full"
            if "block" in line_l:
                return "block"
    return "unknown"


def _extract_coverage(report_text: str) -> str:
    coverage = "unknown"
    for line in (report_text or "").splitlines():
        line_l = line.strip().lower()
        if line_l.startswith("- goal coverage:") or line_l.startswith("goal coverage:"):
            coverage = line.split(":", 1)[1].strip().lower()
            break
        if line_l.startswith("- coverage:") or line_l.startswith("coverage:"):
            coverage = line.split(":", 1)[1].strip().lower()
            break
    if coverage in {"full", "partial", "none"}:
        return coverage
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Goal/status -> parent task hook (no dispatch)")
    ap.add_argument("--report-path", required=True)
    ap.add_argument("--board", default=r"C:\scc\scc-top\docs\TASKS\backlog\parent_task_goal_board.json")
    ap.add_argument("--parents", default=r"C:\scc\scc-top\docs\TASKS\backlog\parent_tasks.json")
    ap.add_argument("--report-dir", default=r"C:\scc\scc-top\docs\REPORT\control_plane")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--match", action="append", default=[])
    ap.add_argument("--require-scope", default="")
    ap.add_argument("--require-coverage", default="")
    args = ap.parse_args()

    repo_root = _repo_root()
    report_path = Path(args.report_path)
    if not report_path.is_absolute():
        report_path = (repo_root / report_path).resolve()
    if not report_path.exists():
        raise SystemExit(f"Report not found: {report_path}")

    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    patterns = args.match or []
    if patterns and not _match_report(report_path, report_text, patterns):
        print("[hook] Report does not match patterns; skip.")
        return 0
    scope = _extract_scope(report_path, report_text)
    coverage = _extract_coverage(report_text)
    require_scope = str(args.require_scope or "").strip().lower()
    require_coverage = str(args.require_coverage or "").strip().lower()
    scope_skip = bool(require_scope and scope != require_scope)
    coverage_skip = bool(require_coverage and coverage != require_coverage)
    if scope_skip:
        print(f"[hook] Report scope={scope} does not meet require_scope={require_scope}; will skip task generation.")
    if coverage_skip:
        print(f"[hook] Report coverage={coverage} does not meet require_coverage={require_coverage}; will skip task generation.")

    board_path = Path(args.board)
    parents_path = Path(args.parents)
    if not board_path.exists() or not parents_path.exists():
        raise SystemExit("Missing board or parents")

    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    changed = 0
    added = 0
    out = ""

    if not scope_skip and not coverage_skip:
        board = _load_lenient_json(board_path)
        for item in board.get("items", []):
            if item.get("status") == "active" and not (item.get("evidence") or []):
                item["status"] = "needs_followup"
                changed += 1
            item["last_review_utc"] = now
        board["generated_at_utc"] = now
        if args.apply:
            _write_json(board_path, board)

        # Run parent_task_goal_review.py to append follow-up parent tasks
        cmd = [sys.executable, "tools/scc/ops/parent_task_goal_review.py"]
        if not args.apply:
            cmd.append("--dry-run")
        proc = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
        out = (proc.stdout or "") + "\n" + (proc.stderr or "")
        for line in (proc.stdout or "").splitlines():
            if line.startswith("added_followups="):
                try:
                    added = int(line.split("=", 1)[1].strip())
                except Exception:
                    pass

    # Audit report (always written to show hook activity)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    audit_path = report_dir / f"REPORT__GOAL_STATUS_TO_PARENT__{stamp}.md"
    lines = [
        f"# Goal Status -> Parent Tasks ({stamp})",
        "",
        f"- Generated at (UTC): {now}",
        f"- Source report: {report_path}",
        f"- Scope: {scope}",
        f"- Goal Coverage: {coverage}",
        f"- Require Scope: {require_scope or '(none)'}",
        f"- Require Coverage: {require_coverage or '(none)'}",
        f"- Goals marked needs_followup: {changed}",
        f"- Followups added: {added}",
        f"- Apply: {bool(args.apply)}",
        "",
        "## Hook Output (last lines)",
    ]
    tail = "\n".join(out.strip().splitlines()[-12:]) if out.strip() else "(no output)"
    lines.append("```text")
    lines.append(tail)
    lines.append("```")
    audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    if scope_skip or coverage_skip:
        print(f"[hook] goal_status_to_parent_tasks: skipped (scope={scope} require={require_scope} coverage={coverage} require_coverage={require_coverage})")
        return 0

    print(f"[hook] goal_status_to_parent_tasks: changed={changed} added={added} apply={bool(args.apply)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
