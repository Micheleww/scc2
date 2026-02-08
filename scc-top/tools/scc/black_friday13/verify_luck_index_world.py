#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify luck index outputs exist and are non-empty.")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/luck_index_world_td")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    required = [
        "overview.json",
        "means_by_friday13.csv",
        "ols__U_t__f13_only.csv",
        "ols__U_t__controls_plus_f13.csv",
        "bad_day_fisher.csv",
        "U_t_by_dow.csv",
        "U_t_by_dom.csv",
        "luck_index_daily.parquet",
        "report.md",
    ]
    missing = [p for p in required if not (out_dir / p).exists()]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_outputs", "missing": missing}, ensure_ascii=False, indent=2))
        return 2

    d = pd.read_parquet(out_dir / "luck_index_daily.parquet")
    if len(d) < 300:
        print(json.dumps({"ok": False, "error": "too_few_days", "days": int(len(d))}, ensure_ascii=False, indent=2))
        return 3
    if "is_friday_13" not in d.columns or int(d["is_friday_13"].sum()) <= 0:
        print(json.dumps({"ok": False, "error": "missing_friday13_days"}, ensure_ascii=False, indent=2))
        return 4
    if "U_t" not in d.columns or not pd.to_numeric(d["U_t"], errors="coerce").notna().any():
        print(json.dumps({"ok": False, "error": "missing_U_t_values"}, ensure_ascii=False, indent=2))
        return 5

    bad_cols = [c for c in d.columns if c.startswith("is_bad_")]
    if not bad_cols:
        print(json.dumps({"ok": False, "error": "missing_bad_flags"}, ensure_ascii=False, indent=2))
        return 6

    checks = {"days": int(len(d)), "friday13_days": int(d["is_friday_13"].sum()), "bad_cols": bad_cols}
    print(json.dumps({"ok": True, "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
