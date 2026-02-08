#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Report -> Parent Tasks Hook

Scans a REPORT__*.md for a follow-up section and appends derived parent tasks.
Design goals:
- deterministic, no network, no LLM
- safe: only acts when a specific section exists
- idempotent: skips existing tasks
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_lenient_json_array(path: Path) -> List[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"Invalid JSON array in {path}")
    return json.loads(text[start : end + 1])


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _slugify(text: str, max_len: int = 60) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text).strip("_").upper()
    if not cleaned:
        cleaned = "UNTITLED"
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("_")
    return cleaned


def _report_relative(repo_root: Path, report_path: Path) -> str:
    try:
        return str(report_path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(report_path).replace("\\", "/")


def _extract_followup_section(report_text: str) -> List[str]:
    lines = report_text.splitlines()
    tasks: List[str] = []
    in_section = False
    heading_re = re.compile(r"^##\s+(.*)$")
    for line in lines:
        heading = heading_re.match(line.strip())
        if heading:
            title = heading.group(1).strip().lower()
            in_section = any(
                key in title
                for key in (
                    "proposed follow-up parent tasks",
                    "proposed followup parent tasks",
                    "follow-up parent tasks",
                    "followup parent tasks",
                    "proposed parent tasks",
                    "follow-up tasks",
                    "followup tasks",
                )
            )
            continue
        if in_section:
            if line.strip().startswith("#"):
                break
            bullet = re.match(r"^\s*[-*]\s+(.*)$", line)
            if not bullet:
                bullet = re.match(r"^\s*\d+\.\s+(.*)$", line)
            if bullet:
                item = bullet.group(1).strip()
                if item:
                    tasks.append(item)
    return tasks


def _parse_task_line(line: str, default_risk: str) -> Tuple[str, str, str]:
    text = line.strip()
    risk = default_risk
    m = re.match(r"^\s*[\[\(]?(P[0-4])[\]\)]?\s*[:\-–]?\s*(.+)$", text, re.IGNORECASE)
    if m:
        risk = m.group(1).upper()
        text = m.group(2).strip()

    title = text
    goal = ""
    if " - " in text:
        title, goal = text.split(" - ", 1)
    elif ":" in text:
        title, goal = text.split(":", 1)

    title = title.strip()
    goal = goal.strip()
    if not goal:
        goal = f"Derived from report follow-up: {title}"

    return title, goal, risk


def _make_task_id(risk: str, title: str, report_rel: str, existing_ids: set[str]) -> str:
    base = f"{risk}_PARENT__FROM_REPORT__{_slugify(title)}"
    if base not in existing_ids:
        return base
    digest = hashlib.sha1(f"{report_rel}|{title}".encode("utf-8")).hexdigest()[:8]
    return f"{base}__{digest}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Hook: parse report follow-ups into parent tasks")
    ap.add_argument("--report-path", required=True)
    ap.add_argument("--parents", default=r"C:\scc\scc-top\docs\TASKS\backlog\parent_tasks.json")
    ap.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    ap.add_argument("--max-new", type=int, default=20)
    ap.add_argument("--default-risk", default="P1")
    args = ap.parse_args()

    repo_root = _repo_root()
    report_path = Path(args.report_path)
    if not report_path.is_absolute():
        report_path = (repo_root / report_path).resolve()
    if not report_path.exists():
        raise SystemExit(f"Report not found: {report_path}")

    report_text = report_path.read_text(encoding="utf-8", errors="replace")
    followups = _extract_followup_section(report_text)
    if not followups:
        print("[hook] No follow-up section found; nothing to do.")
        return 0

    parents_path = Path(args.parents)
    parents = _load_lenient_json_array(parents_path)
    existing_ids = {p.get("parent_task_id") for p in parents if p.get("parent_task_id")}
    existing_by_title = {(p.get("title") or "").strip().lower() for p in parents}

    report_rel = _report_relative(repo_root, report_path)
    new_tasks: List[Dict[str, Any]] = []
    for line in followups:
        if len(new_tasks) >= int(args.max_new):
            break
        title, goal, risk = _parse_task_line(line, default_risk=str(args.default_risk).upper())
        if not title:
            continue
        if title.strip().lower() in existing_by_title:
            continue
        task_id = _make_task_id(risk, title, report_rel, existing_ids)
        if task_id in existing_ids:
            continue

        task = {
            "parent_task_id": task_id,
            "title": title,
            "goal": goal,
            "scope_allow": [
                "docs/",
                "tools/",
                "reports/",
                "artifacts/",
            ],
            "constraints": [
                f"Source report: {report_rel}",
                "Generated by report hook; refine scope before execution",
                "Do not auto-execute; requires manual split/dispatch",
            ],
            "success_criteria": [
                "Required artifacts or reports exist",
                "Goal board marks this objective as met with evidence",
            ],
            "risk_level": risk,
            "acceptance_tests": [
                "Manual: review evidence and confirm completion",
            ],
            "execution_mode": "ifcli_headless",
        }
        new_tasks.append(task)
        existing_ids.add(task_id)
        existing_by_title.add(title.strip().lower())

    if not new_tasks:
        print("[hook] No new tasks after dedupe.")
        return 0

    if not args.apply:
        print("[hook] Dry-run (use --apply to write)")
        print(json.dumps(new_tasks, ensure_ascii=False, indent=2))
        return 0

    parents.extend(new_tasks)
    _write_json(parents_path, parents)
    print(f"[hook] Added {len(new_tasks)} parent task(s) from {report_rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
