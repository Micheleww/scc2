#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
EXEC_LOG_DIR = REPO_ROOT / "artifacts" / "executor_logs"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha1_text(s: str) -> str:
    h = hashlib.sha1()
    h.update(s.encode("utf-8", errors="replace"))
    return h.hexdigest()


def _read_jsonl_tail(path: pathlib.Path, tail: int = 3000) -> List[Dict[str, Any]]:
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


def _pattern_id(event_type: str, executor: Optional[str], stack: Optional[str], failing: Optional[str]) -> str:
    key = "|".join(
        [
            (event_type or "unknown").strip(),
            (executor or "").strip(),
            (stack or "").strip(),
            (failing or "").strip(),
        ]
    )
    sig = _sha1_text(key)[:10]
    name = (event_type or "unknown").strip().lower().replace(" ", "_")
    tool = (executor or "tool").strip().lower().replace(" ", "_")[:20]
    return f"auto.{name}.{tool}.{sig}"


def _group_key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    et = str(row.get("event_type") or row.get("type") or "unknown")
    executor = str(row.get("executor") or "unknown")
    reason = str(row.get("reason") or row.get("error") or "")
    stack = str(row.get("stacktrace_hash") or "")
    return (et, executor, reason, stack)


def _extract_failing_test(row: Dict[str, Any]) -> Optional[str]:
    ft = row.get("failing_tests")
    if isinstance(ft, list) and ft:
        return str(ft[0])
    return None


def mine_patterns(rows: List[Dict[str, Any]], min_count: int = 3) -> List[Dict[str, Any]]:
    buckets: Dict[Tuple[str, str, str, str], List[Dict[str, Any]]] = {}
    for r in rows:
        et = str(r.get("event_type") or "")
        if not et:
            continue
        # Focus on failures.
        if et not in {"CI_FAILED", "EXECUTOR_ERROR", "PREFLIGHT_FAILED", "PINS_INSUFFICIENT", "POLICY_VIOLATION"}:
            continue
        k = _group_key(r)
        buckets.setdefault(k, []).append(r)

    out: List[Dict[str, Any]] = []
    for (et, executor, reason, stack), items in sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True):
        if len(items) < int(min_count):
            continue
        last = items[-1]
        failing = _extract_failing_test(last)
        pid = _pattern_id(et, executor, stack, failing)
        created = _now_iso()
        out.append(
            {
                "schema_version": "scc.pattern.v1",
                "pattern_id": pid,
                "created_at": created,
                "updated_at": None,
                "severity": "P1",
                "match": {
                    "event_type": et,
                    "task_class": str(last.get("task_class") or "") or None,
                    "failing_test": failing,
                    "stacktrace_hash": stack or None,
                    "tool": executor or None,
                    "code": str(reason)[:120] or None,
                },
                "stats": {
                    "count": len(items),
                    "first_seen": str(items[0].get("t") or items[0].get("time") or created),
                    "last_seen": str(last.get("t") or last.get("time") or created),
                },
                "notes": f"Auto-mined cluster: event_type={et}, executor={executor}, reason={reason[:80]}",
            }
        )
    return out


def draft_playbook_for_pattern(pattern: Dict[str, Any]) -> Dict[str, Any]:
    pid = str(pattern.get("pattern_id") or "")
    match = pattern.get("match") if isinstance(pattern.get("match"), dict) else {}
    et = str(match.get("event_type") or "unknown")
    tool = str(match.get("tool") or "") or None

    playbook_id = f"pb.{pid}.v1"
    actions: List[Dict[str, Any]] = []
    actions.append({"type": "note", "params": {"message": f"Auto-draft playbook for pattern {pid} ({et})."}})

    if et == "PINS_INSUFFICIENT" or et == "PREFLIGHT_FAILED":
        actions.append({"type": "route", "lane": "fastlane", "role": "pinser", "params": {"reason": "auto_pins_fix"}})
    elif et == "CI_FAILED":
        actions.append({"type": "route", "lane": "fastlane", "role": "ci_fixup", "params": {"reason": "auto_ci_fixup"}})
        actions.append({"type": "run_smoke", "params": {"tier": "smoke"}})
    elif et == "EXECUTOR_ERROR":
        # Most common stabilization: switch executor away from flapping tool.
        preferred = "codex" if tool == "opencodecli" else "opencodecli"
        actions.append(
            {
                "type": "route",
                "params": {"preferred_executor": preferred, "fallback_executor": "codex", "note": "tooling_error_fallback"},
            }
        )
    elif et == "POLICY_VIOLATION":
        actions.append({"type": "open_dlq", "params": {"reason_code": "POLICY_VIOLATION"}})

    return {
        "schema_version": "scc.playbook.v1",
        "playbook_id": playbook_id,
        "version": "1.0.0",
        "pattern_id": pid,
        "lifecycle": {"stage": "draft", "updated_at": _now_iso()},
        "enablement": {
            "schema_version": "scc.enablement.v1",
            "status": "draft",
            "rollout": {"mode": "percent", "percent": 0},
            "rollback_conditions": [
                {"metric": "ci_failed_rate_15m", "op": ">", "threshold": 0.2},
                {"metric": "avg_retries", "op": ">", "threshold": 3},
            ],
        },
        "actions": actions,
        "notes": "Auto-generated draft; must pass eval_replay before publish.",
    }


