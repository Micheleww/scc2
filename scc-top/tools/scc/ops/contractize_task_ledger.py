#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contractize Task Ledger (v0.1.0) — deterministic.

Goal:
- Convert legacy task ledger entries under artifacts/scc_tasks/*/task.json into v0.1.0
  contract tasks by generating per-task contract JSONs under SSOT and writing request.contract_ref.

Notes:
- Only tasks with schema "legacy_orchestrator_task" (request.task.goal present) are contractized.
- Unknown schema tasks are NOT contractized (no virtual goal/acceptance is fabricated).
- OIDs are minted via SCC OID Postgres registry (env SCC_OID_PG_DSN + PGPASSWORD).
- Evidence is written under docs/REPORT/<area>/... (spec docs must not embed artifacts).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _repo_root() -> Path:
    return _REPO_ROOT


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _date_utc() -> str:
    return time.strftime("%Y%m%d", time.gmtime())


def _stamp_utc() -> str:
    return time.strftime("%Y%m%d-%H%M%SZ", time.gmtime())


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def _repo_rel(p: Path) -> str:
    root = _repo_root().resolve()
    try:
        return str(p.resolve().relative_to(root)).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def _safe_filename(s: str, *, max_len: int = 120) -> str:
    x = (s or "").strip()
    if not x:
        return "task"
    x = x.replace(":", "_").replace("/", "_").replace("\\", "_")
    x = re.sub(r"[^A-Za-z0-9_.-]+", "_", x)
    x = re.sub(r"_+", "_", x).strip("_")
    if not x:
        x = "task"
    if len(x) > max_len:
        x = x[:max_len].rstrip("_")
    return x


def _classify(rec: dict) -> str:
    req = rec.get("request") if isinstance(rec.get("request"), dict) else {}
    if str(req.get("contract_ref") or "").strip():
        return "contract_task"
    task = req.get("task") if isinstance(req.get("task"), dict) else {}
    if str(task.get("goal") or "").strip():
        return "legacy_orchestrator_task"
    return "unknown_schema"


def _ps_encoded_command(script: str) -> str:
    """
    Return PowerShell invocation using -EncodedCommand (UTF-16LE base64), robust for pipelines/quotes.
    """
    b = (script or "").encode("utf-16le")
    enc = base64.b64encode(b).decode("ascii")
    return f"powershell -NoProfile -ExecutionPolicy Bypass -EncodedCommand {enc}"


_DANGEROUS_PATTERNS = [
    r"\brm\b",
    r"\bdel\b",
    r"\brmdir\b",
    r"\bRemove-Item\b",
    r"\bFormat-Volume\b",
    r"\bshutdown\b",
    r"\bRestart-Computer\b",
    r"\bStop-Process\b",
    r"\btaskkill\b",
    r"\bgit\s+reset\b",
    r"\bgit\s+clean\b",
    r"\bInvoke-WebRequest\b",
    r"\bcurl\b",
    r"\bwget\b",
    r"\bscp\b",
    r"\bsftp\b",
]


def _is_safe_command(cmd: str) -> bool:
    s = (cmd or "").strip()
    if not s:
        return False
    for pat in _DANGEROUS_PATTERNS:
        if re.search(pat, s, flags=re.IGNORECASE):
            return False
    return True


def _acceptance_checks_from_commands(commands: List[str]) -> Tuple[List[dict], List[str]]:
    """
    Build acceptance.checks from legacy commands_hint (PowerShell).
    Returns (checks, blocked_reasons).
    """
    blocked: List[str] = []
    checks: List[dict] = []
    if not [c for c in commands if str(c or "").strip()]:
        return [], ["no_commands_hint"]
    for i, raw in enumerate(commands, start=1):
        cmd = str(raw or "").strip()
        if not cmd:
            continue
        if not _is_safe_command(cmd):
            blocked.append(f"unsafe_command[{i}]: {cmd[:200]}")
            continue

        is_rg = cmd.lower().lstrip().startswith("rg ")
        timeout_s = 60
        if re.search(r"\b-Recurse\b", cmd, flags=re.IGNORECASE) or re.search(r"\b--hidden\b", cmd):
            timeout_s = 120
        ps = "\n".join(
            [
                "$ErrorActionPreference = 'Continue'",
                cmd,
                "$ec = $LASTEXITCODE",
                "if ($null -eq $ec) { $ec = 0 }",
                "if ($ec -lt 0) { $ec = 0 }",
                "if ($ec -eq 1) {",
                ("  exit 0" if is_rg else "  exit 1"),
                "}",
                "exit [int]$ec",
            ]
        )
        checks.append(
            {
                "name": f"legacy_cmd_{i:03d}",
                "command": _ps_encoded_command(ps),
                "timeout_s": int(timeout_s),
            }
        )
    return checks, blocked


def _issue_oid_for_path(*, rel_path: str, kind: str, layer: str, primary_unit: str, tags: List[str], hint: str) -> str:
    from tools.scc.oid.pg_registry import get_oid_pg_dsn, issue_new

    dsn = get_oid_pg_dsn()
    oid, _issued = issue_new(
        dsn=dsn,
        path=rel_path,
        kind=kind,
        layer=layer,
        primary_unit=primary_unit,
        tags=tags,
        stable_key=f"path:{rel_path}",
        hint=hint,
    )
    return oid


def main() -> int:
    ap = argparse.ArgumentParser(description="Contractize legacy task ledger entries into SSOT contracts (v0.1.0).")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="CONTRACTIZE_LEDGER_V010")
    ap.add_argument("--tasks-root", default="artifacts/scc_tasks")
    ap.add_argument("--out-dir", default="docs/ssot/04_contracts/generated/ledger")
    ap.add_argument("--limit-latest", type=int, default=800)
    ap.add_argument(
        "--include-contractized",
        action="store_true",
        help="Also re-generate contracts for tasks already contractized under generated/ledger (keeps same oid via stable_key).",
    )
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--run-validators", action="store_true", help="Run top_validator and oid_validator and include outputs in evidence.")
    args = ap.parse_args()

    repo_root = _repo_root()
    area = str(args.area).strip() or "control_plane"
    taskcode = str(args.taskcode).strip() or "CONTRACTIZE_LEDGER_V010"
    env = dict(os.environ)
    env["TASK_CODE"] = taskcode
    env["AREA"] = area

    tasks_root = Path(args.tasks_root)
    if not tasks_root.is_absolute():
        tasks_root = (repo_root / tasks_root).resolve()
    if not tasks_root.exists():
        print(json.dumps({"ok": False, "error": "missing_tasks_root", "tasks_root": str(tasks_root)}, ensure_ascii=False))
        return 2

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (repo_root / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report_dir = (repo_root / "docs" / "REPORT" / area).resolve()
    artifacts_dir = (report_dir / "artifacts" / f"{taskcode}__{_stamp_utc()}").resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # latest by task.json mtime
    scored: List[Tuple[float, Path]] = []
    for d in tasks_root.iterdir():
        if not d.is_dir():
            continue
        tj = d / "task.json"
        if not tj.exists():
            continue
        try:
            scored.append((float(tj.stat().st_mtime), d))
        except Exception:
            scored.append((0.0, d))
    scored.sort(key=lambda t: t[0], reverse=True)
    dirs = [d for _, d in scored[: max(1, int(args.limit_latest or 800))]]

    generated: List[dict] = []
    skipped: List[dict] = []
    blocked: List[dict] = []
    errors: List[dict] = []
    manifest_task_ids: List[str] = []
    hint = f"contractize_task_ledger:{taskcode}"

    for d in dirs:
        tj = d / "task.json"
        rec = _read_json(tj)
        task_id = str(rec.get("task_id") or d.name).strip()
        cls = _classify(rec)
        eligible = (cls == "legacy_orchestrator_task")
        if (not eligible) and bool(args.include_contractized) and (cls == "contract_task"):
            req0 = rec.get("request") if isinstance(rec.get("request"), dict) else {}
            cref0 = str(req0.get("contract_ref") or "").strip().replace("\\", "/")
            if cref0.startswith("docs/ssot/04_contracts/generated/ledger/"):
                eligible = True
        if not eligible:
            skipped.append({"task_id": task_id, "class": cls, "task_dir": _repo_rel(d)})
            continue

        req = rec.get("request") if isinstance(rec.get("request"), dict) else {}
        task = req.get("task") if isinstance(req.get("task"), dict) else {}
        goal = str(task.get("goal") or "").strip()
        commands_hint = task.get("commands_hint")
        if isinstance(commands_hint, str):
            commands = [commands_hint]
        elif isinstance(commands_hint, list):
            commands = [str(x) for x in commands_hint if str(x).strip()]
        else:
            commands = []

        fname = _safe_filename(task_id) + ".json"
        contract_path = (out_dir / fname).resolve()
        rel_contract_path = _repo_rel(contract_path)

        checks, blocked_reasons = _acceptance_checks_from_commands(commands)
        if blocked_reasons:
            blocked.append({"task_id": task_id, "blocked_reasons": blocked_reasons, "task_dir": _repo_rel(d)})

        # Always create a contract. If no commands_hint exist, we allow a no-op migration acceptance (exit 0).
        # If commands exist but are unsafe, we fail-closed (exit 2).
        if not checks:
            if blocked_reasons == ["no_commands_hint"]:
                checks = [
                    {
                        "name": "migration_noop",
                        "command": "python -c \"print('ok: migrated legacy task into contract system (no commands_hint)')\"",
                        "timeout_s": 15,
                    }
                ]
            else:
                checks = [
                    {
                        "name": "acceptance_blocked",
                        "command": "python -c \"import sys; print('Blocked: legacy commands_hint unsafe; harden contract before execution'); sys.exit(2)\"",
                        "timeout_s": 30,
                    }
                ]

        try:
            oid = _issue_oid_for_path(
                rel_path=rel_contract_path,
                kind="json",
                layer="CANON",
                primary_unit="K.CONTRACT_DOC",
                tags=["K.ACCEPTANCE", "V.VERDICT"],
                hint=hint,
            )

            contract = {
                "oid": oid,
                "layer": "CANON",
                "primary_unit": "K.CONTRACT_DOC",
                "tags": ["K.ACCEPTANCE", "V.VERDICT"],
                "status": "active",
                "schema_version": "v0.1.0",
                "task_id": task_id,
                "contract_id": f"ledger_migrate:{task_id}",
                "goal": goal or f"Task {task_id}",
                "scope_allow": "Read-only workspace scan + report (v0.1.0 ledger migration default).",
                "constraints": "Fail-closed. Do not create a second docs entrypoint. No network. No destructive commands.",
                "acceptance": {"checks": checks},
                "stop_condition": "If acceptance cannot be executed safely within scope_allow, stop and report.",
                "commands_hint": "Use deterministic search (rg) and SSOT registry; avoid wide scans.",
                "inputs_ref": {
                    "paths": [],
                    "oids": [],
                },
                "outputs_expected": {"verdict_required": True},
                "migration": {
                    "source_schema": "legacy_orchestrator_task",
                    "source_task_dir": _repo_rel(d),
                    "blocked_reasons": blocked_reasons,
                },
            }

            if not args.dry_run:
                _write_json(contract_path, contract)

                # Write back contract_ref (additive).
                req.setdefault("source", "task_ledger")
                req["contract_ref"] = rel_contract_path
                rec["request"] = req
                rec["updated_utc"] = _iso_now()
                _write_json(tj, rec)

            manifest_task_ids.append(task_id)
            generated.append(
                {
                    "task_id": task_id,
                    "contract_path": rel_contract_path,
                    "oid": oid,
                    "blocked": bool(blocked_reasons),
                    "task_dir": _repo_rel(d),
                }
            )
        except Exception as e:
            errors.append({"task_id": task_id, "error": str(e), "task_dir": _repo_rel(d)})

    summary = {
        "ok": (not errors),
        "schema_version": "v0.1.0",
        "generated_at_utc": _iso_now(),
        "area": area,
        "taskcode": taskcode,
        "tasks_root": _repo_rel(tasks_root),
        "limit_latest": int(args.limit_latest),
        "out_dir": _repo_rel(out_dir),
        "generated_count": len(generated),
        "blocked_count": len(blocked),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "generated_sample": generated[:50],
        "blocked_sample": blocked[:50],
        "errors": errors[:50],
    }
    _write_json(artifacts_dir / "contractize_task_ledger_summary.json", summary)
    _write_text(artifacts_dir / "manifest_task_ids.txt", "\n".join(manifest_task_ids).strip() + ("\n" if manifest_task_ids else ""))

    top_rc = 0
    oid_rc = 0
    if args.run_validators:
        try:
            p = subprocess.run(
                [sys.executable, "tools/scc/ops/top_validator.py", "--registry", "docs/ssot/registry.json", "--out-dir", _repo_rel(artifacts_dir)],
                cwd=str(repo_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=180,
            )
            top_rc = int(p.returncode or 0)
            _write_text(artifacts_dir / "top_validator_stdout.txt", p.stdout or "")
            _write_text(artifacts_dir / "top_validator_stderr.txt", p.stderr or "")
        except Exception as e:
            top_rc = 2
            _write_text(artifacts_dir / "top_validator_stderr.txt", f"{e}\n")

        try:
            p = subprocess.run(
                [sys.executable, "tools/scc/ops/oid_validator.py", "--report-dir", _repo_rel(artifacts_dir)],
                cwd=str(repo_root),
                env=env,
                capture_output=True,
                text=True,
                timeout=240,
            )
            oid_rc = int(p.returncode or 0)
            _write_text(artifacts_dir / "oid_validator_stdout.txt", p.stdout or "")
            _write_text(artifacts_dir / "oid_validator_stderr.txt", p.stderr or "")
        except Exception as e:
            oid_rc = 2
            _write_text(artifacts_dir / "oid_validator_stderr.txt", f"{e}\n")

    ok = (not errors) and (top_rc == 0) and (oid_rc == 0)

    report_md = (report_dir / f"REPORT__{taskcode}__{_date_utc()}.md").resolve()
    lines: List[str] = []
    lines.append(f"# Contractize Task Ledger — {taskcode} (v0.1.0)")
    lines.append("")
    lines.append(f"- generated_at_utc: `{summary['generated_at_utc']}`")
    lines.append(f"- tasks_root: `{summary['tasks_root']}`")
    lines.append(f"- out_dir: `{summary['out_dir']}`")
    lines.append(f"- counts: `{{\"generated\":{summary['generated_count']},\"blocked\":{summary['blocked_count']},\"skipped\":{summary['skipped_count']},\"errors\":{summary['error_count']}}}`")
    lines.append("")
    lines.append("## Evidence")
    lines.append(f"- summary: `{_repo_rel(artifacts_dir / 'contractize_task_ledger_summary.json')}`")
    lines.append(f"- manifest: `{_repo_rel(artifacts_dir / 'manifest_task_ids.txt')}`")
    if args.run_validators:
        lines.append(f"- top_validator_stdout: `{_repo_rel(artifacts_dir / 'top_validator_stdout.txt')}`")
        lines.append(f"- oid_validator_stdout: `{_repo_rel(artifacts_dir / 'oid_validator_stdout.txt')}`")
    lines.append("")
    lines.append("## Notes")
    lines.append("- Only `legacy_orchestrator_task` are contractized. `unknown_schema` are skipped (no fabricated goal/acceptance).")
    lines.append("- Blocked contracts are fail-closed and require hardening before execution.")
    lines.append("")
    report_md.write_text("\n".join(lines).strip() + "\n", encoding="utf-8", errors="replace")

    # Fail-closed report triplet for skill_call_guard / mvm-verdict basic.
    evidence = [
        _repo_rel(artifacts_dir / "contractize_task_ledger_summary.json"),
        _repo_rel(artifacts_dir / "manifest_task_ids.txt"),
    ]
    if args.run_validators:
        evidence.extend([_repo_rel(artifacts_dir / "top_validator_stdout.txt"), _repo_rel(artifacts_dir / "oid_validator_stdout.txt")])
    subprocess.run(
        [
            sys.executable,
            "tools/scc/ops/evidence_triplet.py",
            "--taskcode",
            taskcode,
            "--area",
            area,
            "--exit-code",
            "0" if ok else "1",
            "--notes",
            "\n".join(
                [
                    f"- out_dir: `{summary['out_dir']}`",
                    f"- generated: {summary['generated_count']}",
                    f"- blocked: {summary['blocked_count']}",
                    f"- skipped: {summary['skipped_count']}",
                    f"- errors: {summary['error_count']}",
                ]
            ),
            *sum([["--evidence", p] for p in evidence], []),
        ],
        cwd=str(repo_root),
        env=env,
    )

    print(str(report_md))
    print(str(artifacts_dir))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
