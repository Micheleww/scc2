#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_task_json(task_id: str, contract_ref: str) -> None:
    task_dir = (_REPO_ROOT / "artifacts" / "scc_tasks" / task_id).resolve()
    task_dir.mkdir(parents=True, exist_ok=True)
    task_json = task_dir / "task.json"
    rec = {
        "task_id": task_id,
        "created_utc": None,
        "updated_utc": None,
        "status": "queued",
        "request": {"source": "system", "contract_ref": contract_ref, "evidence_refs": []},
        "run_id": None,
        "exit_code": None,
        "verdict": None,
        "out_dir": None,
        "selftest_log": None,
        "report_md": None,
        "evidence_dir": None,
        "error": None,
    }
    task_json.write_text(json.dumps(rec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser(description="Create+run SCC contract for EM-DAT regional appendix (post2000, Natural, drop).")
    ap.add_argument("--task-id", default="BLACK_FRIDAY13_EMDAT_REGION_APPENDIX_V010")
    ap.add_argument("--contract-ref", default="docs/ssot/04_contracts/black_friday13/contract_black_friday13_emdat_region_appendix_v010.json")
    ap.add_argument("--area", default="control_plane")
    args = ap.parse_args()

    emdat = _REPO_ROOT / "artifacts" / "black_friday13" / "ingest" / "emdat_events.parquet"
    base = _REPO_ROOT / "artifacts" / "black_friday13" / "ingest" / "panel__natural__drop__post2000.parquet"
    if not emdat.exists() or not base.exists():
        raise SystemExit("Missing ingest outputs. Run tools/scc/black_friday13/run_ingest_task.py first.")

    _write_task_json(str(args.task_id), str(args.contract_ref).replace("\\", "/"))
    cmd = ["python", "tools/scc/ops/run_contract_task.py", "--task-id", str(args.task_id), "--area", str(args.area)]
    p = subprocess.run(cmd, cwd=str(_REPO_ROOT), env=dict(os.environ))
    return int(p.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

