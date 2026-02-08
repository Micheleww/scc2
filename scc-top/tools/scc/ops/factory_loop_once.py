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


REPO_ROOT = Path(__file__).resolve().parents[3]


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _to_repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _run(cmd: List[str], *, env: Dict[str, str], timeout_s: Optional[int] = None) -> Tuple[int, str, str]:
    p = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s if timeout_s else None,
    )
    return int(p.returncode), (p.stdout or ""), (p.stderr or "")


def _parse_out_dir(stdout: str) -> Optional[str]:
    for line in (stdout or "").splitlines():
        line = line.strip()
        if line.startswith("out_dir="):
            return line.split("=", 1)[1].strip()
    return None


def _parse_json_from_mixed_stdout(stdout: str) -> Optional[Dict[str, Any]]:
    """
    Many SCC ops print a few human-readable lines before the final JSON.
    This helper extracts the last JSON object from stdout deterministically.
    """
    s = (stdout or "").strip()
    if not s:
        return None
    # Fast path
    try:
        j = json.loads(s)
        return j if isinstance(j, dict) else None
    except Exception:
        pass
    # Try from last '{' to end
    for idx in [s.rfind("{"), s.find("{")]:
        if idx < 0:
            continue
        frag = s[idx:].strip()
        try:
            j = json.loads(frag)
            return j if isinstance(j, dict) else None
        except Exception:
            continue
    return None


def _artifacts_dir(area: str, taskcode: str) -> Path:
    return (REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / taskcode).resolve()


def _evidence_triplet(*, env: Dict[str, str], taskcode: str, area: str, exit_code: int, notes: str, evidence: List[str]) -> None:
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
    subprocess.run(args, cwd=str(REPO_ROOT), env=env)


