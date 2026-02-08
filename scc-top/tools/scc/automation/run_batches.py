#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SCC automation runner (client-side).

Design:
- Runs outside the unified_server process (so we avoid self-HTTP recursion/deadlocks).
- Talks to unified_server via HTTP:
  - waits for /health/ready
  - optional /executor/codex/parallel_probe to pick a safe max_outstanding
  - /executor/codex/run to execute batches (each batch: 5 parents)
- Writes an automation manifest under artifacts/scc_state/automation_runs/<run_id>/.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8", errors="replace")
    os.replace(tmp, path)


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


def _read_json_safe(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def _extract_patch_files_from_git_patch(text: str) -> List[str]:
    files: List[str] = []
    for line in (text or "").splitlines():
        if line.startswith("diff --git a/") and " b/" in line:
            try:
                tail = line.split("diff --git a/", 1)[1]
                _a, b = tail.split(" b/", 1)
                p = (b or "").strip().replace("\\", "/")
                if p:
                    files.append(p)
            except Exception:
                continue
    # stable de-dupe
    seen = set()
    return [p for p in files if not (p in seen or seen.add(p))]


def _is_contract_generated_only(files: List[str]) -> bool:
    if not files:
        return False
    for p in files:
        p2 = str(p).replace("\\", "/")
        if not p2.startswith("docs/ssot/04_contracts/generated/"):
            return False
        if not p2.endswith(".json"):
            return False
    return True


def _contract_files_smoke(*, repo_root: Path, files: List[str]) -> Tuple[bool, List[str]]:
    """
    Deterministic local validation for contract JSON files (no Postgres, no network).
    Returns (ok, errors[]).
    """
    errs: List[str] = []
    for rel in files:
        p = (repo_root / rel).resolve()
        if not p.exists():
            errs.append(f"missing:{rel}")
            continue
        if not str(rel).replace("\\", "/").startswith("docs/ssot/04_contracts/generated/"):
            errs.append(f"unexpected_path:{rel}")
            continue
        try:
            subprocess.run([sys.executable, "-m", "json.tool", str(p)], cwd=str(repo_root), check=True, capture_output=True)
        except Exception as e:
            errs.append(f"json_invalid:{rel}:{e}")
            continue
        try:
            # Required fields + scope_allow includes io refs.
            code = (
                "import json; p=r'"
                + str(rel).replace("'", "\\'")
                + "'; d=json.load(open(p,encoding='utf-8')); "
                "req=['goal','scope_allow','constraints','acceptance','stop_condition','commands_hint','inputs_ref','outputs_expected']; "
                "missing=[k for k in req if k not in d]; assert not missing, missing; "
                "sa=d.get('scope_allow'); assert isinstance(sa,list) and [x for x in sa if str(x).strip()]; "
                "refs=set(); "
                "refs |= set((d.get('inputs_ref') or {}).get('paths') or []) if isinstance(d.get('inputs_ref'), dict) else set(); "
                "refs |= set((d.get('outputs_expected') or {}).get('evidence_paths') or []) if isinstance(d.get('outputs_expected'), dict) else set(); "
                "tt=d.get('task_tree_ref'); refs.add(tt) if isinstance(tt,str) and tt.strip() else None; "
                "missing2=sorted([r for r in refs if str(r).strip() and str(r).strip() not in set(sa)]); "
                "assert not missing2, missing2; "
                "print('OK')"
            )
            subprocess.run([sys.executable, "-c", code], cwd=str(repo_root), check=True, capture_output=True)
        except Exception as e:
            errs.append(f"contract_check_failed:{rel}:{e}")
            continue
    return (len(errs) == 0), errs


def _maybe_fallback_contract_harden(
    *,
    repo_root: Path,
    parent_id: str,
    parent_artifacts_dir: Path,
    area: str,
    task_code_prefix: str,
    allow: bool,
) -> dict:
    """
    Deterministic fallback for a common failure mode:
    - LLM output patch is truncated -> git apply fails (often "corrupt patch at line ...")
    - When the intended changes are only under docs/ssot/04_contracts/generated/*.json,
      we can deterministically harden those contracts without LLM tokens.
    """
    out: dict = {"attempted": False, "ran": False, "taskcode": None, "reason": ""}
    if not allow:
        out["reason"] = "disabled"
        return out

    se = parent_artifacts_dir / "scope_enforcement.json"
    if not se.exists():
        out["reason"] = "missing_scope_enforcement"
        return out
    j = _read_json_safe(se)
    apply_ok = j.get("apply_ok", None)
    apply_error = str(j.get("apply_error") or "")
    # For generated-contract-only parents, we can attempt fallback whenever the apply didn't succeed.
    # This reduces token burn and avoids patch corruption / empty patch outputs.
    if apply_ok is True:
        out["reason"] = "apply_ok_true"
        return out

    patch_text = ""
    patch_path = parent_artifacts_dir / "patch.diff"
    if patch_path.exists():
        try:
            patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            patch_text = ""
    files = _extract_patch_files_from_git_patch(patch_text)
    if not files:
        # Some failures produce empty patch.diff; fall back to allowlist/untracked hints.
        ag = j.get("allowed_globs")
        if isinstance(ag, list):
            files.extend([str(x).strip().replace("\\", "/") for x in ag if str(x).strip()])
        uf = j.get("untracked_files")
        if isinstance(uf, list):
            files.extend([str(x).strip().replace("\\", "/") for x in uf if str(x).strip()])
        # stable de-dupe
        seen = set()
        files = [p for p in files if not (p in seen or seen.add(p))]
    if not _is_contract_generated_only(files):
        out["reason"] = "not_contract_generated_only"
        out["patch_files"] = files
        return out

    out["attempted"] = True
    taskcode = _safe_taskcode(f"{task_code_prefix}__FALLBACK_HARDEN__{parent_id}")
    out["taskcode"] = taskcode
    cmd = [
        sys.executable,
        "tools/scc/ops/contract_harden_job.py",
        "--area",
        area,
        "--taskcode",
        taskcode,
        "--include-non-tbd",
        "--contracts",
        *files,
    ]
    p = subprocess.run(cmd, cwd=str(repo_root))
    out["ran"] = True
    out["exit_code"] = int(p.returncode or 0)
    out["patch_files"] = files
    if out["exit_code"] == 0:
        out["reason"] = "ok"
    else:
        # preserve apply_error hint (useful for debugging) without blocking fallback attempts
        out["reason"] = "fallback_failed"
        if apply_error:
            out["apply_error_head"] = apply_error[:200]
    return out


def _http(method: str, url: str, *, json_body: Any | None = None, timeout_s: float = 10.0) -> Tuple[int, str]:
    import urllib.request
    import urllib.error

    data = None
    headers = {"Content-Type": "application/json"}
    if json_body is not None:
        data = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return int(getattr(resp, "status", 200)), body
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return int(getattr(e, "code", 500)), body or str(e)
    except Exception as e:
        return 0, str(e)


def _wait_ready(base: str, *, timeout_s: float = 120.0, interval_s: float = 1.0) -> bool:
    t0 = time.time()
    while True:
        code, _ = _http("GET", f"{base}/health/ready", timeout_s=3.0)
        if 200 <= code < 300:
            return True
        if time.time() - t0 > timeout_s:
            return False
        time.sleep(interval_s)


@dataclass
class ProbeResult:
    ok: bool
    max_outstanding: int
    max_seen: int
    duration_s: float
    raw: dict


def _parallel_probe(base: str, *, n: int, max_outstanding: int, sleep_ms: int) -> ProbeResult:
    code, body = _http(
        "POST",
        f"{base}/executor/codex/parallel_probe",
        json_body={"n": n, "max_outstanding": max_outstanding, "sleep_ms": sleep_ms},
        timeout_s=30.0,
    )
    raw: dict = {}
    try:
        raw = json.loads(body or "{}")
    except Exception:
        raw = {"_raw": body}
    ok = bool(raw.get("ok")) and 200 <= code < 300
    return ProbeResult(
        ok=ok,
        max_outstanding=int(raw.get("max_outstanding") or max_outstanding),
        max_seen=int(raw.get("max_concurrency_seen") or 0),
        duration_s=float(raw.get("duration_s") or 0.0),
        raw=raw,
    )


def _get_executor_limit(base: str) -> int:
    code, body = _http("GET", f"{base}/executor/status", timeout_s=5.0)
    if not (200 <= code < 300):
        return 1
    try:
        j = json.loads(body or "{}")
    except Exception:
        return 1
    try:
        cfg = (j.get("config") or {}).get("codex") or {}
        lim = int(cfg.get("max_outstanding_limit") or 1)
        return max(1, lim)
    except Exception:
        return 1


def _pick_max_outstanding(base: str, *, limit: int, sleep_ms: int = 700) -> Tuple[int, List[dict]]:
    """
    Empirical probe (token-free). Picks the best K <= limit.
    """
    results: List[dict] = []
    best = 1
    # If probe endpoint is unavailable, fall back to executor config limit.
    probe_supported = True
    for k in range(1, max(1, limit) + 1):
        pr = _parallel_probe(base, n=max(4, k * 2), max_outstanding=k, sleep_ms=sleep_ms)
        results.append({"k": k, "ok": pr.ok, "max_seen": pr.max_seen, "duration_s": pr.duration_s, "raw": pr.raw})
        if not pr.ok and isinstance(pr.raw, dict) and str(pr.raw.get("_raw") or "").find("Not Found") >= 0:
            probe_supported = False
            break
        if pr.ok and pr.max_seen >= k:
            best = k
    if not probe_supported:
        best = min(max(1, int(limit or 1)), _get_executor_limit(base))
    return best, results


def _run_batch(
    base: str,
    *,
    parents: dict,
    model: str,
    timeout_s: float,
    max_outstanding: int,
    dangerously_bypass: bool,
    retry_count: int = 5,
    retry_backoff_s: float = 1.0,
) -> dict:
    payload = {
        "parents": parents,
        "model": model,
        "timeout_s": timeout_s,
        "max_outstanding": max_outstanding,
        "dangerously_bypass": bool(dangerously_bypass),
    }
    url = f"{base}/executor/codex/run"
    timeout_eff = max(30.0, timeout_s + 30.0)
    attempts: list[dict] = []
    backoff = max(0.5, float(retry_backoff_s or 1.0))
    for i in range(max(1, int(retry_count or 1))):
        code, body = _http("POST", url, json_body=payload, timeout_s=timeout_eff)
        attempts.append(
            {
                "attempt": i + 1,
                "http_status": int(code or 0),
                "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        )

        # Success
        if 200 <= int(code or 0) < 300:
            break

        # Transient failures (common when local server is restarting):
        # - code==0: connection refused/reset/timeout
        # - 5xx: server restarting
        msg = str(body or "")
        transient = (int(code or 0) == 0) or (500 <= int(code or 0) <= 599)
        if transient and int(code or 0) == 0:
            transient = any(
                s in msg
                for s in [
                    "WinError 10061",  # actively refused
                    "WinError 10054",  # connection forcibly closed
                    "WinError 10053",  # software caused connection abort
                    "Connection reset",
                    "RemoteDisconnected",
                    "timed out",
                    "timeout",
                    "refused",
                ]
            )

        if not transient:
            break

        # Wait for server readiness again, then retry with exponential backoff.
        _wait_ready(base, timeout_s=60.0, interval_s=1.0)
        time.sleep(backoff)
        backoff = min(30.0, backoff * 1.7)
    try:
        out = json.loads(body or "{}")
    except Exception:
        out = {"_raw": body}
    out["_http_status"] = code
    out["_attempts"] = attempts
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("SCC_BASE_URL", "http://127.0.0.1:18788"))
    ap.add_argument("--config", default=os.environ.get("SCC_AUTOMATION_CONFIG", "configs/scc/parent_batches.v1.json"))
    ap.add_argument("--auto-probe-max", action="store_true", default=(os.environ.get("SCC_AUTOMATION_AUTO_PROBE_MAX", "true").lower() == "true"))
    ap.add_argument("--probe-limit", type=int, default=int(os.environ.get("SCC_AUTOMATION_PROBE_LIMIT", "4")))
    ap.add_argument("--max-outstanding", type=int, default=int(os.environ.get("SCC_AUTOMATION_MAX_OUTSTANDING", "0")))
    ap.add_argument("--model", default=os.environ.get("A2A_CODEX_MODEL", "gpt-5.2"))
    ap.add_argument("--timeout-s", type=float, default=float(os.environ.get("A2A_CODEX_TIMEOUT_SEC", "900")))
    ap.add_argument("--dangerously-bypass", action="store_true", default=(os.environ.get("SCC_AUTOMATION_DANGEROUSLY_BYPASS", "false").lower() == "true"))
    ap.add_argument("--retry-count", type=int, default=int(os.environ.get("SCC_AUTOMATION_RETRY_COUNT", "5")))
    ap.add_argument("--retry-backoff-s", type=float, default=float(os.environ.get("SCC_AUTOMATION_RETRY_BACKOFF_S", "1.0")))
    ap.add_argument("--area", default=os.environ.get("AREA", "control_plane"), help="AREA for deterministic fallbacks (docs/REPORT/<area>/...).")
    ap.add_argument(
        "--fallback-contract-harden",
        action="store_true",
        default=(os.environ.get("SCC_AUTOMATION_FALLBACK_CONTRACT_HARDEN", "true").lower() == "true"),
        help="If a parent fails with apply_failed and only touches docs/ssot/04_contracts/generated/*.json, run contract_harden_job deterministically.",
    )
    args = ap.parse_args()

    repo_root = _repo_root()
    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = (repo_root / cfg_path).resolve()
    if not cfg_path.exists():
        print(f"[automation] config not found: {cfg_path}", file=sys.stderr)
        return 2

    run_id = str(int(time.time() * 1000))
    out_dir = (repo_root / "artifacts" / "scc_state" / "automation_runs" / run_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = _read_json(cfg_path)
    batches = cfg.get("batches") if isinstance(cfg, dict) else None
    if not isinstance(batches, list) or not batches:
        print("[automation] invalid config: missing batches", file=sys.stderr)
        return 2

    # Deterministic guard: validate requested skills against RoleSpec/SkillSpec (fail-closed).
    skill_guard_report = (out_dir / "skill_guard_result.json").resolve()
    try:
        p = subprocess.run(
            [sys.executable, "tools/scc/ops/skill_guard.py", "--config", str(cfg_path), "--out", str(skill_guard_report)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
        if int(p.returncode or 0) != 0:
            print("[automation] skill_guard failed", file=sys.stderr)
            if p.stdout:
                print(p.stdout.strip(), file=sys.stderr)
            if p.stderr:
                print(p.stderr.strip(), file=sys.stderr)
            return 3
    except Exception as e:
        print(f"[automation] skill_guard exception: {e}", file=sys.stderr)
        return 3

    manifest = {
        "ok": False,
        "run_id": run_id,
        "base": str(args.base),
        "config": str(cfg_path),
        "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "end_utc": None,
        "model": str(args.model),
        "dangerously_bypass": bool(args.dangerously_bypass),
        "auto_probe_max": bool(args.auto_probe_max),
        "picked_max_outstanding": None,
        "probe_results": [],
        "batches": [],
        "skill_guard_report": str(skill_guard_report),
        "fallbacks": [],
    }
    _write_json(out_dir / "automation_manifest.json", manifest)

    if not _wait_ready(args.base, timeout_s=180.0, interval_s=1.0):
        manifest["end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        manifest["error"] = "server_not_ready"
        _write_json(out_dir / "automation_manifest.json", manifest)
        return 3

    picked = int(args.max_outstanding or 0)
    if picked <= 0:
        picked = int(cfg.get("max_outstanding") or 0) if isinstance(cfg, dict) else 0
    if picked <= 0 and bool(args.auto_probe_max):
        picked, probe = _pick_max_outstanding(args.base, limit=int(args.probe_limit or 4))
        manifest["probe_results"] = probe
    if picked <= 0:
        picked = 1

    manifest["picked_max_outstanding"] = picked
    _write_json(out_dir / "automation_manifest.json", manifest)

    for bi, batch in enumerate(batches, 1):
        name = str(batch.get("name") or f"batch_{bi}").strip()[:80]
        parents = batch.get("parents")
        if not isinstance(parents, dict):
            # allow a list of parent items
            items = batch.get("items") or batch.get("tasks")
            if isinstance(items, list):
                parents = {"parents": items}
        if not isinstance(parents, dict):
            manifest["batches"].append({"name": name, "ok": False, "error": "invalid_parents"})
            _write_json(out_dir / "automation_manifest.json", manifest)
            continue

        batch_entry = {"name": name, "start_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "response": None}
        _write_json(out_dir / f"{bi:02d}__{name}__request.json", {"parents": parents, "model": args.model, "max_outstanding": picked})
        resp = _run_batch(
            args.base,
            parents=parents,
            model=str(args.model),
            timeout_s=float(args.timeout_s),
            max_outstanding=picked,
            dangerously_bypass=bool(args.dangerously_bypass),
            retry_count=int(args.retry_count or 1),
            retry_backoff_s=float(args.retry_backoff_s or 1.0),
        )
        batch_entry["end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        batch_entry["response"] = resp
        exit_code = resp.get("exit_code")
        try:
            exit_code_i = int(exit_code) if exit_code is not None else 1
        except Exception:
            exit_code_i = 1
        batch_entry["ok"] = bool(resp.get("success")) and exit_code_i == 0
        # Deterministic fallback for common truncated patch failure mode.
        try:
            results = resp.get("results") if isinstance(resp.get("results"), list) else []
            server_run_id = str(resp.get("run_id") or "").strip()
            task_code_prefix = _safe_taskcode(f"AUTOMATION_{run_id}")
            fixed_n = 0
            for r in results:
                if not isinstance(r, dict):
                    continue
                if str(r.get("error") or "") != "apply_failed":
                    continue
                pid = str(r.get("id") or "").strip()
                ad = str(r.get("artifacts_dir") or "")
                if not pid or not ad:
                    continue
                fb = _maybe_fallback_contract_harden(
                    repo_root=repo_root,
                    parent_id=pid,
                    parent_artifacts_dir=Path(ad).resolve(),
                    area=str(args.area).strip() or "control_plane",
                    task_code_prefix=task_code_prefix,
                    allow=bool(args.fallback_contract_harden),
                )
                if fb.get("attempted") or fb.get("ran") or fb.get("reason"):
                    fb["automation_run_id"] = run_id
                    fb["codex_server_run_id"] = server_run_id or None
                    fb["batch_name"] = name
                    manifest["fallbacks"].append(fb)
                    _write_json(out_dir / "automation_manifest.json", manifest)
                # If deterministic harden succeeded, treat this parent as recovered.
                if bool(fb.get("ran")) and int(fb.get("exit_code") or 1) == 0:
                    files = fb.get("patch_files") if isinstance(fb.get("patch_files"), list) else []
                    ok2, errs2 = _contract_files_smoke(repo_root=repo_root, files=[str(x) for x in files if str(x).strip()])
                    fb["post_smoke_ok"] = ok2
                    try:
                        _write_json(out_dir / "automation_manifest.json", manifest)
                    except Exception:
                        pass
                    if not ok2:
                        fb["post_smoke_errors"] = errs2[:20]
                        try:
                            _write_json(out_dir / "automation_manifest.json", manifest)
                        except Exception:
                            pass
                    else:
                        r["error"] = ""
                        r["exit_code"] = 0
                        r["fallback_override"] = {"kind": "contract_harden", "taskcode": str(fb.get("taskcode") or "")}
                        se = r.get("scope_enforcement")
                        if isinstance(se, dict):
                            se["apply_ok"] = True
                            se["apply_error"] = ""
                        fixed_n += 1

            # Recompute batch ok after fallbacks (client-side final verdict).
            def _results_all_ok(rs: list) -> bool:
                if not rs:
                    return False
                for rr in rs:
                    if not isinstance(rr, dict):
                        return False
                    if str(rr.get("error") or "").strip():
                        return False
                    try:
                        if int(rr.get("exit_code") or 0) != 0:
                            return False
                    except Exception:
                        return False
                return True

            all_ok = _results_all_ok(results)
            if all_ok:
                resp["success"] = True
                resp["exit_code"] = 0
                batch_entry["ok"] = True
            else:
                resp["success"] = bool(resp.get("success")) and False
            # Ensure the response snapshot reflects fallback-rewritten results.
            batch_entry["response"] = resp
        except Exception:
            try:
                manifest.setdefault("warnings", []).append({"kind": "fallback_exception", "batch": name})
                _write_json(out_dir / "automation_manifest.json", manifest)
            except Exception:
                pass
        manifest["batches"].append({k: batch_entry.get(k) for k in ("name", "start_utc", "end_utc", "ok")})
        _write_json(out_dir / f"{bi:02d}__{name}__response.json", batch_entry)
        _write_json(out_dir / "automation_manifest.json", manifest)

    manifest["ok"] = all(b.get("ok") for b in manifest.get("batches") or []) if (manifest.get("batches") is not None) else False
    manifest["end_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _write_json(out_dir / "automation_manifest.json", manifest)
    print(f"[automation] done run_id={run_id} out_dir={out_dir}")
    return 0 if manifest["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
