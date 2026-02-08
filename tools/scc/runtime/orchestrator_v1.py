#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _append_jsonl(path: pathlib.Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _factory_policy() -> Dict[str, Any]:
    fp = REPO_ROOT / "factory_policy.json"
    if not fp.exists():
        return {}
    try:
        data = _load_json(fp)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _wip_limits(policy: Dict[str, Any]) -> Tuple[int, int, int]:
    wl = policy.get("wip_limits") if isinstance(policy.get("wip_limits"), dict) else {}
    return (
        int(wl.get("WIP_TOTAL_MAX", 12)),
        int(wl.get("WIP_EXEC_MAX", 4)),
        int(wl.get("WIP_BATCH_MAX", 1)),
    )


def _lane_for_child(child: Dict[str, Any], policy: Dict[str, Any]) -> str:
    # Minimal: use task_class_id if present.
    cls = str(child.get("task_class_id") or "").strip()
    if cls in {"eval", "replay", "index", "lessons"}:
        return "batchlane"
    return "mainlane"


def _count_running() -> Dict[str, int]:
    # Treat artifacts/<task_id>/orchestrator.lock as running marker.
    out = {"total": 0, "exec": 0, "batch": 0}
    base = REPO_ROOT / "artifacts"
    if not base.exists():
        return out
    for p in base.iterdir():
        if not p.is_dir():
            continue
        if (p / "orchestrator.lock").exists():
            out["total"] += 1
            lane = "mainlane"
            try:
                meta = _load_json(p / "orchestrator_meta.json")
                lane = str(meta.get("lane") or "mainlane")
            except Exception:
                lane = "mainlane"
            if lane == "batchlane":
                out["batch"] += 1
            else:
                out["exec"] += 1
    return out


def _acquire_lock(task_id: str, lane: str) -> pathlib.Path:
    art = REPO_ROOT / "artifacts" / task_id
    art.mkdir(parents=True, exist_ok=True)
    lock = art / "orchestrator.lock"
    lock.write_text(_now_iso() + "\n", encoding="utf-8")
    _write_json(art / "orchestrator_meta.json", {"schema_version": "scc.orchestrator_meta.v1", "t": _now_iso(), "task_id": task_id, "lane": lane})
    return lock


def _release_lock(lock: pathlib.Path) -> None:
    try:
        lock.unlink()
    except Exception:
        return


def main() -> int:
    ap = argparse.ArgumentParser(description="SCC Orchestrator v1 (local, deterministic): enforce lanes/WIP and run runtime state machine.")
    ap.add_argument("--child", required=True, help="Child task JSON")
    ap.add_argument("--task-id", default="", help="Task id (default uuid4)")
    ap.add_argument("--lane", default="", help="Lane override (fastlane/mainlane/batchlane/dlq/quarantine)")
    ap.add_argument("--executor", default="noop", choices=["noop", "command", "codex_diff"], help="Executor mode for runtime")
    ap.add_argument("--executor-cmd", default="", help="If executor=command, command to run")
    ap.add_argument("--snapshot", action="store_true", help="Snapshot+rollback primitive")
    ap.add_argument("--codex-bin", default="codex", help="Codex CLI binary")
    ap.add_argument("--codex-model", default="", help="Codex model")
    ap.add_argument("--enforce-wip", action="store_true", help="Fail-closed if WIP limits exceeded (default: queue by sleeping).")
    ap.add_argument("--queue-wait-s", type=int, default=300, help="Max seconds to wait for WIP budget")
    args = ap.parse_args()

    child_path = (REPO_ROOT / str(args.child)).resolve()
    if not child_path.exists():
        print(f"FAIL: missing child {child_path}")
        return 2
    child = _load_json(child_path)
    if not isinstance(child, dict):
        print("FAIL: child not object")
        return 2

    policy = _factory_policy()
    task_id = str(args.task_id or "").strip() or str(uuid.uuid4())
    lane = (str(args.lane or "").strip() or _lane_for_child(child, policy)).strip() or "mainlane"

    # WIP enforcement
    total_max, exec_max, batch_max = _wip_limits(policy)
    deadline = time.time() + max(1, int(args.queue_wait_s))
    while True:
        running = _count_running()
        over = (
            running["total"] >= total_max
            or (lane == "batchlane" and running["batch"] >= batch_max)
            or (lane != "batchlane" and running["exec"] >= exec_max)
        )
        if not over:
            break
        if args.enforce_wip:
            art = REPO_ROOT / "artifacts" / task_id
            art.mkdir(parents=True, exist_ok=True)
            _append_jsonl(
                REPO_ROOT / "artifacts" / "executor_logs" / "state_events.jsonl",
                {
                    "schema_version": "scc.event.v1",
                    "t": _now_iso(),
                    "event_type": "EXECUTOR_ERROR",
                    "task_id": task_id,
                    "parent_id": None,
                    "role": "stability_controller",
                    "area": "orchestrator",
                    "executor": "internal",
                    "model": None,
                    "reason": "wip_limit_exceeded",
                    "details": {"lane": lane, "running": running, "limits": {"total": total_max, "exec": exec_max, "batch": batch_max}},
                },
            )
            print("FAIL: WIP limit exceeded")
            return 1
        if time.time() >= deadline:
            print("FAIL: queue wait timeout")
            return 1
        time.sleep(2)

    lock = _acquire_lock(task_id, lane)
    try:
        _append_jsonl(
            REPO_ROOT / "artifacts" / "executor_logs" / "state_events.jsonl",
            {"schema_version": "scc.event.v1", "t": _now_iso(), "event_type": "SUCCESS", "task_id": task_id, "parent_id": None, "role": "factory_manager", "area": "orchestrator", "executor": "internal", "model": None, "reason": "orchestrator_started", "details": {"lane": lane}},
        )
        # Run runtime pipeline.
        cmd: List[str] = [
            "python",
            "tools/scc/runtime/run_child_task.py",
            "--child",
            str(child_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "--task-id",
            task_id,
            "--executor",
            args.executor,
        ]
        if args.executor == "command":
            cmd += ["--executor-cmd", str(args.executor_cmd)]
        if args.executor == "codex_diff":
            cmd += ["--codex-bin", str(args.codex_bin), "--codex-model", str(args.codex_model or "")]
        if args.snapshot:
            cmd += ["--snapshot"]
        p = subprocess.run(cmd, cwd=str(REPO_ROOT), env={**os.environ, "SCC_REPO_ROOT": str(REPO_ROOT)})
        exit_code = int(p.returncode)
        # VERIFY is inside run_child_task; we also log orchestration result.
        _append_jsonl(
            REPO_ROOT / "artifacts" / "executor_logs" / "state_events.jsonl",
            {"schema_version": "scc.event.v1", "t": _now_iso(), "event_type": "SUCCESS" if exit_code == 0 else "CI_FAILED", "task_id": task_id, "parent_id": None, "role": "factory_manager", "area": "orchestrator", "executor": "internal", "model": None, "reason": "orchestrator_finished", "details": {"exit_code": exit_code}},
        )
        print("OK" if exit_code == 0 else "FAIL")
        print(f"task_id={task_id} lane={lane} exit_code={exit_code}")
        return 0 if exit_code == 0 else 1
    finally:
        _release_lock(lock)


if __name__ == "__main__":
    raise SystemExit(main())