def _iter_task_ids(task_tree: Path, *, limit: int) -> List[str]:
    if int(limit or 0) <= 0:
        return []
    try:
        tree = _read_json(task_tree)
    except Exception:
        return []
    out: List[str] = []
    epics = tree.get("epics") if isinstance(tree.get("epics"), list) else []
    for e in epics:
        if not isinstance(e, dict):
            continue
        caps = e.get("capabilities") if isinstance(e.get("capabilities"), list) else []
        for c in caps:
            if not isinstance(c, dict):
                continue
            tasks = c.get("tasks") if isinstance(c.get("tasks"), list) else []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                tid = str(t.get("task_id") or "").strip()
                if tid:
                    out.append(tid)
                if len(out) >= int(limit):
                    return out
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description="FACTORY_LOOP_ONCE (v0.1.0): task_tree → contractize → scope_harden → execute+verify (LLM) → local acceptance → review → DoD audit."
    )
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="FACTORY_LOOP_ONCE_V010")
    ap.add_argument("--base", default=os.environ.get("SCC_BASE_URL", "http://127.0.0.1:18788"))
    ap.add_argument("--model", default=os.environ.get("A2A_CODEX_MODEL", "gpt-5.2"))
    ap.add_argument("--timeout-s", type=int, default=int(os.environ.get("A2A_CODEX_TIMEOUT_SEC", "1800")))
    ap.add_argument("--max-outstanding", type=int, default=int(os.environ.get("SCC_AUTOMATION_MAX_OUTSTANDING", "1")))
    ap.add_argument("--poll-s", type=int, default=60)
    ap.add_argument("--stuck-after-s", type=int, default=60)
    ap.add_argument("--token-cap", type=int, default=20000, help="Cancel LLM parents when tokens_used reaches this cap (0 disables).")
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--run-mvm", action="store_true", help="Run mvm-verdict basic as part of review_job_run (deterministic).")

    ap.add_argument("--run-secretary", action="store_true", help="Regenerate Goal Brief deterministically from WebGPT exports.")
    ap.add_argument("--goal-brief", default="docs/DERIVED/secretary/GOAL_BRIEF__LATEST.md")
    ap.add_argument("--input-root", default="docs/INPUTS/WEBGPT")
    ap.add_argument("--task-tree", default="docs/DERIVED/task_tree.json")
    ap.add_argument("--regen-task-tree", action="store_true", help="Regenerate task_tree from input-root even if it exists.")

    ap.add_argument("--contractize-limit", type=int, default=10)
    ap.add_argument("--scope-harden-limit", type=int, default=5)
    ap.add_argument(
        "--scope-harden-mode",
        default="deterministic",
        choices=["deterministic", "llm", "both"],
        help="Scope harden mode. deterministic reduces tokens and avoids patch corruption; llm expands scope/acceptance.",
    )
    ap.add_argument("--execute-limit", type=int, default=2)
    ap.add_argument("--run-contracts", type=int, default=2, help="Run local acceptance for up to N task_ids after execution (default: 2).")
    args = ap.parse_args()

    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "FACTORY_LOOP_ONCE_V010"
    base = str(args.base).strip() or "http://127.0.0.1:18788"
    model = str(args.model).strip() or "gpt-5.2"

    env = dict(os.environ)
    env["AREA"] = area
    env["TASK_CODE"] = taskcode

    artifacts = _artifacts_dir(area, taskcode)
    artifacts.mkdir(parents=True, exist_ok=True)
    summary_path = artifacts / "factory_loop_summary.json"

    goal_brief = (REPO_ROOT / str(args.goal_brief)).resolve() if not Path(args.goal_brief).is_absolute() else Path(args.goal_brief).resolve()
    input_root = (REPO_ROOT / str(args.input_root)).resolve() if not Path(args.input_root).is_absolute() else Path(args.input_root).resolve()
    task_tree = (REPO_ROOT / str(args.task_tree)).resolve() if not Path(args.task_tree).is_absolute() else Path(args.task_tree).resolve()

    steps: List[Dict[str, Any]] = []
    rc_all = 0

    def record(step: str, rc: int, cmd: List[str], stdout: str = "", stderr: str = "") -> None:
        nonlocal rc_all
        steps.append({"step": step, "rc": int(rc), "cmd": " ".join(cmd), "stdout_head": (stdout or "")[:800], "stderr_head": (stderr or "")[:800]})
        if rc != 0 and rc_all == 0:
            rc_all = rc

    def record_nonfatal(step: str, rc: int, cmd: List[str], stdout: str = "", stderr: str = "") -> None:
        steps.append({"step": step, "rc": int(rc), "cmd": " ".join(cmd), "stdout_head": (stdout or "")[:800], "stderr_head": (stderr or "")[:800], "nonfatal": True})

    # 0) Optional: Secretary produces Goal Brief deterministically (no LLM).
    if bool(args.run_secretary):
        cmd = [
            sys.executable,
            "tools/scc/ops/secretary_goal_brief_from_webgpt.py",
            "--input-root",
            _to_repo_rel(input_root),
            "--out",
            _to_repo_rel(goal_brief),
        ]
        rc, out, err = _run(cmd, env=env, timeout_s=120)
        record("secretary_goal_brief", rc, cmd, out, err)

    # 1) Ensure / optionally regenerate derived task_tree.json
    if bool(args.regen_task_tree) or (not task_tree.exists()):
        cmd = [sys.executable, "tools/scc/raw_to_task_tree.py", "--input-root", _to_repo_rel(input_root), "--output", _to_repo_rel(task_tree)]
        rc, out, err = _run(cmd, env=env, timeout_s=120)
        record("raw_to_task_tree", rc, cmd, out, err)

    # 2) Contractize pipeline (deterministic; mints OIDs in Postgres)
    cmd = [
        sys.executable,
        "tools/scc/ops/contractize_pipeline_run.py",
        "--taskcode",
        f"{taskcode}__CONTRACTIZE",
        "--area",
        area,
        "--task-tree",
        _to_repo_rel(task_tree),
        "--limit",
        str(int(args.contractize_limit or 0)),
        "--sample-run",
        "0",
    ]
    rc, out, err = _run(cmd, env=env, timeout_s=600)
    record("contractize_pipeline", rc, cmd, out, err)

    # 2b) Deterministic DLQ policy for legacy/unknown schema tasks (non-fabrication rule).
    # This is nonfatal: it only classifies/skips tasks that are missing required goal fields.
    cmd = [
        sys.executable,
        "tools/scc/ops/unknown_schema_351_migration.py",
        "--taskcode",
        f"{taskcode}__UNKNOWN_SCHEMA_351",
        "--area",
        area,
        "--emit-report",
    ]
    rc, out, err = _run(cmd, env=env, timeout_s=120)
    record_nonfatal("unknown_schema_351_migration", rc, cmd, out, err)

    scope_runs: List[Dict[str, Any]] = []
    scope_mode = str(args.scope_harden_mode or "deterministic").strip().lower()

    # 3a) Deterministic scope harden (no LLM) — reduces token burn and avoids patch corruption.
    if int(args.scope_harden_limit or 0) > 0 and scope_mode in ("deterministic", "both"):
        cmd = [
            sys.executable,
            "tools/scc/ops/contract_harden_job.py",
            "--taskcode",
            f"{taskcode}__SCOPE_HARDEN_DET",
            "--area",
            area,
            "--task-tree",
            _to_repo_rel(task_tree),
            "--limit",
            str(int(args.scope_harden_limit or 0)),
            "--emit-report",
        ]
        rc, out, err = _run(cmd, env=env, timeout_s=600)
        record("scope_harden_deterministic", rc, cmd, out, err)
        scope_runs.append({"mode": "deterministic", "rc": rc, "taskcode": f"{taskcode}__SCOPE_HARDEN_DET"})
    elif int(args.scope_harden_limit or 0) <= 0:
        record_nonfatal("scope_harden_skipped", 0, ["scope_harden_limit", str(int(args.scope_harden_limit or 0))])

    # 3b) Optional: LLM scope harden via Codex dispatch, retry<=N (expands scope/acceptance).
    if scope_mode in ("llm", "both") and int(args.scope_harden_limit or 0) > 0:
        for attempt in range(1, max(1, int(args.retries or 1)) + 1):
            cmd_gen = [
                sys.executable,
                "tools/scc/ops/dispatch_from_task_tree.py",
                "--taskcode",
                f"{taskcode}__SCOPE_DISPATCH_GEN_{attempt}",
                "--area",
                area,
                "--task-tree",
                _to_repo_rel(task_tree),
                "--limit",
                str(int(args.scope_harden_limit or 0)),
                "--include-hardened",
                "--model",
                model,
                "--timeout-s",
                str(int(args.timeout_s)),
                "--max-outstanding",
                str(int(args.max_outstanding)),
                "--emit-report",
                "--embed-extra",
                _to_repo_rel(goal_brief),
            ]
            rcg, outg, errg = _run(cmd_gen, env=env, timeout_s=120)
            gen_obj = _parse_json_from_mixed_stdout(outg) or {}
            gen_err = str(gen_obj.get("error") or "").strip()
            # If no contracts require additional LLM scope hardening, treat as a clean skip.
            if int(rcg) == 3 and gen_err in {"no_tasks_with_contract_ref_found"}:
                record_nonfatal(f"scope_dispatch_gen_{attempt}", rcg, cmd_gen, outg, errg)
                scope_runs.append({"mode": "llm", "attempt": attempt, "generated": False, "rc": 0, "skipped": True, "reason": gen_err})
                break
            record(f"scope_dispatch_gen_{attempt}", rcg, cmd_gen, outg, errg)
            if rcg != 0:
                scope_runs.append({"mode": "llm", "attempt": attempt, "generated": False, "rc": rcg})
                break
            cfg = str(gen_obj.get("out_config") or "").strip()
            if not cfg:
                scope_runs.append({"mode": "llm", "attempt": attempt, "generated": False, "rc": 3, "error": "missing_out_config"})
                break

            cmd_run = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str((REPO_ROOT / "tools" / "scc" / "ops" / "dispatch_with_watchdog.ps1").resolve()),
                "-Config",
                cfg,
                "-Model",
                model,
                "-TimeoutS",
                str(int(args.timeout_s)),
                "-MaxOutstanding",
                str(int(args.max_outstanding)),
                "-BaseUrl",
                base,
                "-PollS",
                str(int(args.poll_s)),
                "-StuckAfterS",
                str(int(args.stuck_after_s)),
                "-TokenCap",
                str(int(args.token_cap or 0)),
                "-LeaderBoardPollS",
                str(int(args.poll_s)),
                "-LeaderBoardLimitRuns",
                "10",
            ]
            rcr, outr, errr = _run(cmd_run, env=env, timeout_s=int(args.timeout_s) + 180)
            record(f"scope_dispatch_run_{attempt}", rcr, cmd_run, outr, errr)
            scope_runs.append({"mode": "llm", "attempt": attempt, "generated": True, "config": cfg, "rc": rcr, "out_dir": _parse_out_dir(outr)})
            if rcr == 0:
                break
    else:
        record_nonfatal("scope_harden_llm_skipped", 0, ["scope_harden_mode", scope_mode])

    # 4) Execute+verify dispatch (LLM), retry<=N
    exec_runs: List[Dict[str, Any]] = []
    if int(args.execute_limit or 0) <= 0:
        record_nonfatal("exec_dispatch_skipped", 0, ["execute_limit", str(int(args.execute_limit or 0))])
    else:
        for attempt in range(1, max(1, int(args.retries or 1)) + 1):
            cmd_gen = [
                sys.executable,
                "tools/scc/ops/dispatch_execute_from_task_tree.py",
                "--taskcode",
                f"{taskcode}__EXEC_DISPATCH_GEN_{attempt}",
                "--area",
                area,
                "--task-tree",
                _to_repo_rel(task_tree),
                "--limit",
                str(int(args.execute_limit or 0)),
                "--model",
                model,
                "--timeout-s",
                str(int(args.timeout_s)),
                "--max-outstanding",
                str(max(1, int(args.max_outstanding))),
                "--emit-report",
                "--embed-extra",
                _to_repo_rel(goal_brief),
            ]
            rcg, outg, errg = _run(cmd_gen, env=env, timeout_s=120)
            # Nonfatal: when no executable contracts exist yet, this stage can be skipped.
            parsed = _parse_json_from_mixed_stdout(outg)
            if rcg != 0 and isinstance(parsed, dict) and parsed.get("error") == "no_executable_contracts_found":
                record_nonfatal(f"exec_dispatch_gen_{attempt}", rcg, cmd_gen, outg, errg)
                exec_runs.append({"attempt": attempt, "generated": False, "rc": rcg, "skipped": True, "reason": "no_executable_contracts_found"})
                break
            record(f"exec_dispatch_gen_{attempt}", rcg, cmd_gen, outg, errg)
            if rcg != 0:
                exec_runs.append({"attempt": attempt, "generated": False, "rc": rcg})
                break
            gen_res = parsed or _parse_json_from_mixed_stdout(outg) or {}
            cfg = str(gen_res.get("out_config") or "").strip()
            picked = gen_res.get("picked") if isinstance(gen_res.get("picked"), list) else []
            if not cfg:
                exec_runs.append({"attempt": attempt, "generated": False, "rc": 3, "error": "missing_out_config"})
                break

            cmd_run = [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str((REPO_ROOT / "tools" / "scc" / "ops" / "dispatch_with_watchdog.ps1").resolve()),
                "-Config",
                cfg,
                "-Model",
                model,
                "-TimeoutS",
                str(int(args.timeout_s)),
                "-MaxOutstanding",
                str(int(args.max_outstanding)),
                "-BaseUrl",
                base,
                "-PollS",
                str(int(args.poll_s)),
                "-StuckAfterS",
                str(int(args.stuck_after_s)),
                "-TokenCap",
                str(int(args.token_cap or 0)),
                "-LeaderBoardPollS",
                str(int(args.poll_s)),
                "-LeaderBoardLimitRuns",
                "10",
            ]
            rcr, outr, errr = _run(cmd_run, env=env, timeout_s=int(args.timeout_s) + 180)
            # LLM execution dispatch is optional: deterministic contract runner below is the fail-closed baseline.
            if rcr != 0:
                record_nonfatal(f"exec_dispatch_run_{attempt}", rcr, cmd_run, outr, errr)
            else:
                record(f"exec_dispatch_run_{attempt}", rcr, cmd_run, outr, errr)
            exec_runs.append({"attempt": attempt, "generated": True, "config": cfg, "rc": rcr, "picked": picked, "out_dir": _parse_out_dir(outr)})
            if rcr == 0:
                break

    # 5) Local contract acceptance runs (deterministic; updates artifacts/scc_tasks)
    ran_contracts: List[Dict[str, Any]] = []
    if int(args.run_contracts or 0) <= 0:
        record_nonfatal("run_contracts_skipped", 0, ["run_contracts", str(int(args.run_contracts or 0))])
    else:
        for tid in _iter_task_ids(task_tree, limit=int(args.run_contracts or 0)):
            cmd = [sys.executable, "tools/scc/ops/run_contract_task.py", "--task-id", tid, "--area", area]
            rc, out, err = _run(cmd, env=env, timeout_s=600)
            record(f"run_contract_task:{tid}", rc, cmd, out, err)
            ran_contracts.append({"task_id": tid, "rc": rc})

    # 6) Review job (progress + feedback)
    cmd = [sys.executable, "tools/scc/ops/review_job_run.py", "--taskcode", f"{taskcode}__REVIEW", "--area", area]
    if bool(args.run_mvm):
        cmd.append("--run-mvm")
    rc, out, err = _run(cmd, env=env, timeout_s=240)
    record("review_job_run", rc, cmd, out, err)

    # 7) Backfill derived task_tree with verdicts (deterministic)
    cmd = [
        sys.executable,
        "tools/scc/ops/backfill_task_tree_from_scc_tasks.py",
        "--task-tree",
        _to_repo_rel(task_tree),
        "--tasks-root",
        "artifacts/scc_tasks",
        "--emit-report",
        "--taskcode",
        f"{taskcode}__TASKTREE_BACKFILL",
        "--area",
        area,
    ]
    rc, out, err = _run(cmd, env=env, timeout_s=240)
    record("task_tree_backfill", rc, cmd, out, err)

    # 8) DoD audit (deterministic)
    cmd = [sys.executable, "tools/scc/ops/closed_loop_dod_audit.py", "--taskcode", f"{taskcode}__DOD", "--area", area]
    # If OID DSN is present, DoD audit should actually run oid_validator (fail-closed).
    if str(env.get("SCC_OID_PG_DSN") or "").strip():
        cmd.append("--run-oid-validator")
    rc, out, err = _run(cmd, env=env, timeout_s=240)
    record("closed_loop_dod_audit", rc, cmd, out, err)

    summary = {
        "schema_version": "v0.1.0",
        "taskcode": taskcode,
        "area": area,
        "ts_utc": _iso_now(),
        "base": base,
        "model": model,
        "goal_brief": _to_repo_rel(goal_brief),
        "task_tree": _to_repo_rel(task_tree),
        "scope_runs": scope_runs,
        "execute_runs": exec_runs,
        "ran_contracts": ran_contracts,
        "steps": steps,
        "ok": rc_all == 0,
        "exit_code": int(rc_all),
    }
    _write_json(summary_path, summary)

    notes = "\n".join(
        [
            f"- factory_loop_once stitches: task_tree → contractize → scope_harden(mode={scope_mode}) → execute+verify (LLM) → local acceptance → review → backfill → DoD audit.",
            f"- base: `{base}`",
            f"- model: `{model}`",
            f"- watchdog: poll_s={int(args.poll_s)} stuck_after_s={int(args.stuck_after_s)}",
        ]
    )
    evidence = [
        f"docs/REPORT/{area}/artifacts/{taskcode}/factory_loop_summary.json",
        f"docs/REPORT/{area}/LEADER_BOARD__LATEST.md",
    ]
    _evidence_triplet(env=env, taskcode=taskcode, area=area, exit_code=int(rc_all), notes=notes, evidence=evidence)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if rc_all == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
