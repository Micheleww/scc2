from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> Any:
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


def _dump_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")


def _render_board_md(board: Dict[str, Any]) -> str:
    lines = [
        "# Parent Task Goal Board",
        "",
        "Purpose: sidecar list of parent-task goals for continuous review and follow-up generation.",
        "Rule: If goal met, mark as met with evidence. If not met, mark needs_followup and add new parent task ids.",
        "",
        f"Generated at (UTC): {board.get('generated_at_utc')}",
        "",
        "## Goals",
    ]

    for item in board.get("items", []):
        lines += [
            f"- {item.get('parent_task_id')} | {item.get('title')}",
            f"- Goal: {item.get('goal')}",
            f"- Status: {item.get('status')}",
            f"- Evidence: {', '.join(item.get('evidence') or []) or '(add links)'}",
            f"- Followups: {', '.join(item.get('followups') or []) or '(add parent_task_id if needed)'}",
            "",
        ]

    return "\\n".join(lines) + "\\n"


def _make_followup(parent: Dict[str, Any], stamp: str) -> Dict[str, Any]:
    risk = parent.get("risk_level") or "P1"
    base_id = parent.get("parent_task_id", "UNKNOWN")
    followup_id = f"{risk}_PARENT__FOLLOWUP__{base_id}__{stamp}"
    title = parent.get("title", "Parent Task")
    goal = parent.get("goal", "")

    return {
        "parent_task_id": followup_id,
        "title": f"Follow-up: {title}",
        "goal": f"Address unmet goal: {goal}",
        "scope_allow": parent.get("scope_allow", []) or ["docs/", "tools/"],
        "constraints": (parent.get("constraints", []) or []) + [
            "Follow-up generated automatically; refine scope before execution"
        ],
        "success_criteria": (parent.get("success_criteria", []) or []) + [
            "Goal board marks this objective as met with evidence"
        ],
        "risk_level": risk,
        "acceptance_tests": parent.get("acceptance_tests", []) or [
            "Manual: review evidence and mark goal met"
        ],
        "execution_mode": parent.get("execution_mode", "ifcli_headless"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=r"C:\scc\scc-top\docs\TASKS\backlog\parent_task_goal_board.json")
    ap.add_argument("--parents", default=r"C:\scc\scc-top\docs\TASKS\backlog\parent_tasks.json")
    ap.add_argument("--report-dir", default=r"C:\scc\scc-top\docs\REPORT\control_plane")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    board_path = Path(args.board)
    parents_path = Path(args.parents)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    if not board_path.exists():
        raise SystemExit(f"Missing board: {board_path}")
    if not parents_path.exists():
        raise SystemExit(f"Missing parents: {parents_path}")

    board = _load_json(board_path)
    parents = _load_json(parents_path)

    parent_by_id = {p.get("parent_task_id"): p for p in parents}
    existing_ids = set(parent_by_id.keys())

    now = _utc_now()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")

    added = []
    updated_items: List[Dict[str, Any]] = []

    for item in board.get("items", []):
        item["last_review_utc"] = now
        status = item.get("status")
        if status != "needs_followup":
            updated_items.append(item)
            continue

        followups = item.get("followups") or []
        if followups:
            updated_items.append(item)
            continue

        parent_id = item.get("parent_task_id")
        parent = parent_by_id.get(parent_id)
        if not parent:
            updated_items.append(item)
            continue

        followup = _make_followup(parent, stamp)
        if followup["parent_task_id"] in existing_ids:
            updated_items.append(item)
            continue

        existing_ids.add(followup["parent_task_id"])
        parents.append(followup)
        added.append(followup)
        item["followups"] = [followup["parent_task_id"]]
        updated_items.append(item)

    board["generated_at_utc"] = now
    board["items"] = updated_items

    report_path = report_dir / f"REPORT__PARENT_TASK_GOAL_REVIEW__{stamp}.md"
    report_lines = [
        f"# Parent Task Goal Review Report ({stamp})",
        "",
        f"- Generated at (UTC): {now}",
        f"- Added followups: {len(added)}",
        f"- Board: {board_path}",
        f"- Parents: {parents_path}",
        "",
        "## Added Followups",
    ]
    for f in added:
        report_lines.append(f"- {f['parent_task_id']}: {f['title']}")
    report_lines += [
        "",
        "## Notes",
        "- Only items with status=needs_followup and empty followups generate new parent tasks.",
    ]

    if not args.dry_run:
        _dump_json(parents_path, parents)
        _dump_json(board_path, board)
        board_md_path = board_path.with_suffix('.md')
        board_md_path.write_text(_render_board_md(board), encoding="utf-8")
        report_path.write_text("\\n".join(report_lines) + "\\n", encoding="utf-8")

    print(f"added_followups={len(added)}")
    print(f"report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
