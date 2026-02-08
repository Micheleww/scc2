#!/usr/bin/env python3
"""
Chaos Runner (v1)

This is a SAFE-by-default runner for chaos experiments:
- Default mode is dry-run: generates an evidence pack describing what would be injected.
- Confirm mode requires env var CHAOS_CONFIRM=1, otherwise it refuses to execute.

Artifacts:
<exec_log_dir>/chaos/runs/<run_id>/
  - manifest.json   (machine-readable)
  - run.md          (human-readable evidence pack)

Note:
This runner currently does not execute destructive actions. It is meant to be the
minimal "plumbing" so SCC can later automate chaos in a controlled way.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _default_repo_root() -> Path:
    # scc-top/tools/scc/ops/*.py -> repo root is 4 levels up
    return Path(os.environ.get("SCC_REPO_ROOT") or Path(__file__).resolve().parents[4]).resolve()


def _default_exec_log_dir() -> str:
    return os.environ.get("EXEC_LOG_DIR") or str(_default_repo_root() / "artifacts" / "executor_logs")


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(read_text(path) or "{}")
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def write_json(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def render_run_md(manifest: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Chaos Run v1 (Evidence Pack)")
    lines.append("")
    lines.append(f"- run_id: `{manifest.get('run_id')}`")
    lines.append(f"- generated_at: `{manifest.get('generated_at')}`")
    lines.append(f"- mode: `{manifest.get('mode')}`")
    lines.append(f"- plan: `{manifest.get('plan_path')}`")
    lines.append("")
    lines.append("## Experiments")
    lines.append("")
    for i, ex in enumerate(manifest.get("experiments") or [], start=1):
        lines.append(f"{i}. **{ex.get('id')}** theme=`{ex.get('theme')}`")
        lines.append(f"   - injection: {ex.get('injection')}")
        lines.append(f"   - expected_reaction: {ex.get('expected_reaction')}")
        lines.append(f"   - observability: {ex.get('observability')}")
        lines.append(f"   - auto_recovery: {ex.get('auto_recovery')}")
        lines.append(f"   - pass_criteria: {ex.get('pass_criteria')}")
        lines.append(f"   - status: `{ex.get('status')}`")
        lines.append("")
    lines.append("## Notes")
    lines.append("")
    for n in manifest.get("notes") or []:
        lines.append(f"- {n}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exec-log-dir", default=_default_exec_log_dir())
    ap.add_argument("--plan", default="")
    ap.add_argument("--run-id", default="")
    ap.add_argument("--mode", choices=["dry-run", "confirm"], default="dry-run")
    ap.add_argument("--only", default="", help="Comma-separated experiment ids to include (optional)")
    args = ap.parse_args()

    exec_log_dir = Path(args.exec_log_dir)
    plan_path = Path(args.plan) if args.plan else (exec_log_dir / "chaos" / "plan.json")
    plan = read_json(plan_path)
    if not plan:
        raise SystemExit(f"plan_missing: {plan_path}")

    run_id = args.run_id.strip() or time.strftime("%Y%m%d_%H%M%S")
    out_dir = exec_log_dir / "chaos" / "runs" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    only = [x.strip() for x in args.only.split(",") if x.strip()] if args.only else []
    exps = plan.get("experiments") or []
    if only:
        exps = [e for e in exps if str(e.get("id") or "") in only]

    mode = args.mode
    confirm_ok = os.environ.get("CHAOS_CONFIRM") == "1"
    if mode == "confirm" and not confirm_ok:
        mode = "dry-run"

    experiments_out: List[Dict[str, Any]] = []
    for e in exps:
        experiments_out.append(
            {
                "id": e.get("id"),
                "theme": e.get("theme"),
                "injection": e.get("injection"),
                "expected_reaction": e.get("expected_reaction"),
                "observability": e.get("observability"),
                "auto_recovery": e.get("auto_recovery"),
                "pass_criteria": e.get("pass_criteria"),
                "status": "planned" if mode == "dry-run" else "blocked_confirm_missing" if not confirm_ok else "todo",
            }
        )

    notes = [
        "Safe-by-default: this run is a plan/evidence pack only unless CHAOS_CONFIRM=1 and mode=confirm.",
        "For destructive injections, implement explicit rollback steps and run in an isolated worktree first.",
    ]
    if args.mode == "confirm" and not confirm_ok:
        notes.append("Requested mode=confirm but CHAOS_CONFIRM!=1, so mode was downgraded to dry-run.")

    manifest = {
        "version": "v1",
        "run_id": run_id,
        "generated_at": iso_now(),
        "mode": mode,
        "plan_path": str(plan_path),
        "experiments": experiments_out,
        "notes": notes,
    }

    write_json(out_dir / "manifest.json", manifest)
    (out_dir / "run.md").write_text(render_run_md(manifest), encoding="utf-8-sig")
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

