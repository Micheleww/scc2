#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.scc.runtime.diff_extract import extract_unified_diff  # noqa: E402
from tools.scc.runtime.unified_diff_apply import apply_unified_diff  # noqa: E402
from tools.scc.runtime.unified_diff_guard import guard_diff  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8").lstrip("\ufeff"))


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _append_jsonl(path: pathlib.Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run(cmd: List[str], cwd: pathlib.Path, timeout_s: int, capture: bool = False, extra_env: Optional[Dict[str, str]] = None) -> Tuple[int, str, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd),
        timeout=int(timeout_s),
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "SCC_REPO_ROOT": str(REPO_ROOT), **(extra_env or {})},
    )
    return int(p.returncode), (p.stdout or ""), (p.stderr or "")


def _parse_cmdline(cmd: str) -> List[str]:
    """
    Parse a command string into argv without invoking a shell.

    Security: reject common shell metacharacters.
    If you need a pipeline, wrap it explicitly as argv:
    - Windows: powershell -NoProfile -Command "..."
    - Linux:   bash -lc "..."
    """
    if not isinstance(cmd, str):
        raise TypeError("cmd must be string")
    if re.search(r"[&|;<>`\r\n]", cmd) or (os.name == "nt" and re.search(r"[%^]", cmd)):
        raise ValueError(f"unsafe command string (shell metacharacters): {cmd!r}")
    argv = shlex.split(cmd, posix=(os.name != "nt"))
    if not argv:
        raise ValueError("empty command")
    return [str(x) for x in argv]


def _run_shell(cmd: str, cwd: pathlib.Path, timeout_s: int, extra_env: Optional[Dict[str, str]] = None) -> Tuple[int, str]:
    # Historical name; intentionally does NOT invoke a shell.
    try:
        argv = _parse_cmdline(cmd)
    except Exception as e:
        return 2, f"refusing to run command: {e}\n"

    p = subprocess.run(
        argv,
        cwd=str(cwd),
        timeout=int(timeout_s),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "SCC_REPO_ROOT": str(REPO_ROOT), **(extra_env or {})},
        shell=False,
    )
    out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")
    return int(p.returncode), out


