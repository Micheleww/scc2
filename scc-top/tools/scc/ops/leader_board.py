#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leader Board (v0.1.0)

Goal:
- Provide a single, leader-facing dashboard for all dispatched CodexCLI runs:
  status/error/phase + token usage + quick links to artifacts paths.

Outputs:
- Markdown report under docs/REPORT/control_plane/
- JSON snapshot under docs/REPORT/control_plane/artifacts/

No network calls; deterministic file scan under artifacts/ only.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}

def _maybe_repo_rel(repo_root: Path, p: str) -> str:
    s = str(p or "").strip()
    if not s:
        return ""
    try:
        pp = Path(s).resolve()
        return str(pp.relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return s.replace("\\", "/")


def _try_read_text(path: Path, *, max_bytes: int = 200_000) -> str:
    try:
        b = path.read_bytes()
        if len(b) > max_bytes:
            b = b[:max_bytes]
        return b.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _list_automation_runs(repo_root: Path) -> List[Path]:
    base = (repo_root / "artifacts" / "scc_state" / "automation_runs").resolve()
    if not base.exists():
        return []
    runs = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        if (p / "automation_manifest.json").exists():
            runs.append(p)
    runs.sort(key=lambda x: x.name)
    return runs


def _iter_batch_response_files(run_dir: Path) -> List[Path]:
    out: List[Path] = []
    for p in run_dir.glob("*__response.json"):
        if p.is_file():
            out.append(p)
    out.sort(key=lambda x: x.name)
    return out


@dataclass
class ParentRow:
    automation_run_id: str
    codex_run_id: str
    parent_id: str
    status: str
    error: str
    phase: str
    tokens_used: Optional[int]
    artifacts_dir: str


def _load_parent_status(parent_dir: Path) -> Tuple[str, str]:
    """
    Returns (status, phase).
    """
    st = parent_dir / "status.json"
    if not st.exists():
        return "unknown", ""
    j = _read_json(st)
    status_raw = str(j.get("status") or j.get("phase") or "unknown")
    phase = str(j.get("phase") or "")
    return status_raw, phase


def _normalize_status(*, status_raw: str, exit_code: Optional[int], apply_ok: Optional[bool], err: str) -> str:
    """
    Normalize the unified_server per-parent status into: ok|fail|running|unknown.

    Rationale:
    - status.json often stores phases like collect_changes/apply_changes (not final verdict)
    - The leader board needs a stable, human-usable status.
    """
    if err:
        return "fail"
    if apply_ok is True and (exit_code is None or int(exit_code) == 0):
        return "ok"
    if apply_ok is False:
        return "fail"
    s = (status_raw or "").strip().lower()
    if s in {"ok", "pass", "passed", "success", "done"}:
        return "ok"
    if s in {"fail", "failed", "error", "canceled", "cancelled"}:
        return "fail"
    if s in {"running", "started", "collect_changes", "apply_changes", "planning", "executing"}:
        return "running"
    if s.startswith("collect_") or s.startswith("apply_"):
        return "running"
    return "unknown"


def _load_parent_error(parent_dir: Path) -> str:
    se = parent_dir / "scope_enforcement.json"
    if se.exists():
        j = _read_json(se)
        # common keys written by unified_server
        if isinstance(j.get("error"), str) and j.get("error"):
            return str(j.get("error"))
        if isinstance(j.get("apply_error"), str) and j.get("apply_error"):
            return str(j.get("apply_error"))
    return ""


def _load_tokens_used(parent_dir: Path) -> Optional[int]:
    u = parent_dir / "usage.json"
    if not u.exists():
        return None
    j = _read_json(u)
    try:
        v = j.get("tokens_used")
        return int(v) if v is not None else None
    except Exception:
        return None


def _latest_mtime(paths: list[Path]) -> Optional[float]:
    mt: Optional[float] = None
    for p in paths:
        try:
            if not p.exists():
                continue
            t = float(p.stat().st_mtime)
            if mt is None or t > mt:
                mt = t
        except Exception:
            continue
    return mt


def _heartbeat_age_s(parent_dir: Path) -> Optional[int]:
    candidates = [
        parent_dir / "status.json",
        parent_dir / "events.jsonl",
        parent_dir / "stdout.log",
        parent_dir / "stderr.log",
        parent_dir / "patch.diff",
        parent_dir / "scope_enforcement.json",
        parent_dir / "proc.json",
        parent_dir / "usage.json",
    ]
    mt = _latest_mtime(candidates)
    if mt is None:
        return None
    try:
        age = int(time.time() - mt)
        return max(0, age)
    except Exception:
        return None


def _tail_watchdog_events(repo_root: Path, *, max_lines: int = 60) -> List[dict]:
    p = (repo_root / "docs" / "DERIVED" / "dispatch" / "watchdog_events.jsonl").resolve()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    out: List[dict] = []
    for line in lines[-max(1, int(max_lines or 60)) :]:
        try:
            j = json.loads(line)
            if isinstance(j, dict):
                out.append(j)
        except Exception:
            continue
    return out


def _collect_parents_from_batch_response(
    *,
    automation_run_id: str,
    batch_response: dict,
) -> List[ParentRow]:
    resp = batch_response.get("response") if isinstance(batch_response.get("response"), dict) else {}
    codex_run_id = str(resp.get("run_id") or "")
    results = resp.get("results") if isinstance(resp.get("results"), list) else []
    out: List[ParentRow] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        pid = str(r.get("id") or "")
        artifacts_dir = str(r.get("artifacts_dir") or "")
        status_raw = "unknown"
        phase = ""
        tokens_used = None
        if artifacts_dir:
            pd = Path(artifacts_dir)
            status_raw, phase = _load_parent_status(pd)
            tokens_used = _load_tokens_used(pd)
        err = str(r.get("error") or "")
        exit_code = None
        try:
            exit_code = int(r.get("exit_code")) if r.get("exit_code") is not None else None
        except Exception:
            exit_code = None
        se_obj = r.get("scope_enforcement") if isinstance(r.get("scope_enforcement"), dict) else {}
        apply_ok = None
        if isinstance(se_obj, dict) and "apply_ok" in se_obj:
            apply_ok = bool(se_obj.get("apply_ok"))
        # prefer more specific apply error from scope_enforcement if present
        if artifacts_dir:
            se_err = _load_parent_error(Path(artifacts_dir))
            if se_err:
                err = se_err
        if not err and apply_ok is False:
            err = "apply_failed"

        status = _normalize_status(status_raw=status_raw, exit_code=exit_code, apply_ok=apply_ok, err=err)
        out.append(
            ParentRow(
                automation_run_id=automation_run_id,
                codex_run_id=codex_run_id,
                parent_id=pid,
                status=status,
                error=err,
                phase=phase,
                tokens_used=tokens_used,
                artifacts_dir=_maybe_repo_rel(_repo_root(), artifacts_dir),
            )
        )
    return out


def build_board(
    *,
    repo_root: Path,
    limit_runs: int,
) -> Tuple[dict, str]:
    runs = _list_automation_runs(repo_root)
    runs = runs[-max(1, int(limit_runs or 10)) :]

    rows: List[ParentRow] = []
    for rdir in runs:
        rid = rdir.name
        for rf in _iter_batch_response_files(rdir):
            batch = _read_json(rf)
            rows.extend(_collect_parents_from_batch_response(automation_run_id=rid, batch_response=batch))

    total = len(rows)
    ok_n = sum(1 for x in rows if x.status == "ok")
    fail_n = sum(1 for x in rows if x.status == "fail" or (x.error and x.status != "ok"))
    run_n = sum(1 for x in rows if x.status == "running")

    err_counts: Dict[str, int] = {}
    for x in rows:
        if not x.error:
            continue
        err_counts[x.error] = err_counts.get(x.error, 0) + 1
    top_err = sorted(err_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:12]

    token_rows = [(x.tokens_used or 0, x) for x in rows if x.tokens_used is not None]
    token_rows.sort(key=lambda t: (-t[0], t[1].parent_id))
    top_tokens = token_rows[:10]

    heartbeats: Dict[str, Optional[int]] = {}
    for x in rows:
        if not x.artifacts_dir:
            continue
        try:
            heartbeats[x.artifacts_dir] = _heartbeat_age_s(Path(x.artifacts_dir))
        except Exception:
            heartbeats[x.artifacts_dir] = None

    watchdog_events = _tail_watchdog_events(repo_root, max_lines=60)

    board = {
        "schema_version": "v0.1.0",
        "generated_at_utc": _utc_now(),
        "limit_runs": int(limit_runs),
        "counts": {"total": total, "ok": ok_n, "fail": fail_n, "running": run_n},
        "top_errors": [{"error": e, "count": c} for e, c in top_err],
        "top_tokens": [
            {
                "tokens_used": int(t),
                "automation_run_id": x.automation_run_id,
                "codex_run_id": x.codex_run_id,
                "parent_id": x.parent_id,
                "artifacts_dir": x.artifacts_dir,
            }
            for t, x in top_tokens
        ],
        "parents": [
            {
                "automation_run_id": x.automation_run_id,
                "codex_run_id": x.codex_run_id,
                "parent_id": x.parent_id,
                "status": x.status,
                "phase": x.phase,
                "error": x.error,
                "tokens_used": x.tokens_used,
                "artifacts_dir": x.artifacts_dir,
                "heartbeat_age_s": heartbeats.get(x.artifacts_dir),
            }
            for x in rows
        ],
        "watchdog_events_tail": watchdog_events,
    }

    # Markdown
    lines: List[str] = []
    lines.append("# Leader Board — Dispatch Waterfall (v0.1.0)")
    lines.append("")
    lines.append(f"- generated_at_utc: `{board['generated_at_utc']}`")
    lines.append(f"- automation_runs_scanned: `{len(runs)}`")
    lines.append(f"- totals: ok={ok_n} fail={fail_n} running={run_n} total={total}")
    lines.append("")
    if top_err:
        lines.append("## Top errors")
        for e, c in top_err:
            lines.append(f"- `{e}`: {c}")
        lines.append("")
    if top_tokens:
        lines.append("## Top token consumers")
        for t, x in top_tokens:
            lines.append(f"- tokens={t} parent=`{x.parent_id}` run=`{x.codex_run_id}` dir=`{x.artifacts_dir}`")
        lines.append("")
    lines.append("## Latest parents")
    lines.append("| status | phase | heartbeat_s | tokens | automation_run | codex_run | parent_id | error | artifacts_dir |")
    lines.append("|---|---|---:|---:|---|---|---|---|---|")
    for x in rows[-200:]:
        tok = "" if x.tokens_used is None else str(x.tokens_used)
        hb = ""
        if x.artifacts_dir:
            v = heartbeats.get(x.artifacts_dir)
            hb = "" if v is None else str(v)
        err = (x.error or "").replace("\n", " ")[:120]
        lines.append(f"| {x.status} | {x.phase} | {hb} | {tok} | {x.automation_run_id} | {x.codex_run_id} | {x.parent_id} | {err} | {x.artifacts_dir} |")
    lines.append("")
    if watchdog_events:
        lines.append("## Watchdog tail (events)")
        for ev in watchdog_events[-30:]:
            kind = str(ev.get("kind") or "")
            rid = str(ev.get("run_id") or "")
            pid = str(ev.get("parent_id") or "")
            detail = str(ev.get("detail") or ev.get("reason") or "")[:120].replace("\n", " ")
            ts = str(ev.get("ts_utc") or "")
            lines.append(f"- `{ts}` `{kind}` run=`{rid}` parent=`{pid}` {detail}")
        lines.append("")
    lines.append("## Ops")
    lines.append("- Watchdog (60s): `python tools/scc/ops/dispatch_watchdog.py --poll-s 60 --stuck-after-s 60`")
    lines.append("- Watchdog JSONL: `docs/DERIVED/dispatch/watchdog_events.jsonl`")
    lines.append("- Cancel a parent: `POST /executor/codex/cancel {run_id,parent_id,reason}` (see unified_server)")
    md = "\n".join(lines).strip() + "\n"
    return board, md


def main() -> int:
    ap = argparse.ArgumentParser(description="Leader board generator (leader-facing)")
    ap.add_argument("--limit-runs", type=int, default=int(os.environ.get("SCC_LEADERBOARD_LIMIT_RUNS", "10")))
    ap.add_argument("--out-md", default="", help="Output markdown path")
    ap.add_argument("--out-json", default="", help="Output json path")
    ap.add_argument("--write-latest", action="store_true", default=True)
    args = ap.parse_args()

    repo_root = _repo_root()
    board, md = build_board(repo_root=repo_root, limit_runs=int(args.limit_runs))

    stamp = time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())
    out_md = str(args.out_md or "").strip()
    if not out_md:
        out_md = f"docs/REPORT/control_plane/LEADER_BOARD__{stamp}.md"
    out_md_p = Path(out_md)
    if not out_md_p.is_absolute():
        out_md_p = (repo_root / out_md_p).resolve()
    out_md_p.parent.mkdir(parents=True, exist_ok=True)
    out_md_p.write_text(md, encoding="utf-8", errors="replace")

    out_json = str(args.out_json or "").strip()
    if not out_json:
        out_json = f"docs/REPORT/control_plane/artifacts/LEADER_BOARD__{stamp}/leader_board.json"
    out_json_p = Path(out_json)
    if not out_json_p.is_absolute():
        out_json_p = (repo_root / out_json_p).resolve()
    out_json_p.parent.mkdir(parents=True, exist_ok=True)
    out_json_p.write_text(json.dumps(board, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")

    if bool(args.write_latest):
        latest = (repo_root / "docs" / "REPORT" / "control_plane" / "LEADER_BOARD__LATEST.md").resolve()
        latest.write_text(md, encoding="utf-8", errors="replace")

    print(str(out_md_p))
    print(str(out_json_p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
