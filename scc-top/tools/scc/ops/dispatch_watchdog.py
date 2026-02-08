#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return None


def _http_post(url: str, payload: dict, timeout_s: float = 6.0) -> Tuple[int, str]:
    import urllib.request
    import urllib.error

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(getattr(resp, "status", 200)), body
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(e)
        return int(getattr(e, "code", 500)), body
    except Exception as e:
        return 0, str(e)

def _read_tokens_used(parent_dir: Path) -> Optional[int]:
    u = parent_dir / "usage.json"
    j = _read_json(u) if u.exists() else None
    if not isinstance(j, dict):
        return None
    try:
        v = j.get("tokens_used")
        return int(v) if v is not None else None
    except Exception:
        return None


@dataclass
class RunStatus:
    run_id: str
    updated_utc: str
    manifest_file: str
    any_running: bool
    oldest_running_age_s: Optional[float]


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(s)).astimezone(timezone.utc)
    except Exception:
        return None


def _load_active_runs(repo_root: Path) -> Dict[str, dict]:
    p = (repo_root / "artifacts" / "codexcli_remote_runs" / "_state" / "active_runs.json").resolve()
    j = _read_json(p)
    runs = j.get("runs") if isinstance(j, dict) else None
    return runs if isinstance(runs, dict) else {}


def _summarize_run(run_id: str, entry: dict) -> RunStatus:
    mf = str(entry.get("manifest_file") or "")
    updated_utc = str(entry.get("updated_utc") or "")
    j = _read_json(Path(mf)) if mf else None
    any_running = False
    oldest_running_age_s: Optional[float] = None
    now = datetime.now(timezone.utc)
    if isinstance(j, dict):
        parents = j.get("parents")
        if isinstance(parents, list):
            for p in parents:
                if not isinstance(p, dict):
                    continue
                if p.get("end"):
                    continue
                any_running = True
                st = _parse_iso(str(p.get("start") or ""))
                if st is not None:
                    age = (now - st).total_seconds()
                    if oldest_running_age_s is None or age > oldest_running_age_s:
                        oldest_running_age_s = age
    return RunStatus(
        run_id=str(run_id),
        updated_utc=updated_utc,
        manifest_file=mf,
        any_running=any_running,
        oldest_running_age_s=oldest_running_age_s,
    )


def _append_jsonl(path: Path, obj: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", errors="replace") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    except Exception:
        return

def _latest_mtime(paths: list[Path]) -> Optional[datetime]:
    mt: Optional[datetime] = None
    for p in paths:
        try:
            if not p.exists():
                continue
            t = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
            if mt is None or t > mt:
                mt = t
        except Exception:
            continue
    return mt

def _detect_no_progress(*, parent_dir: Path, now: datetime, stuck_after_s: float) -> tuple[bool, str]:
    candidates = [
        parent_dir / "status.json",
        parent_dir / "events.jsonl",
        parent_dir / "stdout.log",
        parent_dir / "stderr.log",
        parent_dir / "patch.diff",
        parent_dir / "scope_enforcement.json",
        parent_dir / "proc.json",
    ]
    last = _latest_mtime(candidates)
    if last is None:
        return True, "no_heartbeat_files"
    age = (now - last).total_seconds()
    if age >= float(stuck_after_s):
        return True, f"no_progress_for_s:{int(age)}"
    return False, f"last_progress_s:{int(age)}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Leader watchdog: monitor and cancel stuck /executor/codex/run batches.")
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[3]))
    ap.add_argument("--base", default="http://127.0.0.1:18788")
    ap.add_argument("--poll-s", type=float, default=60.0)
    ap.add_argument("--stuck-after-s", type=float, default=60.0, help="Cancel a parent when there is no progress for this many seconds.")
    ap.add_argument("--token-cap", type=int, default=0, help="If >0, cancel a parent when usage.json tokens_used >= token_cap.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    cancel_url = str(args.base).rstrip("/") + "/executor/codex/cancel"
    events_path = (repo_root / "docs" / "DERIVED" / "dispatch" / "watchdog_events.jsonl").resolve()

    print(f"[watchdog] started_utc={_utc_now()} base={args.base} stuck_after_s={args.stuck_after_s} dry_run={args.dry_run}", flush=True)
    _append_jsonl(
        events_path,
        {
            "ts_utc": _utc_now(),
            "kind": "WATCHDOG_START",
            "base": str(args.base),
            "poll_s": float(args.poll_s),
            "stuck_after_s": float(args.stuck_after_s),
            "token_cap": int(args.token_cap or 0),
            "dry_run": bool(args.dry_run),
        },
    )
    while True:
        runs = _load_active_runs(repo_root)
        if not runs:
            time.sleep(float(args.poll_s))
            continue

        for rid, entry in sorted(runs.items(), key=lambda kv: kv[0]):
            if not isinstance(entry, dict):
                continue
            st = _summarize_run(str(rid), entry)
            mf = Path(st.manifest_file) if st.manifest_file else None
            manifest = _read_json(mf) if mf and mf.exists() else None
            parents = manifest.get("parents") if isinstance(manifest, dict) else None
            if not isinstance(parents, list):
                continue
            now = _utc_now_dt()
            for p in parents:
                if not isinstance(p, dict):
                    continue
                pid = str(p.get("id") or "").strip()
                if not pid or p.get("end"):
                    continue
                parent_dir = Path(str(p.get("artifacts_dir") or "")).resolve()
                stuck, detail = _detect_no_progress(parent_dir=parent_dir, now=now, stuck_after_s=float(args.stuck_after_s))
                tokens_used = _read_tokens_used(parent_dir)
                token_cap = int(args.token_cap or 0)
                token_hit = token_cap > 0 and tokens_used is not None and int(tokens_used) >= token_cap
                print(
                    f"[watchdog] run_id={st.run_id} parent_id={pid} stuck={stuck} detail={detail} updated_utc={st.updated_utc}",
                    flush=True,
                )
                _append_jsonl(
                    events_path,
                    {
                        "ts_utc": _utc_now(),
                        "kind": "WATCHDOG_TICK",
                        "run_id": st.run_id,
                        "parent_id": pid,
                        "stuck": bool(stuck),
                        "detail": detail,
                        "tokens_used": tokens_used,
                        "token_cap": token_cap if token_cap > 0 else None,
                        "token_cap_hit": bool(token_hit),
                        "updated_utc": st.updated_utc,
                        "artifacts_dir": str(parent_dir),
                    },
                )
                if not stuck and not token_hit:
                    continue
                reason = f"watchdog_no_reaction {detail}" if stuck else f"watchdog_token_cap {tokens_used}>={token_cap}"
                payload = {"run_id": st.run_id, "parent_id": pid, "reason": reason}
                if args.dry_run:
                    print(f"[watchdog] DRY cancel {payload}", flush=True)
                    _append_jsonl(events_path, {"ts_utc": _utc_now(), "kind": "WATCHDOG_CANCEL_DRY", **payload})
                else:
                    code, body = _http_post(cancel_url, payload, timeout_s=8.0)
                    print(f"[watchdog] cancel run_id={st.run_id} parent_id={pid} http={code} body={body[:400]}", flush=True)
                    _append_jsonl(
                        events_path,
                        {
                            "ts_utc": _utc_now(),
                            "kind": "WATCHDOG_CANCEL",
                            **payload,
                            "http": int(code),
                            "body_head": (body or "")[:400],
                        },
                    )

        time.sleep(float(args.poll_s))


if __name__ == "__main__":
    raise SystemExit(main())
