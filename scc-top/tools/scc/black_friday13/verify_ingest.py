#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify black_friday13 ingest outputs exist and are non-empty.")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/ingest")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    if not out_dir.exists():
        print(json.dumps({"ok": False, "error": "out_dir_missing", "out_dir": str(out_dir)}, ensure_ascii=False))
        return 2

    required = [
        "emdat_events.parquet",
        "owid_world_daily.parquet",
        "owid_world_row_daily.parquet",
        "calendar_daily.parquet",
        "summary.json",
        "panel__natural__drop.parquet",
        "panel__natural__uniform_month.parquet",
        "panel__nat_tech__drop.parquet",
        "panel__nat_tech__uniform_month.parquet",
    ]
    missing = [p for p in required if not (out_dir / p).exists()]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_outputs", "missing": missing}, ensure_ascii=False, indent=2))
        return 3

    # Light sanity checks.
    em = pd.read_parquet(out_dir / "emdat_events.parquet", columns=["disno", "disaster_group", "start_year", "start_month", "start_day"])
    ow = pd.read_parquet(out_dir / "owid_world_daily.parquet", columns=["day", "new_deaths", "new_deaths_per_million"])
    cal = pd.read_parquet(out_dir / "calendar_daily.parquet", columns=["day", "is_friday_13"])
    panel = pd.read_parquet(out_dir / "panel__natural__drop.parquet", columns=["day", "emdat_event_count", "new_deaths", "is_friday_13"])

    ok = True
    checks = {}
    checks["emdat_rows"] = int(len(em))
    checks["emdat_unique_disno"] = int(em["disno"].nunique())
    checks["owid_rows"] = int(len(ow))
    checks["calendar_days"] = int(len(cal))
    checks["panel_days"] = int(len(panel))
    checks["calendar_friday13_days"] = int(cal["is_friday_13"].sum())
    checks["owid_nonzero_new_deaths_days"] = int((ow["new_deaths"].fillna(0.0) > 0).sum())
    checks["owid_max_new_deaths_per_million"] = float(ow["new_deaths_per_million"].max()) if "new_deaths_per_million" in ow.columns else None

    if checks["emdat_rows"] <= 0 or checks["emdat_unique_disno"] <= 0:
        ok = False
        checks["emdat_nonempty"] = False
    else:
        checks["emdat_nonempty"] = True

    if checks["owid_rows"] <= 0:
        ok = False
        checks["owid_nonempty"] = False
    else:
        checks["owid_nonempty"] = True
    if checks["owid_nonzero_new_deaths_days"] <= 50:
        ok = False
        checks["owid_daily_density_ok"] = False
    else:
        checks["owid_daily_density_ok"] = True

    if checks["calendar_days"] <= 0 or checks["panel_days"] <= 0:
        ok = False

    # Friday-13 count should be > 0 in any multi-year calendar.
    if checks["calendar_friday13_days"] <= 0:
        ok = False

    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
