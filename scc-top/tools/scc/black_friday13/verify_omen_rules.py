#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify omen rules outputs exist and are non-empty.")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/omen_rules_world_td")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    required = ["overview.json", "model_scores.csv", "logit_l1_top_coefs.csv", "tree_rules.txt", "holdout_predictions.parquet", "report.md"]
    missing = [p for p in required if not (out_dir / p).exists()]
    if missing:
        print(json.dumps({"ok": False, "error": "missing_outputs", "missing": missing}, ensure_ascii=False, indent=2))
        return 2

    scores = pd.read_csv(out_dir / "model_scores.csv")
    preds = pd.read_parquet(out_dir / "holdout_predictions.parquet")
    if scores.empty or preds.empty:
        print(json.dumps({"ok": False, "error": "empty_outputs"}, ensure_ascii=False, indent=2))
        return 3
    if "target" not in scores.columns or "p_bad" not in preds.columns:
        print(json.dumps({"ok": False, "error": "schema_mismatch"}, ensure_ascii=False, indent=2))
        return 4

    print(json.dumps({"ok": True, "checks": {"targets": scores["target"].nunique(), "pred_rows": int(len(preds))}}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

