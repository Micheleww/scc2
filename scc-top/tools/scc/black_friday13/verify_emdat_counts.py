#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify EM-DAT count analysis outputs exist and are consistent.")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/emdat_counts_A")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    required = [
        "overview.json",
        "groups.csv",
        "glm__f13_only.csv",
        "glm__dow_dom.csv",
        "glm__dow_dom_month_year_plus_f13.csv",
        "good_bad_dow_dom.csv",
        "models.json",
        "report.md",
    ]
    missing = [p for p in required if not (out_dir / p).exists()]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_outputs", "missing": missing}, ensure_ascii=False, indent=2))
        return 2

    combo = pd.read_csv(out_dir / "good_bad_dow_dom.csv")
    if "is_friday_13" not in combo.columns or combo["is_friday_13"].sum() != 1:
        print(json.dumps({"ok": False, "error": "friday13_flag_missing_or_not_unique"}, ensure_ascii=False, indent=2))
        return 3

    f13 = combo[combo["is_friday_13"]].iloc[0].to_dict()
    ok = True
    checks = {
        "combos": int(len(combo)),
        "f13_row": {"dow": int(f13.get("dow")), "dom": int(f13.get("dom")), "p": float(f13.get("p_poisson_vs_global")), "q": float(f13.get("q_fdr"))},
    }
    if checks["combos"] < 200:
        ok = False
        checks["combos_ok"] = False
    else:
        checks["combos_ok"] = True

    print(json.dumps({"ok": ok, "checks": checks}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
