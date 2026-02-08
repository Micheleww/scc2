#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _date_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _write_text(path: Path, s: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(s, encoding="utf-8", errors="replace")


def _to_repo_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _safe_filename(s: str, *, max_len: int = 120) -> str:
    s = (s or "").strip()
    if not s:
        return "task"
    s = s.replace(":", "_").replace("/", "_").replace("\\", "_")
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "task"
    if len(s) > max_len:
        s = s[:max_len].rstrip("_")
    return s


@dataclass
class TaskLeaf:
    epic_id: str
    epic_title: str
    capability_id: str
    capability_title: str
    task_id: str
    task_label: str
    evidence_refs: List[str]
    source_anchor: str


def _extract_tasks(tree: Dict[str, Any]) -> List[TaskLeaf]:
    out: List[TaskLeaf] = []
    epics = tree.get("epics") if isinstance(tree.get("epics"), list) else []
    for e in epics:
        if not isinstance(e, dict):
            continue
        epic_id = str(e.get("epic_id") or "").strip()
        epic_title = str(e.get("title") or "").strip()
        caps = e.get("capabilities") if isinstance(e.get("capabilities"), list) else []
        for c in caps:
            if not isinstance(c, dict):
                continue
            cap_id = str(c.get("capability_id") or "").strip()
            cap_title = str(c.get("title") or "").strip()
            tasks = c.get("tasks") if isinstance(c.get("tasks"), list) else []
            for t in tasks:
                if not isinstance(t, dict):
                    continue
                task_id = str(t.get("task_id") or "").strip()
                task_label = str(t.get("task_label") or "").strip()
                evidence_refs = t.get("evidence_refs") if isinstance(t.get("evidence_refs"), list) else []
                evidence_refs = [str(x).strip() for x in evidence_refs if str(x).strip()]
                source_anchor = str(t.get("source_anchor") or "").strip()
                if not task_id:
                    continue
                out.append(
                    TaskLeaf(
                        epic_id=epic_id,
                        epic_title=epic_title,
                        capability_id=cap_id,
                        capability_title=cap_title,
                        task_id=task_id,
                        task_label=task_label,
                        evidence_refs=evidence_refs,
                        source_anchor=source_anchor,
                    )
                )
    return out


def _artifacts_dir(area: str, task_code: str) -> Path:
    return (_REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / task_code).resolve()


def _report_path(area: str, task_code: str) -> Path:
    return (_REPO_ROOT / "docs" / "REPORT" / area / f"REPORT__{task_code}__{_date_utc()}.md").resolve()


