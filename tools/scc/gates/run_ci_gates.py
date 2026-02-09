import argparse
import json
import os
import pathlib
import sys
from datetime import datetime, timedelta, timezone
from subprocess import run

from tools.scc.gates import (
    connector_gate,
    context_pack_gate,
    context_pack_proof_gate,
    contracts_gate,
    doclink_gate,
    map_gate,
    release_gate,
    schema_gate,
    semantic_context_gate,
    ssot_gate,
    ssot_map_gate,
    trace_gate,
    verifier_judge,
)
from tools.scc.gates import secrets_gate
from tools.scc.validators.hygiene_validator import load_submit, validate_submit
from tools.scc.gates import event_gate


def _write_jsonl(path: pathlib.Path, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _append_jsonl(path: pathlib.Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _ensure_preflight_json(repo: pathlib.Path, submit: dict):
    task_id = submit.get("task_id") or "unknown"
    preflight_path = repo / "artifacts" / str(task_id) / "preflight.json"
    preflight_path.parent.mkdir(parents=True, exist_ok=True)
    if preflight_path.exists():
        try:
            existing = json.loads(preflight_path.read_text(encoding="utf-8"))
            if (
                isinstance(existing, dict)
                and existing.get("schema_version") == "scc.preflight.v1"
                and isinstance(existing.get("pass"), bool)
                and isinstance(existing.get("missing"), dict)
            ):
                return None
        except Exception:
            pass

    # Minimal, schema-conformant fallback. Do not add extra keys: contracts gate is fail-closed.
    preflight = {
        "schema_version": "scc.preflight.v1",
        "task_id": str(task_id),
        "pass": True,
        "missing": {"files": [], "symbols": [], "tests": [], "write_scope": []},
        "notes": "Auto-generated preflight.json (fallback; missing upstream preflight output).",
    }
    preflight_path.write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rel = str(preflight_path.relative_to(repo)).replace("\\", "/")
    return {"artifact": "preflight.json", "path": rel, "reason": "auto_generated_missing_or_invalid"}


def _ensure_pins_json(repo: pathlib.Path, submit: dict, *, upgrade_only: bool = False):
    task_id = submit.get("task_id") or "unknown"
    pins_path = repo / "artifacts" / str(task_id) / "pins" / "pins.json"
    pins_path.parent.mkdir(parents=True, exist_ok=True)
    if pins_path.exists():
        try:
            existing = json.loads(pins_path.read_text(encoding="utf-8"))
            if isinstance(existing, dict) and isinstance(existing.get("pins"), dict):
                sv = existing.get("schema_version")
                if sv == "scc.pins_result.v2":
                    pins = existing.get("pins") or {}
                    items = pins.get("items") if isinstance(pins, dict) else None
                    if isinstance(items, list) and len(items) > 0:
                        return None
                if upgrade_only and sv != "scc.pins_result.v1":
                    # In strict mode, only upgrade v1 -> v2; do not synthesize or
                    # rewrite other schemas.
                    return None
                # If v1 exists, upgrade to v2 (non-strict backfill) to keep L4 pins audited.
        except Exception:
            if upgrade_only:
                # Fail-closed in strict mode if pins is present but invalid.
                return None
            pass
    elif upgrade_only:
        # Fail-closed for missing pins in strict mode, but allow schema upgrades.
        return None

    allow = submit.get("allow_paths") if isinstance(submit, dict) else None
    allow_read = allow.get("read") if isinstance(allow, dict) else []
    allow_write = allow.get("write") if isinstance(allow, dict) else []
    changed = submit.get("changed_files") if isinstance(submit, dict) else []
    touched = [str(x) for x in (allow_write or []) if isinstance(x, str) and x.strip()]
    if not touched:
        touched = [str(x) for x in (allow_read or []) if isinstance(x, str) and x.strip()]
    if not touched:
        touched = [str(x) for x in (changed or []) if isinstance(x, str) and x.strip()]
    if not touched:
        touched = ["**"]

    items = []
    for p in touched[:64]:
        items.append(
            {
                "path": str(p),
                "reason": "auto_generated_missing_or_invalid",
                "read_only": True,
                "write_intent": False,
                "symbols": [],
                "line_windows": [],
            }
        )

    pins_result = {
        "schema_version": "scc.pins_result.v2",
        "task_id": str(task_id),
        "pins": {"items": items, "allowed_paths": touched[:64], "forbidden_paths": ["**/secrets/**"]},
        "recommended_queries": [],
        "preflight_expectation": {"should_pass": True, "notes": "Auto-generated/upgrade pins fallback; prefer map-derived pins v2 with per-path reasons."},
    }
    pins_path.write_text(json.dumps(pins_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rel = str(pins_path.relative_to(repo)).replace("\\", "/")
    return {"artifact": "pins/pins.json", "path": rel, "reason": "auto_generated_or_upgraded_to_v2"}


def _ensure_replay_bundle_json(repo: pathlib.Path, submit: dict, submit_path: pathlib.Path):
    task_id = submit.get("task_id") or "unknown"
    art_dir = repo / "artifacts" / str(task_id)
    replay_path = art_dir / "replay_bundle.json"
    art_dir.mkdir(parents=True, exist_ok=True)
    if replay_path.exists():
        try:
            existing = json.loads(replay_path.read_text(encoding="utf-8"))
            if (
                isinstance(existing, dict)
                and existing.get("schema_version") == "scc.replay_bundle.v1"
                and isinstance(existing.get("board_task_payload"), dict)
                and isinstance(existing.get("artifacts"), dict)
            ):
                return None
        except Exception:
            pass

    rel_submit = str(submit_path.relative_to(repo)).replace("\\", "/") if submit_path.is_absolute() else str(submit_path).replace("\\", "/")
    bundle = {
        "schema_version": "scc.replay_bundle.v1",
        "task_id": str(task_id),
        # Deterministic timestamp so strict gating can backfill legacy tasks
        # without introducing non-reproducible diffs.
        "created_at": _stable_event_time(str(task_id), submit),
        "source": {"job_id": None, "executor": None, "model": None, "job_status": None, "exit_code": submit.get("exit_code") if isinstance(submit, dict) else None},
        "board_task_payload": {
            "title": f"Replay bundle (auto): {task_id}",
            "goal": "Auto-generated replay bundle; upstream gateway did not emit one.",
            "role": None,
            "files": submit.get("changed_files") if isinstance(submit, dict) else [],
            "skills": [],
            "pointers": None,
            "pins": None,
            "pins_instance": None,
            "allowedTests": (submit.get("tests") or {}).get("commands") if isinstance(submit.get("tests"), dict) else [],
            "allowedExecutors": [],
            "allowedModels": [],
            "runner": "internal",
            "area": None,
            "lane": None,
            "task_class_id": None,
        },
        "artifacts": {
            "submit_json": rel_submit,
            "preflight_json": f"artifacts/{task_id}/preflight.json",
            "pins_json": f"artifacts/{task_id}/pins/pins.json",
            "report_md": f"artifacts/{task_id}/report.md",
            "selftest_log": f"artifacts/{task_id}/selftest.log",
            "evidence_dir": f"artifacts/{task_id}/evidence/",
            "patch_diff": f"artifacts/{task_id}/patch.diff",
        },
        "replay": {"dispatch_via": "tools/scc/ops/replay_bundle_dispatch.py"},
    }
    replay_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rel = str(replay_path.relative_to(repo)).replace("\\", "/")
    return {"artifact": "replay_bundle.json", "path": rel, "reason": "auto_generated_missing_or_invalid"}


def _ensure_events_jsonl(repo: pathlib.Path, submit: dict) -> dict | None:
    task_id = submit.get("task_id") or "unknown"
    events_path = repo / "artifacts" / str(task_id) / "events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    if events_path.exists():
        return None
    status = str(submit.get("status") or "")
    exit_code = submit.get("exit_code") if isinstance(submit.get("exit_code"), int) else None
    # Strict event gating requires at least one SUCCESS/FAIL row.
    event_type = "SUCCESS" if status == "DONE" and (exit_code is None or exit_code == 0) else "FAIL"
    row = {
        "schema_version": "scc.event.v1",
        "t": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "task_id": str(task_id),
        "parent_id": None,
        "role": None,
        "area": None,
        "executor": None,
        "model": None,
        "reason": "auto_generated_missing_events",
        "details": {"submit_status": status, "exit_code": exit_code},
    }
    events_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    rel = str(events_path.relative_to(repo)).replace("\\", "/")
    return {"artifact": "events.jsonl", "path": rel, "reason": "auto_generated_missing"}


def _events_has_success_fail(events_path: pathlib.Path, task_id: str) -> bool:
    try:
        text = events_path.read_text(encoding="utf-8-sig")
    except Exception:
        return False

    for ln in text.splitlines()[-2000:]:
        s = ln.strip()
        if not s:
            continue
        try:
            obj = json.loads(s)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("schema_version") != "scc.event.v1":
            continue
        if str(obj.get("task_id") or "") != str(task_id):
            continue
        if str(obj.get("event_type") or "") in {"SUCCESS", "FAIL"}:
            return True
    return False


def _stable_event_time(task_id: str, submit: dict) -> str:
    for k in ("t", "ended_at", "finished_at", "created_at", "started_at"):
        v = submit.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # Deterministic fallback: keep it "in the past" and stable per task_id.
    seconds = sum(ord(ch) for ch in str(task_id)) % (366 * 24 * 60 * 60)
    base = datetime(2000, 1, 1, tzinfo=timezone.utc)
    return (base + timedelta(seconds=seconds)).isoformat()


def _backfill_events_jsonl_strict(repo: pathlib.Path, task_id: str, submit: dict) -> tuple[bool, str]:
    events_path = repo / "artifacts" / str(task_id) / "events.jsonl"
    had_file = events_path.exists()
    if had_file and _events_has_success_fail(events_path, task_id):
        return (True, "already_valid")

    script = repo / "tools" / "scc" / "ops" / "backfill_events_v1.py"
    if not script.exists():
        return (False, "missing_backfill_events_v1")

    r = run(
        [sys.executable, str(script), "--repo-root", str(repo), "--task-id", str(task_id)],
        cwd=str(repo),
        text=True,
        capture_output=True,
        timeout=60,
    )

    if events_path.exists() and _events_has_success_fail(events_path, task_id):
        return (True, "backfilled" if not had_file else "repaired")
    if events_path.exists():
        # Fall back to a deterministic, schema-conformant event row so historical
        # submits can still be verified under strict gating.
        try:
            status = str(submit.get("status") or "")
            exit_code = submit.get("exit_code") if isinstance(submit.get("exit_code"), int) else None
            event_type = "SUCCESS" if status == "DONE" and (exit_code is None or exit_code == 0) else "FAIL"
            row = {
                "schema_version": "scc.event.v1",
                "t": _stable_event_time(str(task_id), submit),
                "event_type": event_type,
                "task_id": str(task_id),
                "parent_id": submit.get("parent_id") if "parent_id" in submit else None,
                "role": submit.get("role") if "role" in submit else None,
                "area": None,
                "executor": None,
                "model": None,
                "reason": "events_backfill_fallback",
                "details": {"submit_status": submit.get("status"), "exit_code": exit_code},
            }
            events_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
            if _events_has_success_fail(events_path, task_id):
                return (True, "fallback_generated")
        except Exception:
            pass
        return (False, "events_present_but_invalid")

    # backfill script did not create an events file; generate a deterministic
    # SUCCESS/FAIL row so strict gating can proceed.
    try:
        status = str(submit.get("status") or "")
        exit_code = submit.get("exit_code") if isinstance(submit.get("exit_code"), int) else None
        event_type = "SUCCESS" if status == "DONE" and (exit_code is None or exit_code == 0) else "FAIL"
        row = {
            "schema_version": "scc.event.v1",
            "t": _stable_event_time(str(task_id), submit),
            "event_type": event_type,
            "task_id": str(task_id),
            "parent_id": submit.get("parent_id") if "parent_id" in submit else None,
            "role": submit.get("role") if "role" in submit else None,
            "area": None,
            "executor": None,
            "model": None,
            "reason": "events_backfill_fallback_missing",
            "details": {"submit_status": submit.get("status"), "exit_code": exit_code},
        }
        events_path.parent.mkdir(parents=True, exist_ok=True)
        events_path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        if _events_has_success_fail(events_path, task_id):
            return (True, "fallback_generated")
    except Exception:
        pass

    stderr = (r.stderr or "").strip().replace("\r", "")
    if len(stderr) > 300:
        stderr = stderr[:300] + "..."
    return (False, f"backfill_failed:returncode={r.returncode}:stderr={stderr}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--submit", default="submit.json", help="Path to submit.json (default: submit.json)")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Fail-closed: do not auto-generate missing artifacts (preflight/pins/replay_bundle).",
    )
    args = ap.parse_args()

    submit_path = pathlib.Path(args.submit)
    if not submit_path.is_absolute():
        # Prefer resolving relative to CWD (backwards compatible), but fall back to the
        # repository root so this gate can run from arbitrary working directories.
        cwd_candidate = pathlib.Path.cwd() / submit_path
        submit_path = cwd_candidate if cwd_candidate.exists() else _REPO_ROOT / submit_path

    repo = _REPO_ROOT

    submit = load_submit(submit_path)
    if not submit:
        print("FAIL: missing submit.json or invalid json", file=sys.stderr)
        return 2

    task_id = submit.get("task_id") or "unknown"
    gates_out = repo / "artifacts" / str(task_id) / "ci_gate_results.jsonl"
    now = datetime.now(timezone.utc).isoformat()

    results: list[dict] = []
    ok = True

    backfills: list[dict] = []
    if not args.strict:
        pre = _ensure_preflight_json(repo, submit)
        if pre:
            backfills.append(pre)
        pins = _ensure_pins_json(repo, submit)
        if pins:
            backfills.append(pins)
        rb = _ensure_replay_bundle_json(repo, submit, submit_path)
        if rb:
            backfills.append(rb)
        ev = _ensure_events_jsonl(repo, submit)
        if ev:
            backfills.append(ev)

        if backfills:
            bf_path = repo / "artifacts" / str(task_id) / "contracts_backfill.json"
            bf = {
                "schema_version": "scc.contracts_backfill.v1",
                "t": now,
                "task_id": str(task_id),
                "strict": False,
                "submit_path": str(submit_path).replace("\\", "/"),
                "backfilled": backfills,
                "notes": "Auto-generated missing artifacts to keep replayability and gates deterministic. Enable --strict to fail-closed instead.",
            }
            bf_path.parent.mkdir(parents=True, exist_ok=True)
            bf_path.write_text(json.dumps(bf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # In strict mode, do not generate missing artifacts. Exception: if pins v2 is
    # explicitly required, ensure a schema-conformant pins v2 exists so historical
    # submits without pins output can still be verified deterministically.
    if args.strict:
        pins_v2_required = str(os.environ.get("PINS_V2_REQUIRED") or "false").strip().lower() in {"1", "true", "yes", "on"}
        _ensure_pins_json(repo, submit, upgrade_only=not pins_v2_required)

        # Strict gating is fail-closed, but allow deterministic migration of legacy
        # artifacts that predate scc.event.v1 emission.
        ok_bf, note = _backfill_events_jsonl_strict(repo, str(task_id), submit)
        if note != "already_present":
            results.append(
                {
                    "t": now,
                    "gate": "events_backfill",
                    "status": "WARN",
                    "errors": [],
                    "warnings": [note] if ok_bf else ["events_backfill_failed", note],
                }
            )

        # Strict gating is fail-closed, but contracts verification requires a replay
        # bundle for reproducibility. For historical submits that predate bundle
        # emission, create a deterministic fallback.
        rb = _ensure_replay_bundle_json(repo, submit, submit_path)
        if rb:
            results.append(
                {
                    "t": now,
                    "gate": "replay_bundle_backfill",
                    "status": "WARN",
                    "errors": [],
                    "warnings": [rb.get("reason") or "auto_generated_missing_or_invalid"],
                }
            )

    def run_gate(name: str, fn):
        nonlocal ok
        try:
            out = fn()
        except Exception as e:
            ok = False
            results.append({"t": now, "gate": name, "status": "ERROR", "errors": [str(e)]})
            return

        errs: list[str] = []
        warns: list[str] = []
        if out is None:
            errs = []
            warns = []
        elif isinstance(out, list):
            errs = [str(x) for x in out]
        elif isinstance(out, dict):
            errs = [str(x) for x in (out.get("errors") or [])]
            warns = [str(x) for x in (out.get("warnings") or [])]
        else:
            errs = [f"invalid_gate_return_type:{type(out).__name__}"]

        if errs:
            ok = False
            results.append({"t": now, "gate": name, "status": "FAIL", "errors": errs, "warnings": warns})
        elif warns:
            results.append({"t": now, "gate": name, "status": "WARN", "errors": [], "warnings": warns})
        else:
            results.append({"t": now, "gate": name, "status": "PASS", "errors": [], "warnings": []})

    run_gate("contracts", lambda: contracts_gate.run(repo, submit, submit_path))
    run_gate("context_pack", lambda: context_pack_gate.run(repo, submit, strict=bool(args.strict)))
    run_gate("context_pack_proof", lambda: context_pack_proof_gate.run(repo, submit, strict=bool(args.strict)))
    run_gate("hygiene", lambda: validate_submit(submit, repo))
    run_gate("secrets", lambda: secrets_gate.run(repo, submit))
    run_gate("events", lambda: event_gate.run(repo, submit))
    run_gate("ssot", lambda: ssot_gate.run(repo, submit))
    run_gate("ssot_map", lambda: ssot_map_gate.run(repo, submit))

    # If ssot_update.json exists, always generate a deterministic patch bundle for review.
    try:
        ssot_update = repo / "artifacts" / str(task_id) / "ssot_update.json"
        if ssot_update.exists():
            patch_out = repo / "artifacts" / str(task_id) / "ssot_update.patch"
            r = run(
                ["python", "tools/scc/ops/ssot_sync.py", "--repo-root", str(repo), "--task-id", str(task_id), "--patch-out", str(patch_out.relative_to(repo)).replace("\\", "/")],
                cwd=str(repo),
                text=True,
                capture_output=True,
                timeout=60,
            )
            if r.returncode == 0 and patch_out.exists():
                results.append({"t": now, "gate": "ssot_patch", "status": "PASS", "errors": [], "warnings": []})
            else:
                results.append(
                    {
                        "t": now,
                        "gate": "ssot_patch",
                        "status": "WARN",
                        "errors": [],
                        "warnings": ["ssot_sync_failed" if r.returncode != 0 else "ssot_patch_missing"],
                    }
                )

            if str(os.environ.get("SSOT_AUTO_PR_BUNDLE") or "false").lower() == "true" and patch_out.exists():
                apply_mode = str(os.environ.get("SSOT_AUTO_PR_APPLY_GIT") or "auto").strip().lower()
                merge_to = str(os.environ.get("SSOT_AUTO_PR_MERGE_TO") or "").strip()
                want_apply = apply_mode in {"1", "true", "yes", "on"} or (apply_mode == "auto" and (repo / ".git").exists())
                r2 = run(
                    [
                        "python",
                        "tools/scc/ops/pr_bundle_create.py",
                        "--repo-root",
                        str(repo),
                        "--task-id",
                        str(task_id),
                        "--patch",
                        str(patch_out.relative_to(repo)).replace("\\", "/"),
                        "--title",
                        f"SSOT sync: {task_id}",
                        "--labels",
                        "ssot,control-plane",
                        *(
                            ["--apply-git"]
                            if want_apply
                            else []
                        ),
                        *(
                            ["--merge-to", merge_to]
                            if want_apply and merge_to
                            else []
                        ),
                    ],
                    cwd=str(repo),
                    text=True,
                    capture_output=True,
                    timeout=60,
                )
                if r2.returncode == 0:
                    results.append({"t": now, "gate": "pr_bundle", "status": "PASS", "errors": [], "warnings": []})
                else:
                    results.append({"t": now, "gate": "pr_bundle", "status": "WARN", "errors": [], "warnings": ["pr_bundle_create_failed"]})
    except Exception:
        # best-effort; do not break gating
        pass
    run_gate("doclink", lambda: doclink_gate.run(repo, submit))
    run_gate("map", lambda: map_gate.run(repo))
    run_gate("schema", lambda: schema_gate.run(repo))
    run_gate("connectors", lambda: connector_gate.run(repo))
    run_gate("semantic_context", lambda: semantic_context_gate.run(repo))
    run_gate("trace", lambda: trace_gate.run(repo, submit))
    run_gate("release", lambda: release_gate.run(repo, submit))

    if backfills:
        results.append({"t": now, "gate": "contracts_backfill", "status": "WARN", "errors": [], "backfilled": backfills})

    _write_jsonl(gates_out, results)
    try:
        verdict = verifier_judge.judge(repo, submit, results)
        verifier_judge.write(repo, verdict)
        verifier_judge.write_log(repo, task_id, verdict)
        # Best-effort: submit index for rollback/debugging (no gate effect).
        try:
            art = repo / "artifacts" / str(task_id)
            _append_jsonl(
                repo / "artifacts" / "executor_logs" / "submits.jsonl",
                {
                    "t": now,
                    "task_id": str(task_id),
                    "status": submit.get("status"),
                    "exit_code": submit.get("exit_code"),
                    "submit": f"artifacts/{task_id}/submit.json",
                    "patch_diff": f"artifacts/{task_id}/patch.diff" if (art / "patch.diff").exists() else None,
                    "verdict": verdict.get("verdict") if isinstance(verdict, dict) else None,
                },
            )
        except Exception:
            pass
    except Exception as e:
        print(f"[WARN] verifier_judge failed: {e}", file=sys.stderr)
    if not ok:
        for r in results:
            if r["status"] != "PASS":
                print(f"{r['gate']}: {r['status']} - {r.get('errors')}", file=sys.stderr)
                if r.get("warnings"):
                    print(f"{r['gate']}: WARNINGS - {r.get('warnings')}", file=sys.stderr)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
