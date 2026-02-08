#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Goal Status Rollup (Total Report)

Collects all "status review" reports and generates a rollup report.
Only the rollup report is allowed to trigger goal->parent task generation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _extract_generated_at(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith("- generated at (utc):"):
            return line.split(":", 1)[1].strip()
        if line.lower().startswith("generated at (utc):"):
            return line.split(":", 1)[1].strip()
    return ""


def _extract_scope(name: str, text: str) -> str:
    name_l = name.lower()
    if "full" in name_l or "__full__" in name_l:
        return "full"
    if "block" in name_l or "__block__" in name_l:
        return "block"
    for line in text.splitlines():
        line_l = line.strip().lower()
        if line_l.startswith("- scope:") or line_l.startswith("scope:"):
            if "full" in line_l:
                return "full"
            if "block" in line_l:
                return "block"
    return "unknown"


def _match_report(path: Path, text: str, patterns: List[str]) -> bool:
    target = (str(path) + "\n" + (text or "")[:4000]).lower()
    return any((p or "").lower() in target for p in patterns)


def _to_repo_rel(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")






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


def _load_lenient_json_array(path: Path) -> List[Dict[str, Any]]:
    data = _load_lenient_json(path)
    if isinstance(data, list):
        return data
    return []


def _slugify(text: str, max_len: int = 64) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_").upper()
    if not cleaned:
        cleaned = "UNTITLED"
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip("_")
    return cleaned


def _goal_tokens(item: Dict[str, Any]) -> List[str]:
    tokens = []
    for key in ("parent_task_id", "title", "goal"):
        val = str(item.get(key) or "").strip()
        if not val:
            continue
        if key == "goal":
            # use a short prefix to avoid overly long matches
            val = val[:80]
        tokens.append(val)
    return [t for t in tokens if len(t) >= 4]


def _compute_goal_coverage(board_path: Path, report_texts: List[str]) -> Tuple[str, int, int, float, List[Dict[str, str]]]:
    if not board_path.exists():
        return "unknown", 0, 0, 0.0, []
    board = _load_lenient_json(board_path)
    items = board.get("items", []) if isinstance(board, dict) else []
    report_blob = "\n".join(report_texts).lower()

    covered = 0
    uncovered: List[Dict[str, str]] = []
    total = len(items)
    for item in items:
        tokens = _goal_tokens(item)
        matched = any(t.lower() in report_blob for t in tokens)
        if matched:
            covered += 1
        else:
            uncovered.append({
                "parent_task_id": str(item.get("parent_task_id") or ""),
                "title": str(item.get("title") or ""),
            })

    ratio = (covered / total) if total > 0 else 0.0
    if total == 0:
        coverage = "none"
    elif covered == total:
        coverage = "full"
    elif covered > 0:
        coverage = "partial"
    else:
        coverage = "none"
    return coverage, total, covered, ratio, uncovered


def _load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _append_gap_parent_tasks(
    *,
    parents_path: Path,
    uncovered: List[Dict[str, str]],
    stamp: str,
    rollup_rel: str,
    gap_rel: str,
    template_rel: str,
    max_new: int = 50,
) -> int:
    if not uncovered:
        return 0
    parents = _load_lenient_json_array(parents_path)
    existing_ids = {p.get("parent_task_id") for p in parents if p.get("parent_task_id")}
    existing_titles = {str(p.get("title") or "").strip().lower() for p in parents}

    task_id = f"P1_PARENT__GOAL_STATUS_SUPPLEMENT__{stamp}"
    title = f"Goal Status Supplement Report ({stamp})"
    if task_id in existing_ids or title.strip().lower() in existing_titles:
        return 0

    missing_preview = "; ".join(
        f"{i.get('parent_task_id')}|{i.get('title')}" for i in uncovered[:10]
    )
    if len(uncovered) > 10:
        missing_preview += f" ...(+{len(uncovered) - 10})"

    task = {
        "parent_task_id": task_id,
        "title": title,
        "goal": "Produce a supplement status review report covering all missing goals from the gap review.",
        "scope_allow": [
            "docs/REPORT/",
            "docs/TASKS/",
            "tools/",
        ],
        "constraints": [
            f"Source rollup: {rollup_rel}",
            f"Gap report: {gap_rel}",
            f"Supplement template: {template_rel}",
            f"Missing goals (preview): {missing_preview}",
            "Generated by gap-review hook; refine scope before execution",
            "Do not auto-execute; split/dispatch by system only",
        ],
        "success_criteria": [
            "Supplement review report references all missing goals",
            "Next rollup shows Goal Coverage: full",
        ],
        "risk_level": "P1",
        "acceptance_tests": [
            "Manual: verify rollup coverage full",
        ],
        "execution_mode": "ifcli_headless",
    }
    parents.append(task)
    parents_path.write_text(json.dumps(parents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1


def _write_gap_review(
    *,
    report_dir: Path,
    stamp: str,
    scope: str,
    coverage: str,
    goal_total: int,
    goal_covered: int,
    goal_ratio: float,
    goal_uncovered: List[Dict[str, str]],
    included_reports: List[str],
    template_rel: str,
    limit: int = 100,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    out_path = report_dir / f"REPORT__GOAL_STATUS_GAP_REVIEW__{stamp}.md"
    lines = [
        f"# Goal Status Gap Review ({stamp})",
        "",
        f"- Scope: {scope}",
        f"- Goal Coverage: {coverage}",
        f"- Goals total: {goal_total}",
        f"- Goals covered: {goal_covered}",
        f"- Coverage ratio: {goal_ratio:.2f}",
        "",
        "## Missing Coverage (Uncovered Goals)",
    ]
    for item in (goal_uncovered or [])[:limit]:
        lines.append(f"- {item.get('parent_task_id')} | {item.get('title')}")
    if (goal_uncovered or []) and len(goal_uncovered) > limit:
        lines.append(f"- ... {len(goal_uncovered) - limit} more")
    lines += [
        "",
        "## Included Reports",
    ]
    for rel in included_reports:
        lines.append(f"- {rel}")
    if template_rel:
        lines += [
            "",
            "## Supplement Template",
            f"- {template_rel}",
        ]
    lines += [
        "",
        "## Action Required",
        "- Add missing goal coverage into the next status review report set.",
        "- Re-run rollup to reach full coverage before triggering parent task generation.",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def _write_gap_template(
    *,
    report_dir: Path,
    stamp: str,
    scope: str,
    goal_uncovered: List[Dict[str, str]],
    limit: int = 200,
) -> Path:
    out_dir = report_dir / "artifacts" / f"GOAL_STATUS_GAP_REVIEW__{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "SUPPLEMENT_TEMPLATE.md"
    lines = [
        "# Status Review Supplement Template",
        "",
        f"- Scope: {scope}",
        f"- Generated from gap review: REPORT__GOAL_STATUS_GAP_REVIEW__{stamp}",
        "",
        "## Missing Goals To Cover",
    ]
    for item in (goal_uncovered or [])[:limit]:
        lines.append(f"- {item.get('parent_task_id')} | {item.get('title')}")
    if (goal_uncovered or []) and len(goal_uncovered) > limit:
        lines.append(f"- ... {len(goal_uncovered) - limit} more")
    lines += [
        "",
        "## Evidence",
        "- Add links to reports/evidence that cover each missing goal.",
        "",
        "## Notes",
        "- This template is auto-generated. Fill in coverage for all missing goals.",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate total status rollup report")
    ap.add_argument("--config", default="")
    ap.add_argument("--scan-dir", default=r"C:\scc\scc-top\docs\REPORT\control_plane")
    ap.add_argument("--out-dir", default=r"C:\scc\scc-top\docs\REPORT\control_plane")
    ap.add_argument("--match", action="append", default=[])
    ap.add_argument("--max-reports", type=int, default=200)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--trigger", action="store_true", help="Trigger goal->parent tasks from rollup")
    ap.add_argument("--require-scope", default="full")
    args = ap.parse_args()

    repo_root = _repo_root()
    default_config_path = repo_root / "tools" / "scc" / "ops" / "goal_status_rollup_config.json"
    config_path = Path(args.config) if str(args.config or "").strip() else default_config_path
    cfg = _load_config(config_path)
    if cfg.get("enabled") is False:
        print("[rollup] config disabled; skip.")
        return 0

    if args.scan_dir == r"C:\scc\scc-top\docs\REPORT\control_plane" and cfg.get("scan_dir"):
        args.scan_dir = str(cfg.get("scan_dir"))
    if args.out_dir == r"C:\scc\scc-top\docs\REPORT\control_plane" and cfg.get("out_dir"):
        args.out_dir = str(cfg.get("out_dir"))
    if args.max_reports == 200 and isinstance(cfg.get("max_reports"), int):
        args.max_reports = int(cfg.get("max_reports"))
    if "require_scope" in cfg:
        args.require_scope = str(cfg.get("require_scope") or "")
    if not args.match and isinstance(cfg.get("match"), list):
        args.match = [str(x) for x in cfg.get("match") if str(x).strip()]
    if not args.apply and bool(cfg.get("trigger_parent_tasks", False)):
        args.apply = True
    if not args.trigger and bool(cfg.get("trigger_parent_tasks", False)):
        args.trigger = True

    scan_dir = Path(args.scan_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    board_path = Path(str(cfg.get("board", r"C:\scc\scc-top\docs\TASKS\backlog\parent_task_goal_board.json")))
    if not board_path.is_absolute():
        board_path = (repo_root / board_path).resolve()

    patterns = args.match or []
    if not patterns:
        patterns = [
            "REPORT__GOAL_CHAIN_STATUS__",
            "Goal Chain Status Report",
        ]

    candidates: List[Tuple[Path, str, str, str]] = []
    for root, _, files in os.walk(scan_dir):
        for name in files:
            if not name.startswith("REPORT__") or not name.endswith(".md"):
                continue
            path = Path(root) / name
            text = _read_text(path)
            if not _match_report(path, text, patterns):
                continue
            scope = _extract_scope(name, text)
            gen = _extract_generated_at(text)
            if not gen:
                try:
                    gen = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat().replace("+00:00", "Z")
                except Exception:
                    gen = ""
            candidates.append((path, scope, gen, text))

    # sort newest first
    candidates.sort(key=lambda x: x[2], reverse=True)
    if args.max_reports and len(candidates) > args.max_reports:
        candidates = candidates[: int(args.max_reports)]

    scope_rollup = "unknown"
    if any(s == "full" for _, s, _, _ in candidates):
        scope_rollup = "full"
    elif any(s == "block" for _, s, _, _ in candidates):
        scope_rollup = "block"

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%d-%H%M%SZ")
    out_path = out_dir / f"REPORT__GOAL_STATUS_ROLLUP__{stamp}.md"

    coverage, goal_total, goal_covered, goal_ratio, goal_uncovered = _compute_goal_coverage(board_path, [t for _, _, _, t in candidates])

    lines = [
        f"# Goal Status Rollup Report ({now.strftime('%Y-%m-%d')})",
        "",
        f"- Generated at (UTC): {now.isoformat().replace('+00:00','Z')}",
        f"- Scope: {scope_rollup}",
        f"- Rollup: true",
        f"- Included reports: {len(candidates)}",
        "",
        "## Goal Coverage",
        f"- Goal Board: {board_path}",
        f"- Goal Coverage: {coverage}",
        f"- Goals total: {goal_total}",
        f"- Goals covered: {goal_covered}",
        f"- Coverage ratio: {goal_ratio:.2f}",
        "- Uncovered goals:",
    ]
    for item in goal_uncovered[:50]:
        lines.append(f"- {item.get('parent_task_id')} | {item.get('title')}")
    lines += [
        "",
        "## Included Reports",
    ]
    for path, scope, gen, _ in candidates:
        rel = _to_repo_rel(path, repo_root)
        lines.append(f"- {rel} | scope={scope} | generated_at={gen}")

    if not args.apply:
        print("[rollup] Dry-run (use --apply to write report)")
        print("\n".join(lines[:40]))
        return 0

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    gap_report = None
    gap_tasks_added = 0
    gap_enabled = bool(cfg.get("gap_review_on_incomplete", True))
    gap_limit = int(cfg.get("gap_review_limit", 100) or 100)
    gap_dir = Path(str(cfg.get("gap_review_report_dir", args.out_dir)))
    if not gap_dir.is_absolute():
        gap_dir = (repo_root / gap_dir).resolve()
    if gap_enabled and coverage != "full":
        included = [_to_repo_rel(p, repo_root) for p, _, _, _ in candidates]
        template_path = _write_gap_template(
            report_dir=gap_dir,
            stamp=stamp,
            scope=scope_rollup,
            goal_uncovered=goal_uncovered,
            limit=gap_limit,
        )
        gap_report = _write_gap_review(
            report_dir=gap_dir,
            stamp=stamp,
            scope=scope_rollup,
            coverage=coverage,
            goal_total=goal_total,
            goal_covered=goal_covered,
            goal_ratio=goal_ratio,
            goal_uncovered=goal_uncovered,
            included_reports=included,
            template_rel=_to_repo_rel(template_path, repo_root),
            limit=gap_limit,
        )
        if bool(cfg.get("gap_review_tasks_enabled", True)):
            parents_path = Path(str(cfg.get("parents", r"C:\scc\scc-top\docs\TASKS\backlog\parent_tasks.json")))
            if not parents_path.is_absolute():
                parents_path = (repo_root / parents_path).resolve()
            gap_tasks_added = _append_gap_parent_tasks(
                parents_path=parents_path,
                uncovered=goal_uncovered,
                stamp=stamp,
                rollup_rel=_to_repo_rel(out_path, repo_root),
                gap_rel=_to_repo_rel(gap_report, repo_root) if gap_report else "",
                template_rel=_to_repo_rel(template_path, repo_root),
                max_new=int(cfg.get("gap_review_tasks_max", 50) or 50),
            )

    if args.trigger:
        require_scope = str(args.require_scope or "").strip().lower()
        require_coverage = str(cfg.get("require_coverage", "") or "").strip().lower()
        cmd = [
            sys.executable,
            "tools/scc/ops/goal_status_to_parent_tasks.py",
            "--report-path",
            str(out_path),
            "--apply",
        ]
        if require_scope:
            cmd += ["--require-scope", require_scope]
        if require_coverage:
            cmd += ["--require-coverage", require_coverage]
        subprocess.run(cmd, cwd=str(repo_root), check=False, capture_output=True, text=True)

    # Optional: sync parent_tasks -> board and run split/dispatch (hooked)
    if bool(cfg.get("board_hook_enabled", False)):
        cmd = [
            sys.executable,
            "tools/scc/ops/parent_tasks_to_board_hook.py",
            "--parents",
            str(cfg.get("parents", r"C:\scc\scc-top\docs\TASKS\backlog\parent_tasks.json")),
            "--base",
            "http://127.0.0.1:18788",
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
            cmd.append("--apply")
        if bool(cfg.get("board_hook_split", True)):
            cmd.append("--split")
        if bool(cfg.get("board_hook_dispatch", True)):
            cmd.append("--dispatch")
        for ex in (cfg.get("board_hook_allowed_executors") or []):
            cmd += ["--allowed-executors", str(ex)]
        for model in (cfg.get("board_hook_allowed_models") or []):
            cmd += ["--allowed-models", str(model)]
        subprocess.run(cmd, cwd=str(repo_root), check=False, capture_output=True, text=True)

    if gap_report:
        print(f"[rollup] gap_report={gap_report}")
    if gap_tasks_added:
        print(f"[rollup] gap_tasks_added={gap_tasks_added}")
    print(f"[rollup] report={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