def _run(cmd: List[str], *, cwd: Optional[Path] = None, env: Optional[dict] = None, timeout_s: int = 180) -> Tuple[int, str, str]:
    p = subprocess.run(
        cmd,
        cwd=str(cwd or _REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    return int(p.returncode), (p.stdout or ""), (p.stderr or "")


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
    ap = argparse.ArgumentParser(description="Contractize job: task_tree.json -> per-task contract JSONs (v0.1.0)")
    ap.add_argument("--task-tree", default="docs/DERIVED/task_tree.json")
    ap.add_argument("--out-dir", default="docs/ssot/04_contracts/generated")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--taskcode", default="CONTRACTIZE_PIPELINE_V010")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of tasks to contractize (0 = all).")
    ap.add_argument("--update-task-tree", action="store_true", help="Write back contract_ref paths into task_tree.json")
    ap.add_argument("--run-mvm", action="store_true", help="Run mvm-verdict basic at the end")
    args = ap.parse_args()

    area = str(args.area).strip() or "control_plane"
    task_code = str(args.taskcode).strip() or "CONTRACTIZE_PIPELINE_V010"
    artifacts = _artifacts_dir(area, task_code)
    artifacts.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    env["TASK_CODE"] = task_code
    env["AREA"] = area

    tree_path = Path(args.task_tree)
    if not tree_path.is_absolute():
        tree_path = (_REPO_ROOT / tree_path).resolve()
    if not tree_path.exists():
        _write_json(artifacts / "contractize_summary.json", {"ok": False, "error": "missing_task_tree", "task_tree": _to_repo_rel(tree_path)})
        subprocess.run(
            [
                sys.executable,
                "tools/scc/ops/evidence_triplet.py",
                "--taskcode",
                task_code,
                "--area",
                area,
                "--exit-code",
                "1",
                "--notes",
                f"- error: missing_task_tree\\n- task_tree: `{_to_repo_rel(tree_path)}`",
                "--evidence",
                f"docs/REPORT/{area}/artifacts/{task_code}/contractize_summary.json",
            ],
            cwd=str(_REPO_ROOT),
            env=env,
        )
        return 1

    tree = _read_json(tree_path)
    tasks = _extract_tasks(tree)
    limit = int(args.limit or 0)
    if limit > 0:
        tasks = tasks[:limit]

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = (_REPO_ROOT / out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    generated: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    hint = f"contractize_job:{task_code}"

    for t in tasks:
        fname = _safe_filename(t.task_id) + ".json"
        contract_path = (out_dir / fname).resolve()
        rel_contract_path = _to_repo_rel(contract_path)

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
                "task_id": t.task_id,
                "contract_id": f"contractize:{t.task_id}",
                "goal": t.task_label or f"Task {t.task_id}",
                "scope_allow": "TBD (must be set by planner/manager before execution)",
                "constraints": "Fail-closed. Must stay within allowlist scope. Do not create a second docs entrypoint.",
                "acceptance": {
                    "checks": [
                        {
                            "name": "acceptance_tbd_blocker",
                            "command": "python -c \"import sys; print('TBD acceptance (blocked): contract must be hardened and acceptance checks defined'); sys.exit(2)\"",
                        }
                    ]
                },
                "stop_condition": "If acceptance cannot be executed or violates scope_allow, stop and report.",
                "commands_hint": "Use SSOT registry for deterministic context; minimize file scanning; prefer allowlisted edits.",
                "inputs_ref": {
                    "paths": [p for p in t.evidence_refs],
                    "oids": [],
                },
                "outputs_expected": {
                    "verdict_required": True,
                    "evidence_paths": [f"docs/REPORT/{area}/artifacts/{t.task_id}/*"],
                },
                "task_tree_ref": _to_repo_rel(tree_path),
                "epic": {"id": t.epic_id, "title": t.epic_title},
                "capability": {"id": t.capability_id, "title": t.capability_title},
                "source_anchor": t.source_anchor,
            }

            _write_json(contract_path, contract)
            generated.append({"task_id": t.task_id, "contract_path": rel_contract_path, "oid": oid})
        except Exception as e:
            errors.append({"task_id": t.task_id, "error": str(e)})

    # Optionally write back contract_ref into the tree (derived file).
    if args.update_task_tree and not errors:
        try:
            for e in tree.get("epics", []) if isinstance(tree.get("epics"), list) else []:
                if not isinstance(e, dict):
                    continue
                for c in e.get("capabilities", []) if isinstance(e.get("capabilities"), list) else []:
                    if not isinstance(c, dict):
                        continue
                    for t in c.get("tasks", []) if isinstance(c.get("tasks"), list) else []:
                        if not isinstance(t, dict):
                            continue
                        tid = str(t.get("task_id") or "").strip()
                        if not tid:
                            continue
                        match = next((g for g in generated if g.get("task_id") == tid), None)
                        if match:
                            t["contract_ref"] = str(match.get("contract_path"))
            _write_json(tree_path, tree)
        except Exception as e:
            errors.append({"task_id": "-", "error": f"update_task_tree_failed: {e}"})

    # Pre-run validators so the report can reference them (guard runs before mvm-verdict validators).
    top_rc, top_out, top_err = _run(
        [sys.executable, "tools/scc/ops/top_validator.py", "--registry", "docs/ssot/registry.json", "--out-dir", _to_repo_rel(artifacts)],
        env=env,
        timeout_s=120,
    )
    _write_text(artifacts / "top_validator_stdout.txt", top_out)
    _write_text(artifacts / "top_validator_stderr.txt", top_err)

    oid_rc, oid_out, oid_err = _run(
        [sys.executable, "tools/scc/ops/oid_validator.py", "--report-dir", _to_repo_rel(artifacts)],
        env=env,
        timeout_s=180,
    )
    _write_text(artifacts / "oid_validator_stdout.txt", oid_out)
    _write_text(artifacts / "oid_validator_stderr.txt", oid_err)

    ok = (not errors) and (top_rc == 0) and (oid_rc == 0)

    summary = {
        "ok": ok,
        "ts_utc": _iso_now(),
        "task_code": task_code,
        "area": area,
        "task_tree": _to_repo_rel(tree_path),
        "out_dir": _to_repo_rel(out_dir),
        "generated_count": len(generated),
        "error_count": len(errors),
        "generated": generated[:200],
        "errors": errors[:50],
    }
    _write_json(artifacts / "contractize_summary.json", summary)

    # Find the newest validator reports (if present).
    top_reports = sorted(artifacts.glob("top_validator__*.md"))
    oid_reports = sorted(artifacts.glob("oid_validator__*.md"))
    top_report = top_reports[-1].name if top_reports else ""
    oid_report = oid_reports[-1].name if oid_reports else ""

    # Report: only reference evidence files under artifacts dir and avoid guard_result/evidence_hashes entries.
    evidence_paths = [
        f"docs/REPORT/{area}/artifacts/{task_code}/contractize_summary.json",
        f"docs/REPORT/{area}/artifacts/{task_code}/selftest.log",
        f"docs/REPORT/{area}/artifacts/{task_code}/top_validator_stdout.txt",
        f"docs/REPORT/{area}/artifacts/{task_code}/oid_validator_stdout.txt",
    ]
    if top_report:
        evidence_paths.append(f"docs/REPORT/{area}/artifacts/{task_code}/{top_report}")
    if oid_report:
        evidence_paths.append(f"docs/REPORT/{area}/artifacts/{task_code}/{oid_report}")

    subprocess.run(
        [
            sys.executable,
            "tools/scc/ops/evidence_triplet.py",
            "--taskcode",
            task_code,
            "--area",
            area,
            "--exit-code",
            "0" if ok else "1",
            "--notes",
            "\n".join(
                [
                    f"- generated contracts dir: `{_to_repo_rel(out_dir)}`",
                    f"- task_tree: `{_to_repo_rel(tree_path)}`",
                    f"- generated_count: {len(generated)}",
                    f"- error_count: {len(errors)}",
                ]
            ),
            *sum([["--evidence", p] for p in evidence_paths], []),
        ],
        cwd=str(_REPO_ROOT),
        env=env,
    )

    if args.run_mvm:
        p = subprocess.run([sys.executable, "tools/ci/mvm-verdict.py", "--case", "basic"], cwd=str(_REPO_ROOT), env=env)
        return int(p.returncode)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
