#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _safe_taskcode(s: str, *, max_len: int = 64) -> str:
    import re

    x = (s or "").strip()
    x = re.sub(r"[^A-Za-z0-9_]+", "_", x)
    x = re.sub(r"_+", "_", x).strip("_")
    if not x:
        x = "TASK"
    if len(x) > max_len:
        x = x[:max_len].rstrip("_")
    return x


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _append_line(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", errors="replace") as f:
        f.write(line.rstrip() + "\n")


def _repo_rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(_REPO_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def _run_cmd(cmd: str, *, cwd: Path, env: Dict[str, str], timeout_s: int) -> Tuple[int, str, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_s,
        shell=True,
    )
    return int(p.returncode), (p.stdout or ""), (p.stderr or "")


def _safe_reason(exit_code: int) -> str:
    return "exit_nonzero" if exit_code != 0 else "ok"


def _report_artifacts_dir(*, area: str, taskcode: str) -> Path:
    return (_REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / taskcode).resolve()

def _stable_task_verdict_dir(*, area: str, task_id: str) -> Path:
    """
    Stable, per-task verdict location (verifier-owned).

    Rationale:
    - Executor must not write under docs/REPORT/**.
    - Some contracts expect evidence paths like docs/REPORT/<area>/artifacts/<task_id>/*.
    - This file is small and acts as an index/pointer to the full deterministic evidence dir.
    """
    return (_REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / task_id).resolve()


def _run_evidence_triplet(*, env: Dict[str, str], taskcode: str, area: str, exit_code: int, notes: str, evidence: List[str]) -> None:
    args = [
        sys.executable,
        "tools/scc/ops/evidence_triplet.py",
        "--taskcode",
        taskcode,
        "--area",
        area,
        "--exit-code",
        str(int(exit_code)),
        "--notes",
        notes,
    ]
    for p in evidence:
        args.extend(["--evidence", p])
    subprocess.run(args, cwd=str(_REPO_ROOT), env=env)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a v0.1.0 contract for a given task_id and write artifacts/scc_tasks records.")
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--area", default="control_plane", help="AREA env used by mvm-verdict/validators.")
    ap.add_argument("--oid-dsn", default="", help="Set SCC_OID_PG_DSN for this run (or set env).")
    ap.add_argument("--timeout-s", type=int, default=600)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    task_id = str(args.task_id).strip()
    if not task_id:
        print(json.dumps({"ok": False, "error": "missing_task_id"}, ensure_ascii=False))
        return 2

    tasks_root = (Path(args.tasks_root) if Path(args.tasks_root).is_absolute() else (_REPO_ROOT / args.tasks_root)).resolve()
    task_dir = (tasks_root / task_id).resolve()
    task_json = task_dir / "task.json"
    if not task_json.exists():
        print(json.dumps({"ok": False, "error": "missing_task_json", "path": _repo_rel(task_json)}, ensure_ascii=False))
        return 3

    rec = _read_json(task_json)
    req = rec.get("request") if isinstance(rec.get("request"), dict) else {}
    contract_ref = str(req.get("contract_ref") or "").strip().replace("\\", "/")
    if not contract_ref:
        print(json.dumps({"ok": False, "error": "missing_contract_ref_in_task", "task_json": _repo_rel(task_json)}, ensure_ascii=False))
        return 4

    contract_path = (_REPO_ROOT / contract_ref).resolve() if not Path(contract_ref).is_absolute() else Path(contract_ref).resolve()
    if not contract_path.exists():
        print(json.dumps({"ok": False, "error": "missing_contract_file", "contract_ref": contract_ref}, ensure_ascii=False))
        return 5

    contract = _read_json(contract_path)
    acceptance = contract.get("acceptance") if isinstance(contract.get("acceptance"), dict) else {}
    checks = acceptance.get("checks") if isinstance(acceptance.get("checks"), list) else []
    checks = [c for c in checks if isinstance(c, dict)]

    now = _iso_now()
    evidence_root = (task_dir / "evidence" / "contract_runner").resolve()
    evidence_root.mkdir(parents=True, exist_ok=True)
    stdout_path = evidence_root / "stdout.txt"
    stderr_path = evidence_root / "stderr.txt"
    selftest_path = evidence_root / "selftest.log"
    verdict_path = evidence_root / "verdict.json"
    # Guard-compatible evidence triplet location (docs/REPORT/<area>/artifacts/<TASK_CODE>/...)
    run_taskcode = _safe_taskcode(f"CONTRACT_RUN__{task_id}")
    report_artifacts = _report_artifacts_dir(area=str(args.area).strip() or "control_plane", taskcode=run_taskcode)
    report_artifacts.mkdir(parents=True, exist_ok=True)
    report_stdout = report_artifacts / "contract_runner_stdout.txt"
    report_stderr = report_artifacts / "contract_runner_stderr.txt"
    report_selftest = report_artifacts / "selftest.log"

    if args.dry_run:
        print(json.dumps({"ok": True, "task_id": task_id, "contract_ref": contract_ref, "checks": len(checks)}, ensure_ascii=False, indent=2))
        return 0

    env = dict(os.environ)
    env["TASK_ID"] = task_id
    env["CONTRACT_REF"] = contract_ref
    # Critical: do not inherit outer TASK_CODE (e.g. factory loop taskcode). Use a dedicated per-task TASK_CODE
    # so mvm-verdict/skill_call_guard sees exactly one REPORT triplet.
    env["TASK_CODE"] = run_taskcode
    env["AREA"] = str(args.area).strip() or "control_plane"
    # Avoid writing to tracked `mvm/verdict/verdict.json` when contract acceptance includes mvm-verdict.
    env["MVM_VERDICT_OUT"] = _repo_rel(report_artifacts / "mvm_verdict.json")
    if str(args.oid_dsn).strip():
        env["SCC_OID_PG_DSN"] = str(args.oid_dsn).strip()

    events_path = task_dir / "events.jsonl"
    _append_line(events_path, json.dumps({"type": "task_submitted", "ts_utc": now, "task_id": task_id, "data": {"contract_ref": contract_ref}}, ensure_ascii=False))

    combined_stdout: List[str] = []
    combined_stderr: List[str] = []
    overall_exit = 0

    # Ensure mvm-verdict runs last, because it requires the report triplet (report+artifacts+hashes) to exist.
    def _is_mvm(cmd: str) -> bool:
        return "tools/ci/mvm-verdict.py" in (cmd or "").replace("\\", "/")

    ordered: List[dict] = []
    mvm: List[dict] = []
    for c in checks:
        cmd = str(c.get("command") or "").strip()
        (mvm if _is_mvm(cmd) else ordered).append(c)
    checks_ordered = ordered + mvm

    def _record_check(i: int, cmd: str, out: str, err: str, rc: int) -> None:
        combined_stdout.append(f"[check {i}] {cmd}\n{out}")
        combined_stderr.append(f"[check {i}] {cmd}\n{err}")
        _append_line(selftest_path, f"CMD[{i}]={cmd}")
        _append_line(selftest_path, f"Exit Code: {rc}")
        _append_line(report_selftest, f"CMD[{i}]={cmd}")
        _append_line(report_selftest, f"Exit Code: {rc}")

    # Preflight: run deterministic checks that do not depend on the REPORT triplet,
    # so we can create the triplet before running mvm-verdict (which requires it).
    preflight_cmds = [
        ("python -c \"import sys; print(sys.version)\"", _REPO_ROOT, 30),
        ("python tools/scc/ops/top_validator.py --registry docs/ssot/registry.json --out-dir artifacts/scc_state/top_validator", _REPO_ROOT, 120),
    ]
    # If OID DSN is available, include oid_validator (fail-closed).
    if env.get("SCC_OID_PG_DSN"):
        preflight_cmds.append((f"python tools/scc/ops/oid_validator.py --report-dir \"{_repo_rel(report_artifacts)}\"", _REPO_ROOT, 120))

    idx = 0
    for cmd, cwd, to in preflight_cmds:
        idx += 1
        rc, out, err = _run_cmd(cmd, cwd=cwd, env=env, timeout_s=int(to))
        _record_check(idx, cmd, out, err, rc)
        if rc != 0 and overall_exit == 0:
            overall_exit = rc

    # Ensure evidence files referenced by the triplet already exist before mvm-verdict runs the guard.
    report_stdout.write_text("\n\n".join(combined_stdout).strip() + "\n", encoding="utf-8", errors="replace")
    report_stderr.write_text("\n\n".join(combined_stderr).strip() + "\n", encoding="utf-8", errors="replace")

    # Create the report triplet BEFORE running any mvm-verdict checks.
    # This allows mvm-verdict basic to run its guard successfully when preflight passed.
    notes0 = "\n".join(
        [
            f"- contract_ref: `{contract_ref}`",
            f"- task_id: `{task_id}`",
            "- Preflight triplet: created before mvm-verdict so guard can run.",
        ]
    )
    _run_evidence_triplet(
        env=env,
        taskcode=run_taskcode,
        area=str(args.area).strip() or "control_plane",
        exit_code=int(overall_exit),
        notes=notes0,
        evidence=[
            f"docs/REPORT/{str(args.area).strip() or 'control_plane'}/artifacts/{run_taskcode}/contract_runner_stdout.txt",
            f"docs/REPORT/{str(args.area).strip() or 'control_plane'}/artifacts/{run_taskcode}/contract_runner_stderr.txt",
            f"docs/REPORT/{str(args.area).strip() or 'control_plane'}/artifacts/{run_taskcode}/selftest.log",
        ],
    )

    for i, c in enumerate(checks_ordered, start=1):
        cmd = str(c.get("command") or "").strip()
        if not cmd:
            continue
        cwd = _REPO_ROOT
        if c.get("cwd"):
            p = Path(str(c.get("cwd")).strip())
            cwd = (p if p.is_absolute() else (_REPO_ROOT / p)).resolve()
        timeout_s = int(c.get("timeout_s") or args.timeout_s)
        rc, out, err = _run_cmd(cmd, cwd=cwd, env=env, timeout_s=timeout_s)
        _record_check(idx + i, cmd, out, err, rc)
        if rc != 0 and overall_exit == 0:
            overall_exit = rc

    stdout_path.write_text("\n\n".join(combined_stdout).strip() + "\n", encoding="utf-8", errors="replace")
    stderr_path.write_text("\n\n".join(combined_stderr).strip() + "\n", encoding="utf-8", errors="replace")
    _append_line(selftest_path, f"EXIT_CODE={overall_exit}")

    report_stdout.write_text("\n\n".join(combined_stdout).strip() + "\n", encoding="utf-8", errors="replace")
    report_stderr.write_text("\n\n".join(combined_stderr).strip() + "\n", encoding="utf-8", errors="replace")
    _append_line(report_selftest, f"EXIT_CODE={overall_exit}")

    verdict = "PASS" if overall_exit == 0 else "FAIL"
    verdict_obj = {
        "verdict": verdict,
        "exit_code": overall_exit,
        "generated_utc": now,
        "evidence_paths": [
            _repo_rel(stdout_path),
            _repo_rel(stderr_path),
            _repo_rel(selftest_path),
        ],
    }
    if verdict != "PASS":
        verdict_obj["fail_class"] = _safe_reason(overall_exit)
    _write_json(verdict_path, verdict_obj)
    verdict_obj["evidence_paths"].append(_repo_rel(verdict_path))

    # Write a stable, per-task verdict pointer under docs/REPORT (verifier-owned).
    try:
        stable_dir = _stable_task_verdict_dir(area=str(args.area).strip() or "control_plane", task_id=task_id)
        stable_dir.mkdir(parents=True, exist_ok=True)
        stable_verdict = {
            "schema_version": "v0.1.0",
            "task_id": task_id,
            "contract_ref": contract_ref,
            "verdict": verdict,
            "exit_code": overall_exit,
            "generated_utc": now,
            "evidence_dir": _repo_rel(evidence_root),
            "report_artifacts_dir": _repo_rel(report_artifacts),
            "contract_runner_taskcode": run_taskcode,
        }
        _write_json(stable_dir / "verdict.json", stable_verdict)
    except Exception:
        pass

    # Refresh the fail-closed evidence triplet for this contract run (final exit code).
    notes = "\n".join(
        [
            f"- contract_ref: `{contract_ref}`",
            f"- task_id: `{task_id}`",
            "- Final triplet: refreshed after all checks (including mvm-verdict if present).",
        ]
    )
    _run_evidence_triplet(
        env=env,
        taskcode=run_taskcode,
        area=str(args.area).strip() or "control_plane",
        exit_code=int(overall_exit),
        notes=notes,
        evidence=[
            f"docs/REPORT/{str(args.area).strip() or 'control_plane'}/artifacts/{run_taskcode}/contract_runner_stdout.txt",
            f"docs/REPORT/{str(args.area).strip() or 'control_plane'}/artifacts/{run_taskcode}/contract_runner_stderr.txt",
            f"docs/REPORT/{str(args.area).strip() or 'control_plane'}/artifacts/{run_taskcode}/selftest.log",
        ],
    )

    # Update task record
    rec["updated_utc"] = now
    rec["status"] = "done" if verdict == "PASS" else "failed"
    rec["exit_code"] = overall_exit
    rec["verdict"] = verdict
    rec["evidence_dir"] = str(evidence_root)
    rec["out_dir"] = str(evidence_root)
    rec["selftest_log"] = str(selftest_path)
    rec["report_md"] = f"docs/REPORT/{str(args.area).strip() or 'control_plane'}/REPORT__{run_taskcode}__{datetime.now(timezone.utc).strftime('%Y%m%d')}.md"
    _write_json(task_json, rec)

    _append_line(
        events_path,
        json.dumps(
            {
                "type": "fullagent_executor_completed",
                "ts_utc": _iso_now(),
                "task_id": task_id,
                "data": {"success": verdict == "PASS", "exit_code": overall_exit, "reason_code": _safe_reason(overall_exit)},
            },
            ensure_ascii=False,
        ),
    )
    _append_line(events_path, json.dumps({"type": "TASK_VERIFIED", "ts_utc": _iso_now(), "task_id": task_id, "data": verdict_obj}, ensure_ascii=False))

    print(json.dumps({"ok": True, "task_id": task_id, "verdict": verdict, "exit_code": overall_exit, "evidence_dir": _repo_rel(evidence_root)}, ensure_ascii=False, indent=2))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
