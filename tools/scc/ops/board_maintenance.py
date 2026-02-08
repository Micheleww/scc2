#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import time
from datetime import datetime, timezone
from typing import Any


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ms(x: Any) -> int:
    try:
        if isinstance(x, bool):
            return 0
        if isinstance(x, int):
            return int(x)
        if isinstance(x, float):
            return int(x)
        if isinstance(x, str) and x.strip().isdigit():
            return int(x.strip())
    except Exception:
        return 0
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Board maintenance: archive old done/failed tasks and sweep failed->dlq.")
    ap.add_argument("--repo-root", default=".", help="Repo root (default: cwd)")
    ap.add_argument("--board", default="artifacts/taskboard/tasks.json", help="Path to board tasks.json")
    ap.add_argument("--archive-dir", default="artifacts/taskboard/archive", help="Archive directory")
    ap.add_argument("--keep-hours", type=int, default=24, help="Keep done/failed tasks updated within this window")
    ap.add_argument("--keep-last-failed", type=int, default=40, help="Always keep the most recent failed tasks")
    ap.add_argument("--keep-last-done", type=int, default=20, help="Always keep the most recent done tasks")
    ap.add_argument("--dlq-after-attempts", type=int, default=2, help="Failed tasks with >=N dispatch_attempts are swept to lane=dlq")
    ap.add_argument("--dry-run", action="store_true", help="Do not write any files")
    ap.add_argument("--write", action="store_true", help="Write updated board + archive file")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo_root).resolve()
    board_path = (repo / _norm_rel(str(args.board))).resolve()
    if not board_path.exists():
        print(f"FAIL: missing board file: {board_path}")
        return 2

    tasks = _load_json(board_path)
    if not isinstance(tasks, list):
        print("FAIL: board file is not a JSON array")
        return 2

    now = _now_ms()
    keep_window_ms = max(0, int(args.keep_hours)) * 3600_000
    keep_failed_n = max(0, int(args.keep_last_failed))
    keep_done_n = max(0, int(args.keep_last_done))
    dlq_attempts = max(1, int(args.dlq_after_attempts))

    # Extract recent task ids to keep by status.
    failed_sorted = sorted(
        [t for t in tasks if isinstance(t, dict) and t.get("status") == "failed"],
        key=lambda t: _ms(t.get("updatedAt")) or _ms(t.get("createdAt")),
        reverse=True,
    )
    done_sorted = sorted(
        [t for t in tasks if isinstance(t, dict) and t.get("status") == "done"],
        key=lambda t: _ms(t.get("updatedAt")) or _ms(t.get("createdAt")),
        reverse=True,
    )
    keep_ids = {str(t.get("id")) for t in failed_sorted[:keep_failed_n] if t.get("id")}
    keep_ids |= {str(t.get("id")) for t in done_sorted[:keep_done_n] if t.get("id")}

    archived: list[dict] = []
    kept: list[dict] = []
    swept_dlq = 0

    for item in tasks:
        if not isinstance(item, dict):
            continue
        tid = str(item.get("id") or "")
        status = str(item.get("status") or "")
        lane = str(item.get("lane") or "")
        updated = _ms(item.get("updatedAt")) or _ms(item.get("createdAt"))
        age_ms = now - updated if updated > 0 else 0

        # Sweep failed tasks into DLQ lane deterministically (do not change status).
        if status == "failed":
            attempts = _ms(item.get("dispatch_attempts"))
            if attempts >= dlq_attempts and lane not in ("quarantine", "dlq"):
                item["lane"] = "dlq"
                item["dlq_opened"] = True
                item["dlq_opened_at"] = _iso_now()
                item["dlq_reason"] = str(item.get("lastJobReason") or item.get("lastJobStatus") or "failed")
                swept_dlq += 1

        # Only archive terminal tasks (done/failed) that are old and not explicitly kept.
        if status in ("done", "failed"):
            if tid and tid in keep_ids:
                kept.append(item)
                continue
            if keep_window_ms and age_ms >= keep_window_ms:
                archived.append(item)
                continue

        kept.append(item)

    report = {
        "schema_version": "scc.board_maintenance_report.v1",
        "generated_at": _iso_now(),
        "board": _norm_rel(str(board_path.relative_to(repo))),
        "counts": {"before": len(tasks), "after": len(kept), "archived": len(archived), "swept_to_dlq": swept_dlq},
        "params": {
            "keep_hours": int(args.keep_hours),
            "keep_last_failed": keep_failed_n,
            "keep_last_done": keep_done_n,
            "dlq_after_attempts": dlq_attempts,
        },
        "write": bool(args.write and not args.dry_run),
    }

    if args.dry_run or not args.write:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_dir = (repo / _norm_rel(str(args.archive_dir))).resolve()
    archive_path = archive_dir / f"tasks_{stamp}.json"
    _write_json(archive_path, archived)
    _write_json(board_path, kept)

    report["archive_path"] = _norm_rel(str(archive_path.relative_to(repo)))
    report_path = archive_dir / f"maintenance_{stamp}.json"
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

