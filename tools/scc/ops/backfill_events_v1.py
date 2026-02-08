#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


_ALLOWED_EVENT_TYPES = {
    "SUCCESS",
    "FAIL",
    "PINS_INSUFFICIENT",
    "PREFLIGHT_FAILED",
    "CI_FAILED",
    "EXECUTOR_ERROR",
    "RETRY_EXHAUSTED",
    "POLICY_VIOLATION",
    "ROLLBACK_APPLIED",
}

_PINS_V2_SCHEMA_VERSION = "scc.pins_result.v2"


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_utc_deterministic(task_id: str, submit: Dict[str, Any]) -> str:
    # Prefer a timestamp already present in submit.json if available.
    for k in ("t", "ended_at", "finished_at", "created_at", "started_at"):
        v = submit.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # Otherwise, synthesize a stable timestamp based on task_id. Keep it safely in the past
    # while still "looking like" a real ISO8601 UTC timestamp.
    h = hashlib.sha256(task_id.encode("utf-8")).hexdigest()
    seconds = int(h[:8], 16) % (366 * 24 * 60 * 60)  # within ~1 year
    base = datetime(2000, 1, 1, tzinfo=timezone.utc)
    return (base + timedelta(seconds=seconds)).isoformat()


def _read_json(path: pathlib.Path) -> Optional[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8-sig")
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _ensure_pins_v2(task_dir: pathlib.Path, task_id: str, submit: Dict[str, Any], *, dry_run: bool) -> Tuple[bool, str]:
    pins_path = task_dir / "pins" / "pins.json"
    existing = _read_json(pins_path)
    if isinstance(existing, dict) and existing.get("schema_version") == _PINS_V2_SCHEMA_VERSION:
        pins = existing.get("pins")
        if isinstance(pins, dict) and isinstance(pins.get("items"), list):
            return (False, "already_v2")

    allow_paths = submit.get("allow_paths") if isinstance(submit.get("allow_paths"), dict) else {}
    read_paths = allow_paths.get("read") if isinstance(allow_paths.get("read"), list) else []
    write_paths = allow_paths.get("write") if isinstance(allow_paths.get("write"), list) else []

    extra_paths: List[str] = []
    for k in ("touched_files", "changed_files", "new_files"):
        v = submit.get(k)
        if isinstance(v, list):
            extra_paths.extend([str(x) for x in v if isinstance(x, str) and x.strip()])

    read_set = {str(p).strip() for p in read_paths if isinstance(p, str) and p.strip()}
    write_set = {str(p).strip() for p in write_paths if isinstance(p, str) and p.strip()}
    all_paths = sorted(read_set | write_set | set(extra_paths))

    items: List[Dict[str, Any]] = []
    if not all_paths:
        all_paths = ["**"]

    for p in all_paths[:128]:
        if p in write_set:
            reason = "submit.allow_paths.write"
        elif p in read_set:
            reason = "submit.allow_paths.read"
        elif p in extra_paths:
            reason = "submit.touched_files"
        else:
            reason = "submit.derived"

        items.append(
            {
                "path": p,
                "reason": reason,
                "read_only": p not in write_set,
                "write_intent": p in write_set,
                "symbols": [],
                "line_windows": [],
            }
        )

    pins_v2 = {
        "schema_version": _PINS_V2_SCHEMA_VERSION,
        "task_id": task_id,
        "pins": {"items": items, "allowed_paths": all_paths[:128], "forbidden_paths": ["**/secrets/**"]},
        "recommended_queries": [],
        "preflight_expectation": {"should_pass": True, "notes": "Backfilled pins v2 from submit allow_paths/touched_files."},
    }

    if dry_run:
        return (True, "dry_run")

    try:
        pins_path.parent.mkdir(parents=True, exist_ok=True)
        pins_path.write_text(
            json.dumps(pins_v2, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="utf-8",
        )
        return (True, "backfilled")
    except Exception as e:
        return (False, f"write_failed:{e}")


def _existing_has_valid_event(events_path: pathlib.Path, task_id: str) -> bool:
    try:
        text = events_path.read_text(encoding="utf-8-sig")
    except Exception:
        return False
    for ln in text.splitlines()[-2000:]:
        s = ln.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("schema_version") != "scc.event.v1":
            continue
        if str(obj.get("task_id") or "") != task_id:
            continue
        # Strict event gating requires at least one SUCCESS/FAIL event row.
        et = str(obj.get("event_type") or "")
        if et in {"SUCCESS", "FAIL"}:
            return True
    return False


def _infer_event_type_from_submit(submit: Dict[str, Any]) -> Tuple[str, str]:
    status = str(submit.get("status") or "").upper().strip()
    reason_code = str(submit.get("reason_code") or "").strip()
    exit_code = submit.get("exit_code")

    if status in {"DONE", "SUCCESS", "OK"} and (exit_code is None or exit_code == 0):
        return ("SUCCESS", reason_code or "submit_status_done")

    return ("FAIL", reason_code or "submit_status_not_done")


def _make_event_row(task_id: str, submit: Dict[str, Any]) -> Dict[str, Any]:
    et, why = _infer_event_type_from_submit(submit)
    exit_code = submit.get("exit_code") if isinstance(submit.get("exit_code"), int) else None
    return {
        "schema_version": "scc.event.v1",
        "t": _iso_utc_deterministic(task_id, submit),
        "event_type": et,
        "task_id": task_id,
        "parent_id": submit.get("parent_id") if "parent_id" in submit else None,
        "role": submit.get("role") if "role" in submit else None,
        "area": None,
        "executor": None,
        "model": None,
        "reason": "events_backfill_v1",
        "details": {
            "inferred_from": why,
            "submit_status": submit.get("status"),
            "reason_code": submit.get("reason_code"),
            "exit_code": exit_code,
        },
    }


def _discover_task_dirs(artifacts_dir: pathlib.Path) -> List[pathlib.Path]:
    if not artifacts_dir.exists():
        return []
    out: List[pathlib.Path] = []
    for p in artifacts_dir.iterdir():
        if not p.is_dir():
            continue
        if p.name in {"executor_logs", "taskboard"}:
            continue
        # Task dir heuristic: must have submit.json.
        if (p / "submit.json").exists():
            out.append(p)
    out.sort(key=lambda x: x.name)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill artifacts/<task_id>/events.jsonl for legacy tasks.")
    ap.add_argument("--repo-root", default="C:/scc")
    ap.add_argument("--artifacts-dir", default="artifacts")
    ap.add_argument("--task-id", default="", help="Only process this task_id (optional)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="Overwrite events.jsonl even if it exists (dangerous)")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo_root).resolve()
    artifacts_dir = pathlib.Path(args.artifacts_dir)
    if not artifacts_dir.is_absolute():
        artifacts_dir = (repo / artifacts_dir).resolve()

    task_filter = str(args.task_id or "").strip()

    if task_filter:
        task_dir = (artifacts_dir / task_filter).resolve()
        submit_path = task_dir / "submit.json"
        if not submit_path.exists():
            print(json.dumps({"ok": False, "error": "task_not_found", "task_id": task_filter}, ensure_ascii=False))
            return 2
        task_dirs = [task_dir]
    else:
        task_dirs = _discover_task_dirs(artifacts_dir)

    changed = 0
    skipped = 0
    pins_changed = 0
    pins_skipped = 0
    errors: List[Dict[str, Any]] = []
    for d in task_dirs:
        task_id = d.name
        submit_path = d / "submit.json"
        submit = _read_json(submit_path)
        if not submit:
            errors.append({"task_id": task_id, "error": "invalid_submit_json"})
            continue
        events_path = d / "events.jsonl"

        pins_ok, pins_status = _ensure_pins_v2(d, task_id, submit, dry_run=args.dry_run)
        if pins_ok:
            if pins_status in {"already_v2"}:
                pins_skipped += 1
            else:
                pins_changed += 1
        else:
            if pins_status == "already_v2":
                pins_skipped += 1
            else:
                errors.append({"task_id": task_id, "error": "pins_backfill_failed", "message": pins_status})

        if events_path.exists() and not args.force:
            if _existing_has_valid_event(events_path, task_id):
                skipped += 1
                continue
            # If file exists but has no valid rows, we overwrite (non-destructive would be append,
            # but keeping strict gate deterministic is better here).

        row = _make_event_row(task_id, submit)
        if args.dry_run:
            changed += 1
            continue
        try:
            events_path.parent.mkdir(parents=True, exist_ok=True)
            events_path.write_text(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            changed += 1
        except Exception as e:
            errors.append({"task_id": task_id, "error": "write_failed", "message": str(e)})

    ok = len(errors) == 0
    print(
        json.dumps(
            {
                "ok": ok,
                "repo_root": repo.as_posix(),
                "artifacts_dir": artifacts_dir.as_posix(),
                "processed": len(task_dirs),
                "backfilled": changed,
                "skipped": skipped,
                "pins_backfilled": pins_changed,
                "pins_skipped": pins_skipped,
                "errors": errors[:50],
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