def draft_skill_for_pattern(pattern: Dict[str, Any]) -> Dict[str, Any]:
    pid = str(pattern.get("pattern_id") or "")
    match = pattern.get("match") if isinstance(pattern.get("match"), dict) else {}
    et = str(match.get("event_type") or "unknown")
    tool = str(match.get("tool") or "unknown")

    skill_id = f"auto.fix.{pid}"
    return {
        "schema_version": "scc.skill.v1",
        "skill_id": skill_id,
        "version": "0.1.0",
        "owner_role": "lessons_miner",
        "summary": f"Auto-draft: mitigate pattern {pid} ({et}, tool={tool}).",
        "applies_to": {"task_class": ["*"]},
        "contracts": {
            "input_schema": "contracts/event/event.schema.json",
            "output_schema": "contracts/playbook/playbook.schema.json",
        },
        "budgets": {"max_files": 16, "max_pins_tokens": 8000},
        "quality_gates": {"must_include_matcher": True, "must_include_repro": True},
        "enablement": {"status": "draft", "rollout": {"mode": "percent", "percent": 0}},
        "notes": {
            "pattern_id": pid,
            "suggested_actions": [
                "Reproduce via replay_bundle, confirm minimal trigger.",
                "Apply smallest fix or pins tightening; avoid broad changes.",
                "Run smoke tier; if regression needed, enqueue to batchlane.",
            ],
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Mine patterns/playbook drafts from SCC event logs (offline, deterministic).")
    ap.add_argument("--tail", type=int, default=4000)
    ap.add_argument("--min-count", type=int, default=3)
    ap.add_argument("--out-patterns", default="patterns")
    ap.add_argument("--out-playbooks-drafts", default="playbooks/drafts")
    ap.add_argument("--out-skills-drafts", default="skills_drafts")
    args = ap.parse_args()

    events_path = EXEC_LOG_DIR / "state_events.jsonl"
    if not events_path.exists():
        print(f"FAIL: missing {events_path}")
        return 2

    rows = _read_jsonl_tail(events_path, tail=int(args.tail))
    patterns = mine_patterns(rows, min_count=int(args.min_count))
    if not patterns:
        print("OK: no clusters above threshold")
        return 0

    pat_dir = (REPO_ROOT / str(args.out_patterns)).resolve()
    pb_dir = (REPO_ROOT / str(args.out_playbooks_drafts)).resolve()
    skills_dir = (REPO_ROOT / str(args.out_skills_drafts)).resolve()
    pat_dir.mkdir(parents=True, exist_ok=True)
    pb_dir.mkdir(parents=True, exist_ok=True)
    skills_dir.mkdir(parents=True, exist_ok=True)

    wrote = 0
    wrote_skills = 0
    for p in patterns[:80]:
        pid = str(p.get("pattern_id") or "")
        if not pid:
            continue
        pat_path = pat_dir / f"{pid}.json"
        pat_path.write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pb = draft_playbook_for_pattern(p)
        pb_path = pb_dir / f"{pb['playbook_id']}.json"
        if not pb_path.exists():
            pb_path.write_text(json.dumps(pb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        sk = draft_skill_for_pattern(p)
        sk_path = skills_dir / f"{sk['skill_id']}.json"
        if not sk_path.exists():
            sk_path.write_text(json.dumps(sk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            wrote_skills += 1
        wrote += 1

    summary = {
        "schema_version": "scc.lesson_miner_summary.v1",
        "t": _now_iso(),
        "events_tail": int(args.tail),
        "min_count": int(args.min_count),
        "patterns_written": wrote,
        "skill_drafts_written": wrote_skills,
        "out_patterns": str(pathlib.Path(args.out_patterns).as_posix()),
        "out_playbooks_drafts": str(pathlib.Path(args.out_playbooks_drafts).as_posix()),
        "out_skills_drafts": str(pathlib.Path(args.out_skills_drafts).as_posix()),
    }
    (pat_dir / "auto_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Best-effort: keep registries in sync so schema gate stays deterministic.
    try:
        import subprocess

        subprocess.run(["python", "tools/scc/ops/patterns_registry_sync.py"], cwd=str(REPO_ROOT), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["python", "tools/scc/ops/skills_drafts_registry_sync.py"], cwd=str(REPO_ROOT), check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    print("OK")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
