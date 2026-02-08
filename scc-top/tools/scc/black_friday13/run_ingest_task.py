#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple


_REPO_ROOT = Path(__file__).resolve().parents[3]


def _find_default_inputs() -> Tuple[Optional[Path], Optional[Path]]:
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop" / "immc dataset"
    if not desktop.exists():
        return None, None

    emdat = None
    # Common naming patterns in EM-DAT downloads/copies.
    for pat in ("*public_emdat_incl_hist*.xlsx", "*emdat*incl*hist*.xlsx", "*emdat*.xlsx"):
        xs = sorted(desktop.glob(pat), key=lambda p: p.stat().st_mtime, reverse=True)
        if xs:
            emdat = xs[0]
            break

    owid = None
    for p in desktop.rglob("owid-covid-data.csv"):
        owid = p
        break

    return emdat, owid


def _write_task_json(task_id: str, contract_ref: str) -> Path:
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
    return task_json


def main() -> int:
    ap = argparse.ArgumentParser(description="Create+run SCC contract task for black_friday13 ingest (EM-DAT + OWID).")
    ap.add_argument("--task-id", default="BLACK_FRIDAY13_INGEST_V010")
    ap.add_argument("--contract-ref", default="docs/ssot/04_contracts/black_friday13/contract_black_friday13_ingest_v010.json")
    ap.add_argument("--emdat-xlsx", default="", help="Override EM-DAT XLSX path (otherwise auto-detect under Desktop/immc dataset).")
    ap.add_argument("--owid-csv", default="", help="Override OWID CSV path (otherwise auto-detect under Desktop/immc dataset).")
    ap.add_argument("--area", default="control_plane")
    args = ap.parse_args()

    emdat = Path(args.emdat_xlsx).expanduser() if args.emdat_xlsx else None
    owid = Path(args.owid_csv).expanduser() if args.owid_csv else None
    if not emdat or not owid:
        d_emdat, d_owid = _find_default_inputs()
        emdat = emdat or d_emdat
        owid = owid or d_owid

    if not emdat or not emdat.exists():
        raise SystemExit("EM-DAT XLSX not found. Pass --emdat-xlsx, or put it under Desktop/immc dataset.")
    if not owid or not owid.exists():
        raise SystemExit("OWID CSV not found. Pass --owid-csv, or put it under Desktop/immc dataset (owid-covid-data.csv).")

    _write_task_json(str(args.task_id), str(args.contract_ref).replace("\\", "/"))

    env = dict(os.environ)
    env["BF13_EMDAT_XLSX"] = str(emdat)
    env["BF13_OWID_CSV"] = str(owid)

    cmd = [
        "python",
        "tools/scc/ops/run_contract_task.py",
        "--task-id",
        str(args.task_id),
        "--area",
        str(args.area),
    ]
    p = subprocess.run(cmd, cwd=str(_REPO_ROOT), env=env)
    return int(p.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

