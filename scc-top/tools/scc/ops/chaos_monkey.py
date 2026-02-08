#!/usr/bin/env python3
"""
Chaos Monkey Experiments (v1)

Design 12 low-cost, high-yield failure injection experiments and persist:
- plan.json (machine-readable)
- plan.md   (human-readable)

This script does NOT execute injections. It only outputs a plan that can be executed later.
"""

from __future__ import annotations

import argparse
import json
import os
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
        return json.loads(read_text(path) or "{}")
    except Exception:
        return None


def experiment(
    id: str,
    theme: str,
    injection: str,
    expected: str,
    observe: str,
    recovery: str,
    pass_criteria: str,
    cheapness: str = "cheap",
) -> Dict[str, Any]:
    return {
        "id": id,
        "theme": theme,
        "cheapness": cheapness,
        "injection": injection,
        "expected_reaction": expected,
        "observability": observe,
        "auto_recovery": recovery,
        "pass_criteria": pass_criteria,
    }


def build_plan(exec_log_dir: Path) -> Dict[str, Any]:
    failure_report = read_json(exec_log_dir / "failure_report_latest.json")
    five_whys = read_json(exec_log_dir / "five_whys" / "report.json")
    viral = read_json(exec_log_dir / "viral_selfcheck" / "defects.json")

    top_fail_reason = None
    try:
        br = (failure_report or {}).get("byReason") or []
        top_fail_reason = br[0]["reason"] if br else None
    except Exception:
        top_fail_reason = None

    top_taxonomy = None
    try:
        ts = (five_whys or {}).get("taxonomy_summary") or []
        top_taxonomy = ts[0]["taxonomy"] if ts else None
    except Exception:
        top_taxonomy = None

    experiments: List[Dict[str, Any]] = []

    # Executors crash/timeout/interruption
    experiments.append(
        experiment(
            id="exec_timeout_micro",
            theme="executor_timeout",
            injection="Create an atomic task with timeoutMs=2000 (2s) that runs a known slow command (e.g. `python -c \"import time; time.sleep(5)\"`).",
            expected="Job fails with reason=timeout quickly; CI gate marks failed; no endless retries; system remains responsive.",
            observe="jobs.jsonl (reason=timeout), failures.jsonl, leader.jsonl (warn_long/timeout patterns), /executor/debug/summary.",
            recovery="Auto-rescue should requeue only if fixup budget allows; otherwise mark failed and emit a feedback event (no storm).",
            pass_criteria="Timeout is detected and contained: no more than 1 retry; queue does not grow unbounded; system still dispatches other jobs.",
        )
    )
    experiments.append(
        experiment(
            id="exec_cancel_midrun",
            theme="executor_interruption",
            injection="Start a running job then call the cancel endpoint (/executor/jobs/:id/cancel).",
            expected="Job transitions to failed/canceled; task status reflects; evidence shows cancel reason; no zombie lease.",
            observe="jobs.jsonl status transitions; leader.jsonl cancel event; worker lease expiry events.",
            recovery="Auto-recovery should release lease and requeue only if allowed; else mark failed with clear reason.",
            pass_criteria="Cancel completes in <10s and leaves no running process; task is not duplicated; board state consistent.",
        )
    )
    experiments.append(
        experiment(
            id="exec_crash_bin_missing",
            theme="executor_crash",
            injection="Temporarily set CODEX_BIN to a non-existent path (or OPENCODE_BIN) and restart gateway, then dispatch a job.",
            expected="Jobs fail fast with missing_binary; system emits a high-severity feedback event; no silent hang.",
            observe="failures.jsonl reason=missing_binary; leader.jsonl feedback; /health still ok.",
            recovery="Auto-disable that executor pool (circuit breaker) and shift traffic to the healthy executor; alert via leader.jsonl.",
            pass_criteria="Failure is fast (<5s), contained, and traffic shifts; queue does not jam.",
        )
    )

    # Evidence missing/corruption
    experiments.append(
        experiment(
            id="evidence_missing_submit",
            theme="evidence_missing",
            injection="Force an executor to return done without SUBMIT (simulate by disabling SUBMIT parsing or crafting a response).",
            expected="CI gate rejects as missing_submit_contract; task fails; pins_fixup/ci_fixup is triggered (<=2).",
            observe="ci_gate_results.jsonl, verifier_failures.jsonl (missing_submit_contract), state_events.jsonl touched_files/tests_run null.",
            recovery="Auto-create a fixup task that restores SUBMIT contract and re-runs CI; otherwise fail-closed.",
            pass_criteria="No task can be marked done without SUBMIT evidence after CI_ENFORCE_SINCE; audit can adjudicate outcome.",
        )
    )
    experiments.append(
        experiment(
            id="evidence_corrupt_jsonl_line",
            theme="evidence_corruption",
            injection="Append a malformed JSON line to failures.jsonl/state_events.jsonl (1 line) and observe readers.",
            expected="Readers skip invalid lines (best-effort) without crashing; endpoints still respond; summaries ignore corrupt line.",
            observe="/executor/debug/summary, /events, leader.jsonl warnings (but process stays alive).",
            recovery="Add a 'log_sanitizer' job: quarantine invalid lines into *.corrupt with offset; continue processing.",
            pass_criteria="Gateway does not crash; summary endpoints still return; corrupt data is quarantined and count reported.",
        )
    )

    # Patch conflict / dirty worktree
    experiments.append(
        experiment(
            id="patch_conflict_same_hunk",
            theme="patch_conflict",
            injection="Dispatch two atomic tasks that both modify the same file and overlapping lines (same hunk) in the same repo.",
            expected="Second task fails with conflict or CI fails; system detects dirty worktree; prevents silent overwrite.",
            observe="git diff status in CI/selftest logs; failures.jsonl signature=conflict; touched_files overlap.",
            recovery="Auto create 'rebase/resolve' fixup task OR block with explicit conflict evidence; do not auto-merge blindly.",
            pass_criteria="No silent corruption: conflict is surfaced, evidence captured, and a deterministic resolution path is created.",
        )
    )
    experiments.append(
        experiment(
            id="dirty_worktree_untracked",
            theme="dirty_worktree",
            injection="Create untracked/modified files in execRoot before running a task; run a task that expects clean repo.",
            expected="Preflight detects dirty status and blocks or snapshots; CI fails with clear message; no task marks done.",
            observe="CI output includes git status; state_events tests_run shows preflight; leader.jsonl dispatch_rejected or ci_failed.",
            recovery="Auto task to clean/snapshot workspace (or run in isolated worktree) and retry once.",
            pass_criteria="Tasks either run in isolation or block fast; no patch applies on unknown dirty base.",
        )
    )

    # Queue blocking / duplicate consumption
    experiments.append(
        experiment(
            id="queue_starvation_split_flood",
            theme="queue_blocking",
            injection="Create 50 parent tasks and trigger split so board_split fills the queue; observe atomic starvation.",
            expected="Atomic execution retains a minimum reserved concurrency; split jobs are rate-limited.",
            observe="/executor/debug/summary, /executor/jobs (taskType distribution), leader.jsonl flow_bottleneck events.",
            recovery="Enable pool separation: split pool cap + atomic reserved; activate FIXUP_FUSE under backlog.",
            pass_criteria="Even under split flood, atomic keeps >=2 running; queued does not grow monotonically for >10min.",
        )
    )
    experiments.append(
        experiment(
            id="duplicate_dispatch_race",
            theme="duplicate_consumption",
            injection="Simulate two dispatchers racing: call dispatch twice for the same task quickly (or restart mid-dispatch).",
            expected="Dispatch idempotency prevents second active job; duplicates are rejected and logged.",
            observe="leader.jsonl dispatch_rejected/dispatch_quality_gate; jobs.jsonl shows at most one active job per task.",
            recovery="Hard lock by task_id; reconciliation job marks duplicates canceled.",
            pass_criteria="No duplicate running jobs exist for same task_id; board state remains consistent.",
        )
    )

    # External dependency unavailable
    experiments.append(
        experiment(
            id="external_upstream_down",
            theme="external_dependency",
            injection="Stop SCC upstream (18789) or OpenCode upstream (18790) temporarily, keep gateway running.",
            expected="Gateway /health still ok; proxy routes show upstream down; tasks that need upstream fail fast with clear reason.",
            observe="/health, /pools, proxy error logs; leader.jsonl network_error.",
            recovery="Circuit-break proxy routes; queue tasks needing upstream into blocked/backoff; auto-retry when upstream recovers.",
            pass_criteria="Gateway stays alive; failures are classified; no infinite retries; recovery resumes automatically.",
        )
    )
    experiments.append(
        experiment(
            id="model_api_throttle",
            theme="external_dependency",
            injection="Induce rate limit (set very high concurrency briefly or use a mock that returns 429) and observe classification.",
            expected="Failures classified rate_limited; backoff applied; no token explosion from retries; executor pool throttles.",
            observe="failures.jsonl reason=rate_limited; leader.jsonl throttle events; queue latency rises but stabilizes.",
            recovery="Adaptive concurrency reduction; switch to free pool / cached prompts; exponential backoff with jitter.",
            pass_criteria="System stabilizes under throttle; retries bounded; throughput degrades gracefully.",
        )
    )
    experiments.append(
        experiment(
            id="disk_full_simulated",
            theme="infra_storage",
            injection="Simulate write failure by making artifacts/executor_logs read-only (ACL) or pointing EXEC_LOG_DIR to unwritable path (in a test run).",
            expected="Gateway continues serving but logs best-effort; tasks fail-closed if evidence cannot be written; alerts emitted.",
            observe="leader.jsonl log_write_failed; missing evidence detected by CI gate; /executor/debug endpoints still respond.",
            recovery="Fallback to secondary log dir; stop dispatch when evidence cannot be persisted (radius control).",
            pass_criteria="No 'done without logs'; system halts dispatch rather than losing evidence; recovery restores normal logging.",
        )
    )

    # Where SCC will fail today (probability-ranked) based on current logs.
    likely_fail_points: List[Dict[str, Any]] = []
    likely_fail_points.append(
        {
            "rank": 1,
            "where": "occli meta-instruction 'Follow the attached file...' -> File not found storm",
            "why": "Recent failures dominated by this signature (see failure_report_latest + five_whys taxonomy).",
            "probability": "very_high",
        }
    )
    likely_fail_points.append(
        {
            "rank": 2,
            "where": "Queue starvation: board_split fills codex concurrency, atomic work stalls",
            "why": "queued is high and many jobs are board_split; no explicit split/atomic pool separation enforced at runtime.",
            "probability": "high",
        }
    )
    likely_fail_points.append(
        {
            "rank": 3,
            "where": "Evidence contract drift: done without SUBMIT/tests_run slips past without strict gates (if not restarted)",
            "why": "Some gates/hook endpoints require restart; running process may drift from repo code.",
            "probability": "high",
        }
    )
    likely_fail_points.append(
        {
            "rank": 4,
            "where": "Version drift / endpoints 404: new observability not active until restart",
            "why": "Observed 404 for /executor/debug/token_cfo earlier indicates mismatch between code and running process.",
            "probability": "medium_high",
        }
    )
    likely_fail_points.append(
        {
            "rank": 5,
            "where": "Patch conflict/dirty worktree leading to CI flakiness or silent overwrite (without isolation)",
            "why": "Multiple tasks can touch same repo concurrently; isolation isn't guaranteed.",
            "probability": "medium",
        }
    )

    return {
        "version": "v1",
        "generated_at": iso_now(),
        "inputs": {
            "failure_report_latest": str(exec_log_dir / "failure_report_latest.json"),
            "five_whys_report": str(exec_log_dir / "five_whys" / "report.json"),
            "viral_selfcheck": str(exec_log_dir / "viral_selfcheck" / "defects.json"),
            "top_fail_reason": top_fail_reason,
            "top_taxonomy": top_taxonomy,
        },
        "experiments": experiments,
        "likely_fail_points_today": likely_fail_points,
    }


