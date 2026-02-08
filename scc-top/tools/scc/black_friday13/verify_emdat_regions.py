#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify regional appendix outputs exist and have expected schema.")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/emdat_region_appendix_post2000")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    required = ["overview.json", "region_f13_tests.csv", "subregion_f13_tests.csv", "report.md"]
    missing = [p for p in required if not (out_dir / p).exists()]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_outputs", "missing": missing}, ensure_ascii=False, indent=2))
        return 2

    reg = pd.read_csv(out_dir / "region_f13_tests.csv")
    sub = pd.read_csv(out_dir / "subregion_f13_tests.csv")
    for df, name in [(reg, "region"), (sub, "subregion")]:
        if len(df) < 3:
            print(json.dumps({"ok": False, "error": "too_few_groups", "table": name, "groups": int(len(df))}, ensure_ascii=False, indent=2))
            return 3
        needed_cols = {"group", "m1_irr", "m1_p", "m1_q_fdr", "total_events"}
        if not needed_cols.issubset(set(df.columns)):
            print(json.dumps({"ok": False, "error": "schema_mismatch", "table": name, "missing_cols": sorted(needed_cols - set(df.columns))}, ensure_ascii=False, indent=2))
            return 4
        if "p_poisson_f13_vs_global" not in df.columns or "q_poisson_fdr" not in df.columns:
            print(json.dumps({"ok": False, "error": "missing_poisson_columns", "table": name}, ensure_ascii=False, indent=2))
            return 5

    print(json.dumps({"ok": True, "checks": {"regions": int(len(reg)), "subregions": int(len(sub))}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
