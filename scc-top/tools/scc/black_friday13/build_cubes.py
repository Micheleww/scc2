#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build (dow,dom)->value cubes for visualization.")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/cubes")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    # Part 1 cube: EM-DAT daily rate by (dow, dom) in main display A.
    em = pd.read_csv("artifacts/black_friday13/emdat_counts_A/good_bad_dow_dom.csv")
    em_out = em[["dow", "dom", "days", "events", "rate", "p_poisson_vs_global", "q_fdr", "is_friday_13"]].copy()
    em_out.to_csv(out_dir / "cube_emdat_rate__post2000_natural_drop.csv", index=False, encoding="utf-8")
    em_pivot = em_out.pivot(index="dow", columns="dom", values="rate").sort_index()
    em_pivot.to_csv(out_dir / "cube_emdat_rate__post2000_natural_drop__pivot.csv", encoding="utf-8")

    # Part 2 cube: mean U_t by (dow, dom) in the overlap window.
    u = pd.read_parquet("artifacts/black_friday13/luck_index_world_td/luck_index_daily.parquet")
    u["dow"] = u["dow"].astype(int)
    u["dom"] = u["dom"].astype(int)
    g = u.groupby(["dow", "dom"], as_index=False).agg(days=("U_t", "count"), mean_U_t=("U_t", "mean"), median_U_t=("U_t", "median"))
    g["is_friday_13"] = (g["dow"] == 4) & (g["dom"] == 13)
    g.to_csv(out_dir / "cube_U_t_mean__world_overlap.csv", index=False, encoding="utf-8")
    g.pivot(index="dow", columns="dom", values="mean_U_t").sort_index().to_csv(out_dir / "cube_U_t_mean__world_overlap__pivot.csv", encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

