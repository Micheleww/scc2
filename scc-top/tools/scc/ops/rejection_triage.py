#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rejection triage (v0.1.0) — deterministic.

Purpose:
- Summarize why dispatched CodexCLI parents are failing (apply_failed / corrupt patch / etc.)
- Provide deterministic, low-token remediation actions.

Outputs:
- Markdown report under docs/REPORT/<area>/
- JSON snapshot under docs/REPORT/<area>/artifacts/
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def _utc_stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _date_utc() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def _find_latest_leader_board_json(repo_root: Path) -> Path | None:
    base = (repo_root / "docs" / "REPORT" / "control_plane" / "artifacts").resolve()
    if not base.exists():
        return None
    best: Tuple[float, Path] | None = None
    for p in base.glob("LEADER_BOARD__*/leader_board.json"):
        try:
            ts = p.stat().st_mtime
        except Exception:
            continue
        if best is None or ts > best[0]:
            best = (ts, p)
    return best[1] if best else None


def _count_by(items: List[dict], key: str) -> List[Tuple[str, int]]:
    m: Dict[str, int] = {}
    for x in items:
        v = str(x.get(key) or "").strip()
        if not v:
            continue
        m[v] = m.get(v, 0) + 1
    return sorted(m.items(), key=lambda kv: (-kv[1], kv[0]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic rejection triage report (leader-facing).")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="REJECTION_TRIAGE_V010")
    ap.add_argument("--limit-errors", type=int, default=12)
    ap.add_argument("--out-md", default="")
    ap.add_argument("--out-json", default="")
    args = ap.parse_args()

    repo_root = _repo_root()
    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "REJECTION_TRIAGE_V010"

    lb_json = _find_latest_leader_board_json(repo_root)
    if lb_json is None:
        print(json.dumps({"ok": False, "error": "leader_board_json_missing"}, ensure_ascii=False))
        return 2

    lb = _read_json(lb_json)
    parents = lb.get("parents") if isinstance(lb.get("parents"), list) else []
    top_errors = _count_by(parents, "error")[: max(1, int(args.limit_errors or 12))]

    # Heuristics
    has_apply_failed = any(e == "apply_failed" for e, _ in top_errors)
    has_corrupt_patch = any("corrupt patch" in e for e, _ in top_errors)
    has_truncated = any("truncated_or_corrupt" in e for e, _ in top_errors)
    has_patch_does_not_apply = any("patch does not apply" in e for e, _ in top_errors)

    recs: List[str] = []
    if has_apply_failed or has_corrupt_patch or has_truncated or has_patch_does_not_apply:
        recs.append("Prefer deterministic jobs for contract harden (avoid LLM patch for generated contracts).")
        recs.append("Enable automation fallback: apply_failed on generated contracts ⇒ run contract_harden_job and mark recovered.")
        recs.append("For LLM execute: enforce patch-only output + reduce context size + max_outstanding=1 + token_cap.")
        recs.append("Use watchdog 60s poll + stuck-after 60s; cancel parents with no heartbeat or token cap hit.")

    payload = {
        "ok": True,
        "schema_version": "v0.1.0",
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "area": area,
        "taskcode": taskcode,
        "leader_board_json": str(lb_json.relative_to(repo_root)).replace("\\", "/"),
        "counts": lb.get("counts") if isinstance(lb.get("counts"), dict) else {},
        "top_errors": [{"error": e, "count": c} for e, c in top_errors],
        "recommendations": recs,
    }

    # Markdown (no artifacts copying; link by path)
    lines: List[str] = []
    lines.append(f"# Rejection Triage — {taskcode} (v0.1.0)")
    lines.append("")
    lines.append(f"- generated_at_utc: `{payload['generated_at_utc']}`")
    lines.append(f"- leader_board_json: `{payload['leader_board_json']}`")
    counts = payload.get("counts") or {}
    lines.append(f"- counts: `{json.dumps(counts, ensure_ascii=False)}`")
    lines.append("")
    if top_errors:
        lines.append("## Top errors")
        for e, c in top_errors:
            lines.append(f"- `{e}`: {c}")
        lines.append("")
    if recs:
        lines.append("## Recommended actions (deterministic first)")
        for r in recs:
            lines.append(f"- {r}")
        lines.append("")
    lines.append("## Commands")
    lines.append("- Regenerate leader board: `python tools/scc/ops/leader_board.py --limit-runs 20`")
    lines.append("- Watchdog (60s): `python tools/scc/ops/dispatch_watchdog.py --base http://127.0.0.1:18788 --poll-s 60 --stuck-after-s 60 --token-cap 20000`")
    lines.append("- Factory loop (deterministic scope harden): `python tools/scc/ops/factory_loop_once.py --area control_plane --taskcode FACTORY_LOOP_ONCE_V010 --scope-harden-mode deterministic --execute-limit 0 --run-contracts 0`")
    lines.append("")

    stamp = _utc_stamp()
    out_md = str(args.out_md or "").strip()
    if not out_md:
        out_md = f"docs/REPORT/{area}/REPORT__{taskcode}__{_date_utc()}.md"
    out_json = str(args.out_json or "").strip()
    if not out_json:
        out_json = f"docs/REPORT/{area}/artifacts/{taskcode}__{stamp}/rejection_triage.json"

    out_md_p = (repo_root / out_md).resolve() if not Path(out_md).is_absolute() else Path(out_md).resolve()
    out_md_p.parent.mkdir(parents=True, exist_ok=True)
    out_md_p.write_text("\n".join(lines).strip() + "\n", encoding="utf-8", errors="replace")

    out_json_p = (repo_root / out_json).resolve() if not Path(out_json).is_absolute() else Path(out_json).resolve()
    out_json_p.parent.mkdir(parents=True, exist_ok=True)
    out_json_p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")

    print(str(out_md_p))
    print(str(out_json_p))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

