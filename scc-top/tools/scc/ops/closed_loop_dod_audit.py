#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_json(path: Path) -> Any:
    return json.loads(_read_text(path) or "null")


def _exists(rel: str) -> bool:
    return (REPO_ROOT / rel).resolve().exists()


def _frontmatter_oid(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    lines = _read_text(path).splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for i in range(1, min(len(lines), 200)):
        if lines[i].strip() == "---":
            break
        if lines[i].lower().startswith("oid:"):
            return lines[i].split(":", 1)[1].strip()
    return ""


def _iter_tasks(tree: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
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
                if isinstance(t, dict):
                    out.append(t)
    return out


def _latest_file_under(path: Path) -> str:
    if not path.exists():
        return ""
    best: Tuple[float, str] = (0.0, "")
    for p in path.rglob("*"):
        if not p.is_file():
            continue
        mt = p.stat().st_mtime
        if mt > best[0]:
            try:
                rel = str(p.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
            except Exception:
                rel = str(p).replace("\\", "/")
            best = (mt, rel)
    return best[1]


def main() -> int:
    ap = argparse.ArgumentParser(description="Closed-loop DoD audit (v0.1.0) — evaluates SCC_TOP closure against minimum autonomy criteria.")
    ap.add_argument("--taskcode", default="CLOSED_LOOP_DOD_AUDIT_V010")
    ap.add_argument("--area", default="control_plane")
    ap.add_argument("--task-tree", default="docs/DERIVED/task_tree.json")
    ap.add_argument("--run-oid-validator", action="store_true", help="Run oid_validator as part of audit (requires SCC_OID_PG_DSN + PGPASSWORD).")
    args = ap.parse_args()

    taskcode = str(args.taskcode).strip() or "CLOSED_LOOP_DOD_AUDIT_V010"
    area = str(args.area).strip() or "control_plane"

    env = dict(os.environ)
    env["TASK_CODE"] = taskcode
    env["AREA"] = area

    artifacts_dir = (REPO_ROOT / "docs" / "REPORT" / area / "artifacts" / taskcode).resolve()
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    registry_path = (REPO_ROOT / "docs" / "ssot" / "registry.json").resolve()
    reg = _read_json(registry_path) if registry_path.exists() else {}
    default_order = []
    try:
        default_order = reg.get("context_assembly", {}).get("default_order", [])  # type: ignore[assignment]
    except Exception:
        default_order = []

    required_chain = [
        "docs/ssot/02_architecture/SCC_TOP.md",
        "docs/ssot/02_architecture/canonical_truth.md",
        "docs/ssot/04_contracts/task_model.md",
        "docs/ssot/04_contracts/contract_min_spec.md",
        "docs/ssot/05_runbooks/execution_verification_interfaces.md",
        "docs/ssot/05_runbooks/review_progress.md",
        "docs/ssot/05_runbooks/metrics_spec.md",
    ]

    # A) Authority chain
    a = {
        "entrypoint_ok": _exists("docs/START_HERE.md") and _exists("docs/ssot/START_HERE.md"),
        "registry_ok": _exists("docs/ssot/registry.json") or _exists("docs/ssot/_registry.json"),
        "required_chain_present": {p: _exists(p) for p in required_chain},
        "registry_order_has_top": bool(default_order) and any("SCC_TOP.md" in str(x) for x in (default_order or [])),
    }

    # B) Canonical set presence + inline oids
    canonical_docs = [
        "docs/CANONICAL/GOALS.md",
        "docs/CANONICAL/ROADMAP.md",
        "docs/CANONICAL/CURRENT_STATE.md",
        "docs/CANONICAL/PROGRESS.md",
    ]
    adr_dir = (REPO_ROOT / "docs" / "CANONICAL" / "ADR").resolve()
    b = {
        "canonical_docs_present": {p: _exists(p) for p in canonical_docs},
        "canonical_docs_oid_inline": {p: _frontmatter_oid((REPO_ROOT / p).resolve()) for p in canonical_docs},
        "adr_dir_present": adr_dir.exists(),
    }

    # C) Task tree basic structure + contract linkage coverage
    tree_path = (Path(args.task_tree) if Path(args.task_tree).is_absolute() else (REPO_ROOT / args.task_tree)).resolve()
    tree = _read_json(tree_path) if tree_path.exists() else {}
    tasks = _iter_tasks(tree if isinstance(tree, dict) else {})
    with_contract_ref = [t for t in tasks if str(t.get("contract_ref") or "").strip()]
    c = {
        "task_tree_present": tree_path.exists(),
        "epics_count": len((tree.get("epics") or [])) if isinstance(tree, dict) else 0,
        "tasks_total": len(tasks),
        "tasks_with_contract_ref": len(with_contract_ref),
    }

    # D) Contract schema + examples
    d = {
        "contract_schema_present": _exists("docs/ssot/04_contracts/contract.schema.json"),
        "contract_examples_dir_present": _exists("docs/ssot/04_contracts/examples"),
    }

    # E) Exec/Verify interface docs + CI hard gate (phase4 check includes oid-validator)
    phase4_path = (REPO_ROOT / "tools" / "ci" / "run_phase4_checks.py").resolve()
    phase4_text = _read_text(phase4_path) if phase4_path.exists() else ""
    e = {
        "interfaces_doc_present": _exists("docs/ssot/05_runbooks/execution_verification_interfaces.md"),
        "phase4_includes_oid_validator": "run_oid_validator_check" in phase4_text and "oid-validator" in phase4_text,
    }

    # F) Review loop outputs: progress + raw-b
    rawb_dir = (REPO_ROOT / "docs" / "INPUTS" / "raw-b").resolve()
    f = {
        "progress_doc_present": _exists("docs/CANONICAL/PROGRESS.md"),
        "rawb_dir_present": rawb_dir.exists(),
        "rawb_latest": _latest_file_under(rawb_dir),
    }

    oid_validator_rc = None
    oid_validator_report = ""
    if bool(args.run_oid_validator):
        p = subprocess.run(
            [sys.executable, "tools/scc/ops/oid_validator.py", "--report-dir", str(artifacts_dir)],
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        oid_validator_rc = int(p.returncode)
        # find newest report emitted into artifacts_dir
        reports = sorted(artifacts_dir.glob("oid_validator__*.md"))
        if reports:
            oid_validator_report = str(reports[-1].resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")

    payload = {
        "schema_version": "v0.1.0",
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "taskcode": taskcode,
        "area": area,
        "A_authority": a,
        "B_canonical_truth": b,
        "C_task_model": c,
        "D_contracts": d,
        "E_exec_verify_gate": e,
        "F_review_feedback": f,
        "oid_validator": {"ran": bool(args.run_oid_validator), "rc": oid_validator_rc, "report": oid_validator_report},
    }
    (artifacts_dir / "dod_audit_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        errors="replace",
    )

    evidence = [f"docs/REPORT/{area}/artifacts/{taskcode}/dod_audit_summary.json"]
    if oid_validator_report:
        evidence.append(oid_validator_report)

    subprocess.run(
        [
            sys.executable,
            "tools/scc/ops/evidence_triplet.py",
            "--taskcode",
            taskcode,
            "--area",
            area,
            "--exit-code",
            "0",
            "--notes",
            "\n".join(
                [
                    "- This audit is informational: it reports closure status and gaps against the minimum autonomy DoD.",
                    "- For fail-closed enforcement, rely on CI/verdict (phase4 checks + mvm-verdict).",
                ]
            ),
            *sum([["--evidence", p] for p in evidence], []),
        ],
        cwd=str(REPO_ROOT),
        env=env,
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
