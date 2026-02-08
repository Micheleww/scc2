#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Scan Hook Runner

Runs a configured list of deterministic scan/audit scripts as a hook.
Designed to be safe: no network, no LLM, and no destructive actions by default.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _match_report(report_path: Path, patterns: List[str]) -> bool:
    if not patterns:
        return True
    text = _read_text(report_path)
    target = (str(report_path) + "\n" + text[:4000]).lower()
    return any(str(p).lower() in target for p in patterns if str(p).strip())


def _norm_rel(repo_root: Path, path_str: str) -> str:
    try:
        return str(Path(path_str).resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except Exception:
        return str(path_str).replace("\\", "/")


def _extract_report_paths(output: str, repo_root: Path) -> List[str]:
    hits: List[str] = []
    pattern = re.compile(r"(report_(?:md|json)|report)\s*=\s*([^\s]+)", re.IGNORECASE)
    for line in (output or "").splitlines():
        m = pattern.search(line)
        if not m:
            continue
        raw = m.group(2).strip().strip('"').strip("'")
        hits.append(_norm_rel(repo_root, raw))
    return sorted({h for h in hits if h})


def _tail(text: str, limit: int = 12) -> str:
    lines = (text or "").splitlines()
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[-limit:])


def _run_scan(
    *,
    repo_root: Path,
    scan: Dict[str, Any],
    apply: bool,
) -> Dict[str, Any]:
    name = str(scan.get("name") or "scan")
    script = str(scan.get("script") or "")
    args = [str(x) for x in (scan.get("args") or []) if str(x).strip()]
    timeout_sec = int(scan.get("timeout_sec") or 60)
    allow_apply = bool(scan.get("allow_apply", False))

    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = (repo_root / script_path).resolve()

    cmd = [sys.executable, str(script_path), *args]
    if apply and allow_apply:
        cmd.append("--apply")

    started = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
        rc = int(proc.returncode)
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
    except Exception as e:
        rc = 1
        stdout = ""
        stderr = str(e)
    duration = time.time() - started

    report_paths = _extract_report_paths(stdout + "\n" + stderr, repo_root)
    return {
        "name": name,
        "script": _norm_rel(repo_root, str(script_path)),
        "args": args,
        "return_code": rc,
        "duration_sec": round(duration, 2),
        "report_paths": report_paths,
        "stdout_tail": _tail(stdout),
        "stderr_tail": _tail(stderr),
    }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run scan hooks from config")
    ap.add_argument("--config", default="")
    ap.add_argument("--report-path", default="")
    ap.add_argument("--trigger", default="report", choices=["report", "manual"])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-scans", type=int, default=0)
    args = ap.parse_args()

    repo_root = _repo_root()
    default_cfg = repo_root / "tools" / "scc" / "ops" / "scan_hook_config.json"
    cfg_path = Path(args.config) if str(args.config or "").strip() else default_cfg
    if not cfg_path.is_absolute():
        cfg_path = (repo_root / cfg_path).resolve()

    cfg = _load_config(cfg_path)
    if not cfg or bool(cfg.get("enabled", False)) is False:
        print("[scan_hook] config disabled; skip.")
        return 0

    if args.trigger == "report" and not bool(cfg.get("on_report", True)):
        print("[scan_hook] on_report disabled; skip.")
        return 0

    report_path = Path(str(args.report_path)).resolve() if str(args.report_path or "").strip() else None
    if report_path and report_path.exists():
        patterns = cfg.get("match") or []
        if not _match_report(report_path, patterns):
            print("[scan_hook] report does not match patterns; skip.")
            return 0

    scans = [s for s in (cfg.get("scans") or []) if bool(s.get("enabled", True))]
    if not scans:
        print("[scan_hook] no scans configured; skip.")
        return 0

    max_scans = int(args.max_scans or 0)
    if not max_scans and isinstance(cfg.get("max_scans"), int):
        max_scans = int(cfg.get("max_scans") or 0)
    if max_scans > 0:
        scans = scans[:max_scans]

    results: List[Dict[str, Any]] = []
    for scan in scans:
        results.append(_run_scan(repo_root=repo_root, scan=scan, apply=bool(args.apply)))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    report_dir = Path(str(cfg.get("report_dir") or "docs/REPORT/control_plane"))
    if not report_dir.is_absolute():
        report_dir = (repo_root / report_dir).resolve()
    artifacts_root = Path(str(cfg.get("artifacts_dir") or "docs/REPORT/control_plane/artifacts/SCAN_HOOK"))
    if not artifacts_root.is_absolute():
        artifacts_root = (repo_root / artifacts_root).resolve()
    run_dir = artifacts_root / stamp

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "trigger": str(args.trigger),
        "report_path": _norm_rel(repo_root, str(report_path)) if report_path else "",
        "config_path": _norm_rel(repo_root, str(cfg_path)),
        "scans_total": len(results),
        "scans_failed": len([r for r in results if int(r.get("return_code", 1)) != 0]),
        "results": results,
    }
    _write_json(run_dir / "scan_hook_results.json", payload)

    ok = len(results) - int(payload["scans_failed"])
    md_lines: List[str] = []
    md_lines.append(f"# Scan Hook Report ({stamp})")
    md_lines.append("")
    md_lines.append(f"- Generated at (UTC): {payload['generated_at_utc']}")
    md_lines.append(f"- Trigger: {payload['trigger']}")
    if payload["report_path"]:
        md_lines.append(f"- Source report: {payload['report_path']}")
    md_lines.append(f"- Config: {payload['config_path']}")
    md_lines.append(f"- Scans total: {payload['scans_total']}")
    md_lines.append(f"- Scans ok: {ok}")
    md_lines.append(f"- Scans failed: {payload['scans_failed']}")
    md_lines.append(f"- Results JSON: { _norm_rel(repo_root, str((run_dir / 'scan_hook_results.json').resolve())) }")
    md_lines.append("")

    for r in results:
        md_lines.append(f"## Scan: {r.get('name')}")
        md_lines.append(f"- Script: {r.get('script')}")
        md_lines.append(f"- Args: {' '.join(r.get('args') or [])}")
        md_lines.append(f"- Return code: {r.get('return_code')}")
        md_lines.append(f"- Duration: {r.get('duration_sec')}s")
        if r.get("report_paths"):
            md_lines.append(f"- Reports: {'; '.join(r.get('report_paths'))}")
        if r.get("stderr_tail"):
            md_lines.append("- Stderr (tail):")
            md_lines.append("```")
            md_lines.append(str(r.get("stderr_tail")))
            md_lines.append("```")
        elif r.get("stdout_tail"):
            md_lines.append("- Stdout (tail):")
            md_lines.append("```")
            md_lines.append(str(r.get("stdout_tail")))
            md_lines.append("```")
        md_lines.append("")

    report_path = report_dir / f"REPORT__SCAN_HOOK__{stamp}.md"
    _write_text(report_path, "\n".join(md_lines).strip() + "\n")

    print(f"[scan_hook] report={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