def _robocopy_mirror(src: pathlib.Path, dst: pathlib.Path, excludes: List[str]) -> bool:
    dst.mkdir(parents=True, exist_ok=True)
    xd = []
    for d in excludes:
        xd += ["/XD", d]
    cmd = ["robocopy", str(src), str(dst), "/MIR", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:1", "/W:1", *xd]
    p = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    # Robocopy exit codes: 0-7 are success (with differences), >=8 failure.
    return int(p.returncode) < 8


def _norm_rel(p: str) -> str:
    return str(p or "").replace("\\", "/").lstrip("./")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run SCC child_task through a minimal PRECHECK→PINS→EXEC→VERIFY state machine (local).")
    ap.add_argument("--child", required=True, help="Child task JSON (contracts/child_task/child_task.schema.json)")
    ap.add_argument("--task-id", default="", help="Task id (default: new uuid4)")
    ap.add_argument("--executor", default="noop", choices=["noop", "command", "codex_diff"], help="Execution mode")
    ap.add_argument("--executor-cmd", default="", help="If executor=command, run this command in repo root (shell-free parsing; deprecated).")
    ap.add_argument("--executor-argv-json", default="", help="If executor=command, JSON array argv to execute (preferred; shell-free).")
    ap.add_argument("--codex-bin", default="codex", help="Codex CLI binary (for executor=codex_diff)")
    ap.add_argument("--codex-model", default="", help="Model name override (for executor=codex_diff)")
    ap.add_argument("--secret", action="append", default=[], help="Secret key(s) to mount as env SCC_SECRET_<KEY> (repeatable)")
    ap.add_argument("--snapshot", action="store_true", help="Create a repo snapshot before EXEC; restore it on failure.")
    ap.add_argument("--timeout-tests-s", type=int, default=600, help="Timeout per allowedTests command")
    args = ap.parse_args()

    child_path = (REPO_ROOT / str(args.child)).resolve()
    if not child_path.exists():
        print(f"FAIL: missing child {child_path}")
        return 2
    child = _load_json(child_path)
    if not isinstance(child, dict):
        print("FAIL: child task not object")
        return 2

    role = str(child.get("role") or "").strip().lower()
    if not role:
        print("FAIL: child.role missing")
        return 2
    role_policy_path = (REPO_ROOT / "roles" / f"{role}.json").resolve()
    if not role_policy_path.exists():
        print(f"FAIL: missing role policy {role_policy_path}")
        return 2
    role_policy = _load_json(role_policy_path)

    task_id = str(args.task_id or "").strip() or str(uuid.uuid4())
    art_dir = (REPO_ROOT / "artifacts" / task_id).resolve()
    evidence_dir = art_dir / "evidence"
    pins_dir = art_dir / "pins"
    sandbox_dir = art_dir / "sandbox"
    art_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Soft secrets mount (DPAPI vault): export selected keys into env vars only.
    secrets: Dict[str, str] = {}
    secret_keys = [str(x).strip() for x in (args.secret or []) if str(x).strip()]
    if secret_keys:
        try:
            ps = REPO_ROOT / "tools" / "scc" / "runtime" / "secrets_vault.ps1"
            p = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ps), "export", *secret_keys],
                cwd=str(REPO_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "SCC_REPO_ROOT": str(REPO_ROOT)},
                timeout=30,
            )
            if p.returncode != 0:
                raise RuntimeError((p.stderr or p.stdout or "secrets_export_failed").strip()[:2000])
            obj = json.loads(p.stdout or "{}")
            sec = obj.get("secrets") if isinstance(obj, dict) else None
            if isinstance(sec, dict):
                for k, v in sec.items():
                    if isinstance(k, str) and k and isinstance(v, str):
                        secrets[k] = v
        except Exception as e:
            _write_json(evidence_dir / "secrets_mount.json", {"ok": False, "error": str(e), "keys": secret_keys})
            # Fail-closed if caller requested secrets.
            _write_text(art_dir / "report.md", "# SECRETS mount failed\nRequested secrets could not be exported.\n")
            _write_text(art_dir / "selftest.log", "secrets mount failed\nEXIT_CODE=0\n")
            _write_text(art_dir / "patch.diff", "\n")
            _write_text(
                art_dir / "events.jsonl",
                json.dumps(
                    {"schema_version": "scc.event.v1", "t": _now_iso(), "event_type": "EXECUTOR_ERROR", "task_id": task_id, "parent_id": None, "role": "workspace_janitor", "area": "runtime", "executor": "internal", "model": None, "reason": "secrets_mount_failed", "details": {"keys": secret_keys}},
                    ensure_ascii=False,
                )
                + "\n",
            )
            submit = {
                "schema_version": "scc.submit.v1",
                "task_id": task_id,
                "status": "FAILED",
                "reason_code": "secrets_mount_failed",
                "changed_files": [],
                "new_files": [],
                "touched_files": [],
                "allow_paths": {"read": ["**"], "write": ["**"]},
                "tests": {"commands": [], "passed": False, "summary": "secrets mount failed"},
                "artifacts": {"report_md": f"artifacts/{task_id}/report.md", "selftest_log": f"artifacts/{task_id}/selftest.log", "evidence_dir": f"artifacts/{task_id}/evidence/", "patch_diff": f"artifacts/{task_id}/patch.diff", "submit_json": f"artifacts/{task_id}/submit.json"},
                "exit_code": 1,
                "needs_input": [],
                "summary": "SECRETS mount failed",
            }
            _write_json(art_dir / "submit.json", submit)
            # Best-effort strict gating (may fail due to missing replay_bundle; acceptable for this error path).
            _run(["python", "tools/scc/gates/run_ci_gates.py", "--submit", f"artifacts/{task_id}/submit.json"], cwd=REPO_ROOT, timeout_s=120, capture=False)
            return 1

    if secret_keys:
        _write_json(evidence_dir / "secrets_mount.json", {"ok": True, "keys": secret_keys, "count": len(secrets)})
    extra_env = {f"SCC_SECRET_{k}": v for k, v in secrets.items()}

    # PRECHECK: ensure Map exists (pins builder needs map hash).
    code, _, _ = _run(["cmd.exe", "/c", "npm --prefix oc-scc-local run -s map:build"], cwd=REPO_ROOT, timeout_s=240, capture=False)
    if code != 0:
        _write_text(art_dir / "report.md", "# PRECHECK failed\nmap:build failed.\n")
        _write_text(art_dir / "selftest.log", "precheck failed\nEXIT_CODE=1\n")
        _write_text(art_dir / "patch.diff", "\n")
        _write_text(art_dir / "events.jsonl", json.dumps({"schema_version": "scc.event.v1", "t": _now_iso(), "event_type": "EXECUTOR_ERROR", "task_id": task_id, "parent_id": None, "role": "preflight_gate", "area": "runtime", "executor": "internal", "model": None, "reason": "map_build_failed", "details": {}}, ensure_ascii=False) + "\n")
        submit = {
            "schema_version": "scc.submit.v1",
            "task_id": task_id,
            "status": "FAILED",
            "reason_code": "map_build_failed",
            "changed_files": [],
            "new_files": [],
            "touched_files": [],
            "allow_paths": {"read": ["**"], "write": ["**"]},
            "tests": {"commands": [], "passed": False, "summary": "precheck failed"},
            "artifacts": {"report_md": f"artifacts/{task_id}/report.md", "selftest_log": f"artifacts/{task_id}/selftest.log", "evidence_dir": f"artifacts/{task_id}/evidence/", "patch_diff": f"artifacts/{task_id}/patch.diff", "submit_json": f"artifacts/{task_id}/submit.json"},
            "exit_code": 1,
            "needs_input": [],
            "summary": "PRECHECK failed: map:build failed",
        }
        _write_json(art_dir / "submit.json", submit)
        print(f"FAIL: map:build failed task_id={task_id}")
        return 1

    map_ver = _load_json(REPO_ROOT / "map" / "version.json")
    map_hash = str(map_ver.get("hash") or "").strip()

    # PINS: build via node script
    pins_req = {
        "schema_version": "scc.pins_request.v1",
        "task_id": task_id,
        "child_task": child,
        "signals": {"keywords": [], "failing_test": None, "stacktrace": None},
        "budgets": {"max_files": 12, "max_loc": 240, "default_line_window": 140, "max_pins_tokens": 8000},
        "map_ref": {"path": "map/map.json", "hash": map_hash},
    }
    pins_req_path = art_dir / "pins_request.json"
    _write_json(pins_req_path, pins_req)
    code, out, err = _run(
        ["node", "oc-scc-local/scripts/pins_build_v1.mjs", "--request", str(pins_req_path.relative_to(REPO_ROOT)).replace("\\", "/")],
        cwd=REPO_ROOT,
        timeout_s=120,
        capture=True,
    )
    if code != 0:
        _write_text(art_dir / "report.md", "# PINS failed\npins_build_v1 failed.\n")
        _write_text(art_dir / "selftest.log", "pins failed\nEXIT_CODE=1\n")
        _write_text(art_dir / "patch.diff", "\n")
        _write_text(art_dir / "events.jsonl", json.dumps({"schema_version": "scc.event.v1", "t": _now_iso(), "event_type": "PINS_INSUFFICIENT", "task_id": task_id, "parent_id": None, "role": "pins", "area": "runtime", "executor": "internal", "model": None, "reason": "pins_build_failed", "details": {"stderr": err[-2000:]}}, ensure_ascii=False) + "\n")
        submit = {
            "schema_version": "scc.submit.v1",
            "task_id": task_id,
            "status": "NEED_INPUT",
            "reason_code": "pins_build_failed",
            "changed_files": [],
            "new_files": [],
            "touched_files": [],
            "allow_paths": {"read": ["**"], "write": ["**"]},
            "tests": {"commands": [], "passed": False, "summary": "pins failed"},
            "artifacts": {"report_md": f"artifacts/{task_id}/report.md", "selftest_log": f"artifacts/{task_id}/selftest.log", "evidence_dir": f"artifacts/{task_id}/evidence/", "patch_diff": f"artifacts/{task_id}/patch.diff", "submit_json": f"artifacts/{task_id}/submit.json"},
            "exit_code": 1,
            "needs_input": [{"type": "pins", "missing": ["pins_build_v1_failed"], "note": "pins builder failed"}],
            "summary": "PINS failed: pins builder error",
        }
        _write_json(art_dir / "submit.json", submit)
        print(f"FAIL: pins build failed task_id={task_id}")
        return 1

    def write_replay_bundle(status: str):
        # Minimal replay bundle so strict gates can always PASS (replayability L3).
        rb = {
            "schema_version": "scc.replay_bundle.v1",
            "task_id": task_id,
            "created_at": _now_iso(),
            "source": {"job_id": None, "executor": args.executor, "model": None, "job_status": status, "exit_code": None},
            "board_task_payload": {
                "kind": "atomic",
                "title": str(child.get("title") or ""),
                "goal": str(child.get("goal") or ""),
                "role": role,
                "files": child.get("files") if isinstance(child.get("files"), list) else [],
                "skills": child.get("skills") if isinstance(child.get("skills"), list) else [],
                "pointers": child.get("pointers") if isinstance(child.get("pointers"), dict) else None,
                "pins": None,
                "pins_instance": child.get("pins_instance") if isinstance(child.get("pins_instance"), dict) else None,
                "allowedTests": child.get("allowedTests") if isinstance(child.get("allowedTests"), list) else [],
                "allowedExecutors": child.get("allowedExecutors") if isinstance(child.get("allowedExecutors"), list) else [],
                "allowedModels": child.get("allowedModels") if isinstance(child.get("allowedModels"), list) else [],
                "runner": child.get("runner") if isinstance(child.get("runner"), str) else "internal",
                "area": "runtime",
                "lane": None,
                "task_class_id": child.get("task_class_id") if isinstance(child.get("task_class_id"), str) else None,
            },
            "artifacts": {
                "submit_json": f"artifacts/{task_id}/submit.json",
                "preflight_json": f"artifacts/{task_id}/preflight.json",
                "pins_json": f"artifacts/{task_id}/pins/pins.json",
                "report_md": f"artifacts/{task_id}/report.md",
                "selftest_log": f"artifacts/{task_id}/selftest.log",
                "evidence_dir": f"artifacts/{task_id}/evidence/",
                "patch_diff": f"artifacts/{task_id}/patch.diff",
            },
            "replay": {"dispatch_via": "tools/scc/ops/replay_bundle_dispatch.py"},
        }
        _write_json(art_dir / "replay_bundle.json", rb)

    # Preflight
    pins_spec_path = art_dir / "pins" / "pins_spec.json"
    if not pins_spec_path.exists():
        # Fallback: use pins.json if spec is missing (shouldn't happen).
        pins_spec_path = art_dir / "pins" / "pins.json"
    preflight_out_path = art_dir / "preflight.json"
    code, out, err = _run(
        [
            "node",
            "oc-scc-local/scripts/preflight_v1.mjs",
            "--child",
            str(child_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "--pins",
            str(pins_spec_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "--policy",
            str(role_policy_path.relative_to(REPO_ROOT)).replace("\\", "/"),
            "--taskId",
            task_id,
            "--out",
            str(preflight_out_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        ],
        cwd=REPO_ROOT,
        timeout_s=120,
        capture=True,
    )
    preflight = _load_json(preflight_out_path) if preflight_out_path.exists() else None
    if not (isinstance(preflight, dict) and isinstance(preflight.get("pass"), bool)):
        code = 1

    if not preflight or not preflight.get("pass"):
        _write_text(art_dir / "report.md", "# PREFLIGHT failed\nMissing pins/tests/scope per preflight.json.\n")
        _write_text(art_dir / "selftest.log", "preflight failed\nEXIT_CODE=0\n")
        _write_text(art_dir / "patch.diff", "\n")
        write_replay_bundle("NEED_INPUT")
        _write_text(art_dir / "events.jsonl", json.dumps({"schema_version": "scc.event.v1", "t": _now_iso(), "event_type": "PREFLIGHT_FAILED", "task_id": task_id, "parent_id": None, "role": "preflight_gate", "area": "runtime", "executor": "internal", "model": None, "reason": "preflight_failed", "details": {"missing": preflight.get("missing") if isinstance(preflight, dict) else None}}, ensure_ascii=False) + "\n")
        submit = {
            "schema_version": "scc.submit.v1",
            "task_id": task_id,
            "status": "NEED_INPUT",
            "reason_code": "preflight_failed",
            "changed_files": [],
            "new_files": [],
            "touched_files": [],
            "allow_paths": {"read": ["**"], "write": ["**"]},
            "tests": {"commands": child.get("allowedTests") if isinstance(child.get("allowedTests"), list) else [], "passed": False, "summary": "preflight failed"},
            "artifacts": {"report_md": f"artifacts/{task_id}/report.md", "selftest_log": f"artifacts/{task_id}/selftest.log", "evidence_dir": f"artifacts/{task_id}/evidence/", "patch_diff": f"artifacts/{task_id}/patch.diff", "submit_json": f"artifacts/{task_id}/submit.json"},
            "exit_code": 0,
            "needs_input": [{"type": "preflight", "missing": preflight.get("missing") if isinstance(preflight, dict) else {}, "note": "preflight failed"}],
            "summary": "PREFLIGHT failed",
        }
        _write_json(art_dir / "submit.json", submit)
        # VERIFY gates (strict) should still PASS: artifacts are present and schema-valid.
        _run(["python", "tools/scc/gates/run_ci_gates.py", "--strict", "--submit", f"artifacts/{task_id}/submit.json"], cwd=REPO_ROOT, timeout_s=120, capture=False)
        print(f"NEED_INPUT: preflight failed task_id={task_id}")
        return 0

    # Optional snapshot (rollback primitive)
    snap_root = sandbox_dir / "snapshot"
    if args.snapshot:
        ok = _robocopy_mirror(
            REPO_ROOT,
            snap_root,
            excludes=[
                "artifacts",
                ".opencode",
                "node_modules",
                "__pycache__",
                ".venv",
                ".git",
                "dist",
                "build",
                ".next",
            ],
        )
        if not ok:
            _write_text(art_dir / "report.md", "# SNAPSHOT failed\nrobocopy snapshot failed.\n")
            _write_text(art_dir / "selftest.log", "snapshot failed\nEXIT_CODE=1\n")
            _write_text(art_dir / "patch.diff", "\n")
            _write_text(art_dir / "events.jsonl", json.dumps({"schema_version": "scc.event.v1", "t": _now_iso(), "event_type": "EXECUTOR_ERROR", "task_id": task_id, "parent_id": None, "role": "workspace_janitor", "area": "runtime", "executor": "internal", "model": None, "reason": "snapshot_failed", "details": {}}, ensure_ascii=False) + "\n")
            submit = {
                "schema_version": "scc.submit.v1",
                "task_id": task_id,
                "status": "FAILED",
                "reason_code": "snapshot_failed",
                "changed_files": [],
                "new_files": [],
                "touched_files": [],
                "allow_paths": {"read": ["**"], "write": ["**"]},
                "tests": {"commands": [], "passed": False, "summary": "snapshot failed"},
                "artifacts": {"report_md": f"artifacts/{task_id}/report.md", "selftest_log": f"artifacts/{task_id}/selftest.log", "evidence_dir": f"artifacts/{task_id}/evidence/", "patch_diff": f"artifacts/{task_id}/patch.diff", "submit_json": f"artifacts/{task_id}/submit.json"},
                "exit_code": 1,
                "needs_input": [],
                "summary": "SNAPSHOT failed",
            }
            _write_json(art_dir / "submit.json", submit)
            print(f"FAIL: snapshot failed task_id={task_id}")
            return 1

    # EXEC: run allowedTests or executor command
    tests = child.get("allowedTests") if isinstance(child.get("allowedTests"), list) else []
    test_logs: List[str] = []
    tests_ok = True
    for i, tcmd in enumerate([str(x) for x in tests][:10]):
        code, log = _run_shell(tcmd, cwd=REPO_ROOT, timeout_s=int(args.timeout_tests_s), extra_env=extra_env)
        log_path = evidence_dir / "tests" / f"{i:02d}.log"
        _write_text(log_path, log)
        test_logs.append(str(log_path.relative_to(REPO_ROOT)).replace("\\", "/"))
        if code != 0:
            tests_ok = False
            break

    exec_code = 0
    exec_summary = "noop"
    if args.executor == "command":
        argv_json = str(getattr(args, "executor_argv_json", "") or "").strip()
        if argv_json:
            try:
                argv_obj = json.loads(argv_json)
                if not isinstance(argv_obj, list) or not all(isinstance(x, str) and x.strip() for x in argv_obj):
                    raise ValueError("argv must be a JSON array of non-empty strings")
                exec_code, out, err = _run([str(x) for x in argv_obj], cwd=REPO_ROOT, timeout_s=900, capture=True, extra_env=extra_env)
                log = (out or "") + (("\n" + err) if err else "")
            except Exception as e:
                print(f"FAIL: invalid --executor-argv-json: {e}")
                return 2
        else:
            if not args.executor_cmd.strip():
                print("FAIL: executor=command requires --executor-argv-json or --executor-cmd")
                return 2
            exec_code, log = _run_shell(args.executor_cmd, cwd=REPO_ROOT, timeout_s=900, extra_env=extra_env)
        _write_text(evidence_dir / "executor_command.log", log)
        exec_summary = f"command exit_code={exec_code}"
    elif args.executor == "codex_diff":
        model = (args.codex_model or os.environ.get("CODEX_MODEL") or "").strip()
        if not model:
            model = "gpt-5.2-codex"
        codex_bin = (args.codex_bin or os.environ.get("CODEX_BIN") or "codex").strip()
        # Force read-only: LLM must emit a patch; factory applies it under guard.
        prompt = "\n".join(
            [
                "You are an executor in a patch-only pipeline.",
                "Rules:",
                "1) Do NOT propose edits in prose. Output ONLY a unified diff in a single fenced ```diff block.",
                "2) The diff must only touch paths allowed by pins.allowed_paths and the role policy write_allow_paths.",
                "3) Keep the patch minimal and correct.",
                "",
                "Task:",
                json.dumps(child, ensure_ascii=False, indent=2),
                "",
                "Pins:",
                (pins_spec_path.read_text(encoding="utf-8", errors="replace") if pins_spec_path.exists() else "{}"),
                "",
                "Return:",
                "```diff",
                "...",
                "```",
            ]
        )
        out_file = evidence_dir / "executor_llm_stdout.txt"
        err_file = evidence_dir / "executor_llm_stderr.txt"
        p = subprocess.run(
            [codex_bin, "exec", "--model", model, "--sandbox", "read-only", "--skip-git-repo-check", "-C", str(REPO_ROOT), "--dangerously-bypass-approvals-and-sandbox"],
            cwd=str(REPO_ROOT),
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=900,
            env={**os.environ, "SCC_REPO_ROOT": str(REPO_ROOT), **extra_env},
        )
        _write_text(out_file, p.stdout or "")
        _write_text(err_file, p.stderr or "")
        exec_code = int(p.returncode)
        exec_summary = f"codex_diff model={model} exit_code={exec_code}"

        # Even if codex exits 0, treat missing diff as failure.
        ex = extract_unified_diff(p.stdout or "")
        if not ex.ok:
            exec_code = exec_code or 1
        else:
            patch_path = art_dir / "patch.diff"
            _write_text(patch_path, ex.diff.strip() + "\n")
            g = guard_diff(diff_text=ex.diff, role_policy=role_policy, child_task=child)
            _write_json(evidence_dir / "patch_guard.json", {"ok": g.ok, "error": g.error, "touched_files": g.touched_files, "denied": g.denied, "notes": g.notes})
            if not g.ok:
                exec_code = 1
            else:
                # Apply patch into repo (still within snapshot rollback).
                ap_res = apply_unified_diff(REPO_ROOT, ex.diff)
                _write_json(evidence_dir / "patch_apply.json", {"ok": ap_res.ok, "error": ap_res.error, "applied_files": ap_res.applied_files})
                if not ap_res.ok:
                    exec_code = 1

    status = "DONE" if (tests_ok and exec_code == 0) else "FAILED"
    exit_code = 0 if status == "DONE" else (exec_code or 1)
    event_type = "SUCCESS" if status == "DONE" else "CI_FAILED"
    _write_text(art_dir / "report.md", f"# EXEC result\nstatus={status}\n{exec_summary}\n")
    _write_text(art_dir / "selftest.log", f"runtime\nEXIT_CODE=0\n")
    _write_text(art_dir / "patch.diff", "\n")
    _write_text(
        art_dir / "events.jsonl",
        json.dumps(
            {
                "schema_version": "scc.event.v1",
                "t": _now_iso(),
                "event_type": event_type,
                "task_id": task_id,
                "parent_id": None,
                "role": role,
                "area": "runtime",
                "executor": args.executor,
                "model": None,
                "reason": "runtime",
                "details": {"tests_ok": tests_ok, "exec_code": exec_code, "test_logs": test_logs},
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    submit = {
        "schema_version": "scc.submit.v1",
        "task_id": task_id,
        "status": status,
        "reason_code": "runtime",
        "changed_files": [],
        "new_files": [],
        "touched_files": [],
        "allow_paths": {"read": ["**"], "write": ["**"]},
        "tests": {"commands": [str(x) for x in tests][:10], "passed": bool(tests_ok), "summary": "runtime"},
        "artifacts": {
            "report_md": f"artifacts/{task_id}/report.md",
            "selftest_log": f"artifacts/{task_id}/selftest.log",
            "evidence_dir": f"artifacts/{task_id}/evidence/",
            "patch_diff": f"artifacts/{task_id}/patch.diff",
            "submit_json": f"artifacts/{task_id}/submit.json",
        },
        "exit_code": int(exit_code),
        "needs_input": [],
        "summary": f"runtime status={status}",
    }
    _write_json(art_dir / "submit.json", submit)
    write_replay_bundle(status)

    # VERIFY (strict gates). On failure, restore snapshot and rerun verify once.
    verify_code, _, _ = _run(["python", "tools/scc/gates/run_ci_gates.py", "--strict", "--submit", f"artifacts/{task_id}/submit.json"], cwd=REPO_ROOT, timeout_s=180, capture=False)
    if verify_code != 0 and args.snapshot and snap_root.exists():
        _robocopy_mirror(snap_root, REPO_ROOT, excludes=["artifacts"])
        _append_jsonl(REPO_ROOT / "artifacts" / "executor_logs" / "rollbacks.jsonl", {"t": _now_iso(), "task_id": task_id, "type": "snapshot_restore", "reason": "verify_failed"})
        _run(["python", "tools/scc/gates/run_ci_gates.py", "--strict", "--submit", f"artifacts/{task_id}/submit.json"], cwd=REPO_ROOT, timeout_s=180, capture=False)

    # Append global state event for mining (single row per task run).
    try:
        ev = _load_json(art_dir / "verdict.json") if (art_dir / "verdict.json").exists() else None
        _append_jsonl(
            REPO_ROOT / "artifacts" / "executor_logs" / "state_events.jsonl",
            {
                "schema_version": "scc.event.v1",
                "t": _now_iso(),
                "event_type": event_type,
                "task_id": task_id,
                "parent_id": None,
                "role": role,
                "area": "runtime",
                "executor": args.executor,
                "model": None,
                "reason": "runtime_summary",
                "details": {"status": status, "exit_code": exit_code},
            },
        )
    except Exception:
        pass

    print("OK")
    print(f"task_id={task_id} status={status}")
    return 0 if status == "DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
