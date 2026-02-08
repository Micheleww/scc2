#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd
import scipy.stats as st
import statsmodels.formula.api as smf


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _zscore(v: np.ndarray) -> np.ndarray:
    v = v.astype(float)
    m = np.nanmean(v)
    s = np.nanstd(v, ddof=0)
    if not np.isfinite(s) or s <= 0:
        return np.zeros_like(v)
    return (v - m) / s


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Weight sweep for U_t construction (World): check sensitivity of Friday-13 conclusion.")
    ap.add_argument("--panel", default="artifacts/black_friday13/ingest/panel__natural__drop.parquet")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/luck_index_weight_sweep_world_td")
    ap.add_argument("--covid-mode", choices=["raw", "ma7"], default="ma7")
    args = ap.parse_args(list(argv) if argv is not None else None)

    panel = Path(args.panel)
    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    df = pd.read_parquet(panel, columns=["day", "year", "month", "dom", "dow", "is_friday_13", "emdat_total_deaths", "new_deaths_per_million_fill0"])
    df["day"] = pd.to_datetime(df["day"], errors="coerce")
    df = df.dropna(subset=["day"]).sort_values("day").reset_index(drop=True)

    # Focus on overlap where COVID exists (non-null in OWID from-countries series).
    mask = df["new_deaths_per_million_fill0"].notna()
    d = df[mask].copy().reset_index(drop=True)
    for c in ("year", "month", "dom", "dow"):
        d[c] = d[c].astype(int)
    d["is_friday_13"] = d["is_friday_13"].astype(bool)
    d["emdat_total_deaths"] = pd.to_numeric(d["emdat_total_deaths"], errors="coerce").fillna(0.0)
    covid_raw = pd.to_numeric(d["new_deaths_per_million_fill0"], errors="coerce").fillna(0.0).astype(float).to_numpy()
    covid_ma7 = pd.Series(covid_raw).rolling(window=7, min_periods=1).mean().to_numpy(dtype=float)
    covid = covid_ma7 if str(args.covid_mode) == "ma7" else covid_raw

    x_em = np.log1p(d["emdat_total_deaths"].to_numpy(dtype=float).clip(min=0.0))
    x_cv = np.log1p(np.clip(covid, a_min=0.0, a_max=None))
    z_em = _zscore(x_em)
    z_cv = _zscore(x_cv)

    weights = [
        ("emdat_only", 1.0, 0.0),
        ("covid_only", 0.0, 1.0),
        ("equal", 1.0, 1.0),
        ("emdat2_covid1", 2.0, 1.0),
        ("emdat1_covid2", 1.0, 2.0),
    ]

    rows: list[dict[str, Any]] = []
    for name, we, wc in weights:
        d2 = d.copy()
        d2["U_t"] = float(we) * z_em + float(wc) * z_cv
        m0 = smf.ols("U_t ~ is_friday_13", data=d2).fit(cov_type="HC0")
        m1 = smf.ols("U_t ~ C(dow) + C(dom) + C(month) + C(year) + is_friday_13", data=d2).fit(cov_type="HC0")
        b0 = float(m0.params.get("is_friday_13[T.True]", np.nan))
        p0 = float(m0.pvalues.get("is_friday_13[T.True]", np.nan))
        b1 = float(m1.params.get("is_friday_13[T.True]", np.nan))
        p1 = float(m1.pvalues.get("is_friday_13[T.True]", np.nan))
        mu_f13 = float(d2.loc[d2["is_friday_13"], "U_t"].mean())
        mu_nf13 = float(d2.loc[~d2["is_friday_13"], "U_t"].mean())
        rows.append(
            {
                "name": name,
                "w_emdat_td": float(we),
                "w_covid_deaths_pm": float(wc),
                "days": int(len(d2)),
                "friday13_days": int(d2["is_friday_13"].sum()),
                "mean_U_f13": mu_f13,
                "mean_U_non_f13": mu_nf13,
                "diff_mean": mu_f13 - mu_nf13,
                "ols_f13_only_coef": b0,
                "ols_f13_only_p": p0,
                "ols_controls_coef": b1,
                "ols_controls_p": p1,
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(out_dir / "weight_sweep.csv", index=False, encoding="utf-8")
    overview = {
        "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "panel": str(panel).replace("\\", "/"),
        "covid_mode": str(args.covid_mode),
        "window": {"min_day": str(d["day"].min().date()), "max_day": str(d["day"].max().date())},
    }
    _write_json(out_dir / "overview.json", overview)

    lines = []
    lines.append("# U_t weight sensitivity (World)")
    lines.append("")
    lines.append(f"- Window: {overview['window']['min_day']}..{overview['window']['max_day']} (COVID mode={overview['covid_mode']})")
    lines.append("- Columns: diff_mean = mean(U_t|F13) - mean(U_t|!F13)")
    lines.append("")
    for r in out.itertuples(index=False):
        lines.append(
            f"- {r.name}: w=({r.w_emdat_td:g},{r.w_covid_deaths_pm:g}) diff_mean={r.diff_mean:+.3f}; "
            f"OLS coef={r.ols_f13_only_coef:+.3f} p={r.ols_f13_only_p:.4g}; controls coef={r.ols_controls_coef:+.3f} p={r.ols_controls_p:.4g}"
        )
    _ensure_dir(out_dir)
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8", errors="replace")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