def render_md(plan: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append("# Chaos Monkey Plan v1")
    lines.append("")
    lines.append(f"- generated_at: `{plan.get('generated_at')}`")
    inputs = plan.get("inputs") or {}
    lines.append(f"- top_taxonomy: `{inputs.get('top_taxonomy')}` top_fail_reason: `{inputs.get('top_fail_reason')}`")
    lines.append("")
    lines.append("## Experiments (12)")
    lines.append("")
    for i, e in enumerate(plan.get("experiments") or [], start=1):
        lines.append(f"{i}. **{e.get('id')}** — theme=`{e.get('theme')}` cheapness=`{e.get('cheapness')}`")
        lines.append(f"   - 注入方式: {e.get('injection')}")
        lines.append(f"   - 预期系统反应: {e.get('expected_reaction')}")
        lines.append(f"   - 观测点: {e.get('observability')}")
        lines.append(f"   - 自动恢复策略: {e.get('auto_recovery')}")
        lines.append(f"   - 通过标准: {e.get('pass_criteria')}")
        lines.append("")
    lines.append("## Where SCC Will Break Today (Probability-Ranked)")
    lines.append("")
    for row in plan.get("likely_fail_points_today") or []:
        lines.append(f"- {row.get('rank')}. {row.get('where')} (prob={row.get('probability')}) — {row.get('why')}")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exec-log-dir", default=_default_exec_log_dir())
    args = ap.parse_args()

    log_dir = Path(args.exec_log_dir)
    out_dir = log_dir / "chaos"
    out_dir.mkdir(parents=True, exist_ok=True)

    plan = build_plan(log_dir)
    (out_dir / "plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "plan.md").write_text(render_md(plan), encoding="utf-8-sig")
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

