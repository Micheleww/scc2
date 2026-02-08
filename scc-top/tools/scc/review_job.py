#!/usr/bin/env python3
"""SCC review job: Progress + Feedback + Metrics (v0.1.0).

Outputs:
- Progress Report (canonical): docs/CANONICAL/PROGRESS.md (append-only log entry)
- Feedback Package (raw-b): docs/INPUTS/raw-b/review_feedback_<ts>.md (append-only)
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TaskRecord:
    task_id: str
    path: Path
    created_utc: Optional[datetime]
    updated_utc: Optional[datetime]
    status: Optional[str]
    verdict: Optional[str]
    exit_code: Optional[int]
    error: Optional[str]
    run_id: Optional[str]
    events: List[Dict[str, Any]]


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return None


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return None


def _load_events(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
    except Exception:
        return []
    return out


def iter_task_records(tasks_root: Path) -> List[TaskRecord]:
    records: List[TaskRecord] = []
    if not tasks_root.exists():
        return records
    for task_json in tasks_root.rglob("task.json"):
        task_data = _load_json(task_json) or {}
        task_id = str(task_data.get("task_id") or task_json.parent.name)
        records.append(
            TaskRecord(
                task_id=task_id,
                path=task_json.parent,
                created_utc=_parse_iso(task_data.get("created_utc")),
                updated_utc=_parse_iso(task_data.get("updated_utc")),
                status=task_data.get("status"),
                verdict=task_data.get("verdict"),
                exit_code=task_data.get("exit_code"),
                error=task_data.get("error"),
                run_id=task_data.get("run_id"),
                events=_load_events(task_json.parent / "events.jsonl"),
            )
        )
    return records


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    values = sorted(values)
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * (pct / 100.0)
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


def _mean(values: List[float]) -> Optional[float]:
    return (sum(values) / len(values)) if values else None


def _format_seconds(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    if value >= 60:
        minutes = int(value // 60)
        seconds = value - minutes * 60
        return f"{minutes}m{seconds:.1f}s"
    return f"{value:.2f}s"


def _has_frontmatter_oid(path: Path) -> bool:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return False
    if not lines or lines[0].strip() != "---":
        return False
    end = None
    for i in range(1, min(len(lines), 120)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return False
    for l in lines[1:end]:
        if l.strip().startswith("oid:"):
            return True
    return False


def compute_oid_coverage(repo_root: Path) -> Optional[Dict[str, Any]]:
    trees = [
        ("docs/ssot", repo_root / "docs" / "ssot"),
        ("docs/CANONICAL", repo_root / "docs" / "CANONICAL"),
        ("docs/DOCOPS", repo_root / "docs" / "DOCOPS"),
        ("docs/arch", repo_root / "docs" / "arch"),
    ]
    total_all = 0
    with_all = 0
    by_tree: Dict[str, Dict[str, int]] = {}
    any_found = False
    for key, base in trees:
        if not base.exists():
            continue
        any_found = True
        total = 0
        with_oid = 0
        for p in base.rglob("*.md"):
            total += 1
            if _has_frontmatter_oid(p):
                with_oid += 1
        by_tree[key] = {"with_oid": with_oid, "total": total}
        total_all += total
        with_all += with_oid
    if not any_found or total_all == 0:
        return None
    return {"ratio": with_all / total_all, "with_oid": with_all, "total": total_all, "by_tree": by_tree}


def compute_metrics(records: List[TaskRecord], *, oid_cov: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    completed = [r for r in records if r.verdict]
    passed = [r for r in completed if r.verdict == "PASS"]

    pass_rate = (len(passed) / len(completed)) if completed else None

    retries: List[float] = []
    for r in records:
        attempts = 0
        for e in r.events:
            if e.get("type") == "fullagent_executor_completed":
                attempts += 1
        retries.append(float(max(0, attempts - 1)))
    mean_retries = _mean(retries)

    t2g: List[float] = []
    for r in passed:
        if r.created_utc and r.updated_utc:
            delta = (r.updated_utc - r.created_utc).total_seconds()
            if delta >= 0:
                t2g.append(delta)
    t2g_p50 = _percentile(t2g, 50)
    t2g_p95 = _percentile(t2g, 95) if len(t2g) >= 5 else None

    fail_codes: Dict[str, int] = {}
    for r in records:
        if r.verdict and r.verdict != "PASS":
            if r.exit_code not in (None, 0):
                k = f"exit_code:{r.exit_code}"
                fail_codes[k] = fail_codes.get(k, 0) + 1
            elif r.error:
                fail_codes["error"] = fail_codes.get("error", 0) + 1
        for e in r.events:
            data = e.get("data") if isinstance(e.get("data"), dict) else {}
            if data.get("success") is False:
                rc = data.get("reason_code") or data.get("reason")
                if rc:
                    fail_codes[str(rc)] = fail_codes.get(str(rc), 0) + 1
    top_fail_codes = sorted(fail_codes.items(), key=lambda x: (-x[1], x[0]))[:20]

    ingestion: List[float] = []
    for r in records:
        if not r.created_utc:
            continue
        ts_candidates: List[datetime] = []
        for e in r.events:
            if (e.get("type") or e.get("name")) == "task_submitted":
                t = _parse_iso(e.get("ts_utc"))
                if t:
                    ts_candidates.append(t)
        if not ts_candidates:
            for e in r.events:
                t = _parse_iso(e.get("ts_utc"))
                if t:
                    ts_candidates.append(t)
        if not ts_candidates:
            continue
        first = min(ts_candidates)
        lag = (first - r.created_utc).total_seconds()
        if lag >= 0:
            ingestion.append(lag)
    ing_p50 = _percentile(ingestion, 50)
    ing_p95 = _percentile(ingestion, 95) if len(ingestion) >= 5 else None

    return {
        "pass_rate": pass_rate,
        "mean_retries": mean_retries,
        "time_to_green_p50_s": t2g_p50,
        "time_to_green_p95_s": t2g_p95,
        "top_fail_codes": top_fail_codes,
        "oid_coverage": oid_cov,
        "ingestion_lag_p50_s": ing_p50,
        "ingestion_lag_p95_s": ing_p95,
    }


def append_progress(progress_path: Path, entry: str) -> None:
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    existing = progress_path.read_text(encoding="utf-8", errors="replace") if progress_path.exists() else ""
    if "## Log" not in existing:
        existing = existing.rstrip() + "\n\n## Log\n"
    updated = existing.rstrip() + "\n" + entry.rstrip() + "\n"
    progress_path.write_text(updated, encoding="utf-8", errors="replace")


def write_feedback(rawb_dir: Path, filename: str, content: str) -> Path:
    rawb_dir.mkdir(parents=True, exist_ok=True)
    path = rawb_dir / filename
    path.write_text(content, encoding="utf-8", errors="replace")
    return path


def main() -> int:
    ap = argparse.ArgumentParser(description="SCC review job")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--progress-doc", default="docs/CANONICAL/PROGRESS.md")
    ap.add_argument("--rawb-dir", default="docs/INPUTS/raw-b")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[2]
    tasks_root = Path(args.tasks_root)
    progress_path = Path(args.progress_doc)
    rawb_dir = Path(args.rawb_dir)

    records = iter_task_records(tasks_root)
    oid_cov = compute_oid_coverage(repo_root)
    metrics = compute_metrics(records, oid_cov=oid_cov)

    done = sum(1 for r in records if r.status == "done")
    pending = sum(1 for r in records if r.status == "pending")
    other = len(records) - done - pending

    created_times = [r.created_utc for r in records if r.created_utc]
    updated_times = [r.updated_utc for r in records if r.updated_utc]
    window_str = "unknown"
    if created_times and updated_times:
        window_str = f"{min(created_times).isoformat()} → {max(updated_times).isoformat()}"

    now_utc = datetime.now(timezone.utc)
    date_str = now_utc.strftime("%Y-%m-%d")
    ts_str = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    feedback_name = f"review_feedback_{now_utc.strftime('%Y%m%d-%H%M%SZ')}.md"

    pass_rate = metrics.get("pass_rate")
    pass_rate_display = "n/a" if pass_rate is None else f"{float(pass_rate):.2%}"
    mean_retries_display = "n/a" if metrics.get("mean_retries") is None else f"{float(metrics['mean_retries']):.2f}"
    t2g_p50 = _format_seconds(metrics.get("time_to_green_p50_s"))
    t2g_p95 = _format_seconds(metrics.get("time_to_green_p95_s"))
    ing_p50 = _format_seconds(metrics.get("ingestion_lag_p50_s"))
    ing_p95 = _format_seconds(metrics.get("ingestion_lag_p95_s"))

    oid_cov = metrics.get("oid_coverage")
    oid_display = "n/a"
    if isinstance(oid_cov, dict) and oid_cov.get("ratio") is not None:
        oid_display = f"{float(oid_cov['ratio']):.2%} ({int(oid_cov.get('with_oid') or 0)}/{int(oid_cov.get('total') or 0)})"

    top_fail = metrics.get("top_fail_codes") or []
    top_fail_lines = [f"- {code}: {count}" for code, count in top_fail] or ["- none"]

    progress_entry = (
        f"- {date_str}: Review job update (window {window_str}). "
        f"Tasks total={len(records)} done={done} pending={pending} other={other}. "
        f"Metrics: pass_rate={pass_rate_display}, mean_retries={mean_retries_display}, "
        f"time_to_green_p50={t2g_p50}, time_to_green_p95={t2g_p95}, "
        f"oid_coverage={oid_display}, ingestion_lag_p50={ing_p50}, ingestion_lag_p95={ing_p95}. "
        f"Evidence: artifacts/scc_tasks, artifacts/scc_runs, docs/INPUTS/raw-b/{feedback_name}"
    )

    feedback_content = "\n".join(
        [
            "---",
            "source: review_job",
            f"ts_utc: {ts_str}",
            f"tasks_total: {len(records)}",
            "---",
            "",
            "# Review Feedback Package",
            "",
            "## Summary",
            f"- task_window: {window_str}",
            f"- tasks: total={len(records)} done={done} pending={pending} other={other}",
            "",
            "## Metrics",
            f"- pass_rate: {pass_rate_display}",
            f"- mean_retries: {mean_retries_display}",
            f"- time_to_green_p50: {t2g_p50}",
            f"- time_to_green_p95: {t2g_p95}",
            "- top_fail_codes:",
            *top_fail_lines,
            f"- oid_coverage: {oid_display}",
            f"- ingestion_lag_p50: {ing_p50}",
            f"- ingestion_lag_p95: {ing_p95}",
            "",
            "## Evidence",
            "- artifacts/scc_tasks",
            "- artifacts/scc_runs",
            "",
            "## Questions",
            "- none",
        ]
    )

    if args.dry_run:
        print(progress_entry)
        print()
        print(feedback_content)
        return 0

    append_progress(progress_path, progress_entry)
    fb_path = write_feedback(rawb_dir, feedback_name, feedback_content)

    print("review_job completed")
    print(f"progress_doc={progress_path}")
    print(f"feedback={fb_path}")
    print(f"tasks_root={tasks_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

