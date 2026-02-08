#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8", errors="replace")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _date_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _run_cmd(
    *, repo_root: Path, cmd: str, cwd: Optional[str], timeout_s: Optional[int], env: Optional[dict]
) -> Tuple[int, str, str]:
    # Avoid `shell=True` to prevent command injection. Contracts may come from outside this process.
    # If you really need a shell pipeline, wrap it explicitly as: ["powershell", "-NoProfile", "-Command", "..."].
    if not isinstance(cmd, str):
        raise TypeError("command must be a string")

    # Fail-closed on shell metacharacters; these are the common injection primitives on Windows+POSIX.
    # Note: allow colon/equals/slash/backslash for paths and flags.
    if re.search(r"[&|;<>`\r\n]", cmd) or (os.name == "nt" and re.search(r"[%^]", cmd)):
        raise SystemExit(f"refusing to run unsafe command string (contains shell metacharacters): {cmd!r}")

    argv = shlex.split(cmd, posix=(os.name != "nt"))
    if not argv:
        raise SystemExit("refusing to run empty command")

    p = subprocess.run(
        argv,
        shell=False,
        cwd=str((repo_root / cwd).resolve()) if cwd else str(repo_root),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s if timeout_s else None,
    )
    return int(p.returncode), (p.stdout or ""), (p.stderr or "")


def _artifacts_dir(repo_root: Path, area: str, task_code: str) -> Path:
    return (repo_root / "docs" / "REPORT" / area / "artifacts" / task_code).resolve()


def _report_path(repo_root: Path, area: str, task_code: str) -> Path:
    # Guard expects REPORT__<TaskCode>__YYYYMMDD.md
    return (repo_root / "docs" / "REPORT" / area / f"REPORT__{task_code}__{_date_utc()}.md").resolve()


def _build_report_lines(*, task_code: str, area: str, evidence_paths: List[str]) -> str:
    lines = [
        f"# REPORT__{task_code}",
        "",
        f"- TaskCode: {task_code}",
        f"- Area: {area}",
        f"- Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "",
        "## Evidence Paths",
    ]
    for p in evidence_paths:
        lines.append(f"- {p}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a v0.1.0 SCC contract acceptance and emit verdict artifacts")
    ap.add_argument("--contract", required=True, help="Path to contract JSON (v0.1.0)")
    ap.add_argument("--area", default="control_plane", help="docs/REPORT/<area>/...")
    ap.add_argument("--taskcode", default="", help="Override TaskCode (default contract.task_id)")
    ap.add_argument("--no-mvm", action="store_true", help="Do not run mvm-verdict (just emit artifacts)")
    args = ap.parse_args()

    repo_root = _repo_root()
    contract_path = Path(args.contract)
    if not contract_path.is_absolute():
        contract_path = (repo_root / contract_path).resolve()
    contract = _read_json(contract_path)

    task_id = str(contract.get("task_id") or "").strip()
    task_code = str(args.taskcode).strip() or task_id
    if not task_code:
        raise SystemExit("missing task_code (provide --taskcode or contract.task_id)")

    area = str(args.area).strip() or "control_plane"
    artifacts_dir = _artifacts_dir(repo_root, area, task_code)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    base_env = dict(os.environ)
    base_env["TASK_CODE"] = task_code
    base_env["AREA"] = area

    checks = contract.get("acceptance", {}).get("checks") if isinstance(contract.get("acceptance"), dict) else None
    if not isinstance(checks, list) or not checks:
        raise SystemExit("contract.acceptance.checks missing or empty")

    evidence_rel: List[str] = []
    check_results: List[Dict[str, Any]] = []

    verdict = "PASS"
    fail_class: Optional[str] = None
    exit_code = 0

    for idx, chk in enumerate(checks, start=1):
        if not isinstance(chk, dict):
            continue
        name = str(chk.get("name") or f"check_{idx}").strip() or f"check_{idx}"
        cmd = str(chk.get("command") or "").strip()
        if not cmd:
            verdict = "FAIL"
            fail_class = "artifact_missing"
            exit_code = 2
            check_results.append({"name": name, "ok": False, "reason": "missing_command"})
            break

        cwd = str(chk.get("cwd") or "").strip() or None
        timeout_s = chk.get("timeout_s")
        timeout_s = int(timeout_s) if isinstance(timeout_s, int) and timeout_s > 0 else None

        rc, out, err = _run_cmd(repo_root=repo_root, cmd=cmd, cwd=cwd, timeout_s=timeout_s, env=base_env)
        stdout_path = artifacts_dir / f"{name}__stdout.txt"
        stderr_path = artifacts_dir / f"{name}__stderr.txt"
        _write_text(stdout_path, out)
        _write_text(stderr_path, err)

        evidence_rel.extend([stdout_path.name, stderr_path.name])

        expected = chk.get("expects") if isinstance(chk.get("expects"), dict) else {}
        exp_rc = expected.get("exit_code")
        if isinstance(exp_rc, int):
            ok = (rc == exp_rc)
        else:
            ok = (rc == 0)

        check_results.append({"name": name, "command": cmd, "exit_code": rc, "ok": ok})
        if not ok:
            verdict = "FAIL"
            fail_class = "command_failed"
            exit_code = rc if rc is not None else 1
            break

    # selftest.log: last line must be EXIT_CODE=0 for guard to PASS
    selftest_path = artifacts_dir / "selftest.log"
    self_exit = 0 if verdict == "PASS" else 1
    _write_text(selftest_path, f"{task_code} contract_runner\nEXIT_CODE={self_exit}\n")
    evidence_rel.append(selftest_path.name)

    verdict_obj = {
        "verdict": verdict,
        "fail_class": fail_class,
        "exit_code": int(exit_code),
        "generated_utc": _iso_now(),
        "evidence_paths": sorted(set(evidence_rel)),
        "contract_path": str(contract_path.relative_to(repo_root)).replace("\\", "/"),
        "task_code": task_code,
        "area": area,
        "checks": check_results,
    }
    _write_json(artifacts_dir / "verdict.json", verdict_obj)

    # Report must only reference evidence files that exist BEFORE guard runs.
    report_evidence = [
        f"docs/REPORT/{area}/artifacts/{task_code}/verdict.json",
        f"docs/REPORT/{area}/artifacts/{task_code}/selftest.log",
    ]
    # include first 4 check logs to keep report compact
    for name in sorted(set(evidence_rel)):
        if name.endswith(".txt"):
            report_evidence.append(f"docs/REPORT/{area}/artifacts/{task_code}/{name}")
    _write_text(_report_path(repo_root, area, task_code), _build_report_lines(task_code=task_code, area=area, evidence_paths=report_evidence))

    if args.no_mvm:
        print(json.dumps({"ok": verdict == "PASS", "task_code": task_code, "artifacts_dir": str(artifacts_dir)}, ensure_ascii=False))
        return 0 if verdict == "PASS" else 1

    # Run mvm-verdict (fail-closed)
    env = dict(os.environ)
    env["TASK_CODE"] = task_code
    env["AREA"] = area
    p = subprocess.run(
        [sys.executable, "tools/ci/mvm-verdict.py", "--case", "basic"],
        cwd=str(repo_root),
        env=env,
        capture_output=True,
        text=True,
    )
    # Mirror output for operator
    print(p.stdout)
    if p.returncode != 0:
        print(p.stderr)
    return int(p.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
