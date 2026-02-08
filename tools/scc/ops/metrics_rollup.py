#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import pathlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
EXEC_LOG_DIR = REPO_ROOT / "artifacts" / "executor_logs"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_jsonl(path: pathlib.Path, tail: int = 20000) -> List[Dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out: List[Dict[str, Any]] = []
    for ln in lines[-int(tail) :]:
        s = str(ln or "").strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _read_jobs_jsonl_utf16ish(path: pathlib.Path, tail: int = 40000) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = path.read_bytes()
    except Exception:
        return []

    # jobs.jsonl is sometimes UTF-16LE (BOM + NULs). Decode best-effort.
    text: str
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        try:
            text = raw.decode("utf-16", errors="replace")
        except Exception:
            text = raw.decode("utf-8", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")

    lines = [ln for ln in text.splitlines() if ln.strip()]
    out: List[Dict[str, Any]] = []
    for ln in lines[-int(tail) :]:
        s = ln.strip().lstrip("\x00").strip()
        if not s:
            continue
        i = s.find("{")
        if i < 0:
            continue
        s = s[i:]
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def _bucket_start(ts: datetime, bucket_minutes: int) -> datetime:
    bucket_seconds = int(bucket_minutes) * 60
    epoch = int(ts.timestamp())
    start_epoch = epoch - (epoch % bucket_seconds)
    return datetime.fromtimestamp(start_epoch, tz=timezone.utc)


def _pctl(values: List[float], p: float) -> Optional[float]:
    xs = [float(v) for v in values if isinstance(v, (int, float)) and math.isfinite(float(v))]
    if not xs:
        return None
    xs.sort()
    if p <= 0:
        return xs[0]
    if p >= 1:
        return xs[-1]
    k = (len(xs) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    d0 = xs[f] * (c - k)
    d1 = xs[c] * (k - f)
    return d0 + d1


def _safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
        if math.isfinite(v):
            return v
    except Exception:
        return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Compute SCC metrics trends from executor logs (offline, deterministic).")
    ap.add_argument("--window-hours", type=int, default=72)
    ap.add_argument("--bucket-minutes", type=int, default=60)
    ap.add_argument("--out-latest", default="metrics/latest.json")
    ap.add_argument("--out-trends", default="metrics/trends.jsonl")
    args = ap.parse_args()

    window_hours = int(args.window_hours)
    bucket_minutes = int(args.bucket_minutes)
    if window_hours <= 0:
        print("FAIL: --window-hours must be > 0")
        return 2
    if bucket_minutes not in (5, 10, 15, 30, 60):
        print("FAIL: --bucket-minutes must be one of 5/10/15/30/60")
        return 2

    since = _now() - timedelta(hours=window_hours)

    events_path = EXEC_LOG_DIR / "state_events.jsonl"
    jobs_path = EXEC_LOG_DIR / "jobs.jsonl"
    if not events_path.exists():
        print(f"FAIL: missing {events_path}")
        return 2
    if not jobs_path.exists():
        print(f"FAIL: missing {jobs_path}")
        return 2

    events = _read_jsonl(events_path, tail=60000)
    jobs = _read_jobs_jsonl_utf16ish(jobs_path, tail=60000)

    now = _now()
    since_15m = now - timedelta(minutes=15)

    # Index latest job per task_id (finished only), and also keep per-bucket aggregates.
    job_by_task: Dict[str, Dict[str, Any]] = {}
    job_rows: List[Dict[str, Any]] = []
    for j in jobs:
        tid = j.get("task_id")
        if not isinstance(tid, str) or not tid.strip():
            continue
        finished_at = j.get("finishedAt")
        if not isinstance(finished_at, (int, float)):
            continue
        t = datetime.fromtimestamp(float(finished_at) / 1000.0, tz=timezone.utc)
        if t < since:
            continue
        job_rows.append(j)
        prev = job_by_task.get(tid)
        if not prev or float(prev.get("finishedAt") or 0) <= float(finished_at):
            job_by_task[tid] = j

    # Bucket events by time (use event.t).
    buckets: Dict[str, Dict[str, Any]] = {}
    w15_finished = 0
    w15_ci_failed = 0
    w15_timeouts = 0
    for e in events:
        ts = e.get("t")
        if not isinstance(ts, str):
            continue
        try:
            t = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
        except Exception:
            continue
        if t < since:
            continue
        in_15m = t >= since_15m
        b = _bucket_start(t, bucket_minutes)
        key = b.isoformat()
        cur = buckets.get(key)
        if not cur:
            cur = {
                "bucket_start": key,
                "bucket_minutes": bucket_minutes,
                "finished": 0,
                "success": 0,
                "success_first_attempt": 0,
                "retries_sum": 0,
                "retries_n": 0,
                "ci_failed": 0,
                "timeouts": 0,
                "durations_done_ms": [],
                "tokens_done": [],
            }
            buckets[key] = cur

        et = str(e.get("event_type") or "")
        attempts = e.get("attempts")
        attempts_i = int(attempts) if isinstance(attempts, int) else None

        is_finished = et in {"SUCCESS", "CI_FAILED", "EXECUTOR_ERROR", "PREFLIGHT_FAILED", "PINS_INSUFFICIENT", "POLICY_VIOLATION"}
        if is_finished:
            cur["finished"] += 1
            if in_15m:
                w15_finished += 1
            if attempts_i is not None and attempts_i >= 1:
                cur["retries_sum"] += max(0, attempts_i - 1)
                cur["retries_n"] += 1

        if et == "SUCCESS":
            cur["success"] += 1
            if attempts_i == 1:
                cur["success_first_attempt"] += 1
        if et == "CI_FAILED":
            cur["ci_failed"] += 1
            if in_15m:
                w15_ci_failed += 1

        reason = str(e.get("reason") or "").lower()
        if et == "timeout" or "timeout" in reason:
            cur["timeouts"] += 1
            if in_15m:
                w15_timeouts += 1

        # Attach job metrics if available for this task.
        tid = e.get("task_id")
        if isinstance(tid, str) and tid in job_by_task:
            j = job_by_task[tid]
            if str(j.get("status") or "") == "done":
                d = _safe_float(j.get("durationMs"))
                if d is not None:
                    cur["durations_done_ms"].append(d)
                usage = j.get("usage")
                if isinstance(usage, dict):
                    it = _safe_float(usage.get("input_tokens"))
                    ot = _safe_float(usage.get("output_tokens"))
                    if it is not None and ot is not None:
                        cur["tokens_done"].append(it + ot)

    # Compute rollups
    trend_rows: List[Dict[str, Any]] = []
    for k in sorted(buckets.keys()):
        b = buckets[k]
        success = int(b["success"])
        sfa = int(b["success_first_attempt"])
        finished = int(b["finished"])
        retries_n = int(b["retries_n"])
        first_pass_rate = (sfa / success) if success > 0 else None
        avg_retries = (float(b["retries_sum"]) / retries_n) if retries_n > 0 else None
        tokens_done = b["tokens_done"]
        durations_done_ms = b["durations_done_ms"]
        token_per_done = (sum(tokens_done) / len(tokens_done)) if tokens_done else None
        time_per_done_s = (sum(durations_done_ms) / len(durations_done_ms) / 1000.0) if durations_done_ms else None
        p95_task_duration_s = (_pctl([d / 1000.0 for d in durations_done_ms], 0.95)) if durations_done_ms else None
        ci_failed_rate = (int(b["ci_failed"]) / finished) if finished > 0 else None
        timeout_rate = (int(b["timeouts"]) / finished) if finished > 0 else None
        trend_rows.append(
            {
                "schema_version": "scc.metrics_bucket.v1",
                "bucket_start": b["bucket_start"],
                "bucket_minutes": bucket_minutes,
                "first_pass_rate": first_pass_rate,
                "avg_retries": avg_retries,
                "token_per_done": token_per_done,
                "time_per_done_s": time_per_done_s,
                "p95_task_duration_s": p95_task_duration_s,
                "ci_failed_rate": ci_failed_rate,
                "timeout_rate": timeout_rate,
                "counts": {"finished": finished, "success": success},
            }
        )

    # Latest window = last non-empty bucket.
    latest = next((r for r in reversed(trend_rows) if (r.get("counts") or {}).get("finished")), None)
    if isinstance(latest, dict):
        latest["ci_failed_rate_15m"] = (w15_ci_failed / w15_finished) if w15_finished > 0 else None
        latest["timeout_rate_15m"] = (w15_timeouts / w15_finished) if w15_finished > 0 else None
    out_latest = (REPO_ROOT / str(args.out_latest)).resolve()
    out_trends = (REPO_ROOT / str(args.out_trends)).resolve()
    out_trends.parent.mkdir(parents=True, exist_ok=True)

    _write_json(
        out_latest,
        {
            "schema_version": "scc.metrics_latest.v1",
            "t": _iso(_now()),
            "window_hours": window_hours,
            "bucket_minutes": bucket_minutes,
            "sources": {
                "events": str(events_path.relative_to(REPO_ROOT)).replace("\\", "/"),
                "jobs": str(jobs_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            },
            "latest_bucket": latest,
        },
    )
    with out_trends.open("w", encoding="utf-8") as f:
        for r in trend_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("OK")
    print(str(out_latest.relative_to(REPO_ROOT)).replace("\\", "/"))
    print(str(out_trends.relative_to(REPO_ROOT)).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
