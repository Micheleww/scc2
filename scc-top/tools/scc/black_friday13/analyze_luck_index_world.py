#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd
import scipy.stats as st
import statsmodels.api as sm
import statsmodels.formula.api as smf


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, obj: Any) -> None:
    _ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")


def _write_text(path: Path, text: str) -> None:
    _ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8", errors="replace")


def _write_parquet(path: Path, df: pd.DataFrame) -> None:
    _ensure_dir(path.parent)
    df.to_parquet(path, index=False)


def _zscore(x: pd.Series) -> pd.Series:
    v = pd.to_numeric(x, errors="coerce").astype(float)
    m = float(np.nanmean(v))
    s = float(np.nanstd(v, ddof=0))
    if not np.isfinite(s) or s <= 0:
        return pd.Series(np.zeros(len(v), dtype=float), index=v.index)
    return (v - m) / s


@dataclass(frozen=True)
class CoefRow:
    term: str
    coef: float
    se: float
    z: float
    p: float


def _coef_table(res: Any) -> pd.DataFrame:
    params = res.params
    bse = res.bse
    z = params / bse
    p = 2.0 * (1.0 - st.norm.cdf(np.abs(z)))
    return pd.DataFrame(
        {
            "term": params.index.astype(str),
            "coef": params.values.astype(float),
            "se": bse.values.astype(float),
            "z": z.values.astype(float),
            "p": p.astype(float),
        }
    )


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build and analyze a daily 'unluckiness' index U_t (World) from EM-DAT + OWID COVID.")
    ap.add_argument(
        "--panel",
        default="artifacts/black_friday13/ingest/panel__natural__drop.parquet",
        help="Ingest panel parquet (calendar + EM-DAT daily aggregates + OWID World).",
    )
    ap.add_argument("--out-dir", default="artifacts/black_friday13/luck_index_world_td", help="Output directory.")
    ap.add_argument("--bad-pcts", default="0.05,0.01", help="Comma-separated tail probabilities (e.g. 0.05,0.01).")
    ap.add_argument("--w-emdat", type=float, default=1.0, help="Weight for EM-DAT component (Total Deaths).")
    ap.add_argument("--w-covid", type=float, default=1.0, help="Weight for COVID component (new_deaths_per_million).")
    ap.add_argument(
        "--covid-mode",
        default="ma7",
        choices=["raw", "ma7"],
        help="Use raw daily COVID series or 7-day trailing mean to reduce reporting periodicity.",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    panel = Path(args.panel)
    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    df = pd.read_parquet(panel)
    need = [
        "day",
        "year",
        "month",
        "dom",
        "dow",
        "is_friday",
        "is_friday_13",
        "emdat_total_deaths",
        "new_deaths_per_million_fill0",
    ]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise SystemExit(f"panel missing columns: {missing}")

    df = df[need].copy()
    df["day"] = pd.to_datetime(df["day"], errors="coerce")
    df = df.dropna(subset=["day"]).sort_values("day").reset_index(drop=True)
    for c in ("year", "month", "dom", "dow"):
        df[c] = df[c].astype(int)
    df["is_friday"] = df["is_friday"].astype(bool)
    df["is_friday_13"] = df["is_friday_13"].astype(bool)
    df["emdat_total_deaths"] = pd.to_numeric(df["emdat_total_deaths"], errors="coerce").fillna(0.0)

    covid_mask = df["new_deaths_per_million_fill0"].notna()
    d = df[covid_mask].copy().reset_index(drop=True)
    d["covid_deaths_pm_raw"] = pd.to_numeric(d["new_deaths_per_million_fill0"], errors="coerce").fillna(0.0)
    d["covid_deaths_pm_ma7"] = d["covid_deaths_pm_raw"].rolling(window=7, min_periods=1).mean()
    d["covid_new_deaths_pm"] = d["covid_deaths_pm_ma7"] if str(args.covid_mode) == "ma7" else d["covid_deaths_pm_raw"]

    # Components: log1p to reduce outlier dominance; then z-score within the overlapping COVID window.
    d["x_emdat_td"] = np.log1p(d["emdat_total_deaths"].clip(lower=0.0))
    d["x_covid_deaths_pm"] = np.log1p(d["covid_new_deaths_pm"].clip(lower=0.0))

    d["z_emdat_td"] = _zscore(d["x_emdat_td"])
    d["z_covid_deaths_pm"] = _zscore(d["x_covid_deaths_pm"])

    w_emdat = float(args.w_emdat)
    w_covid = float(args.w_covid)
    d["U_t"] = w_emdat * d["z_emdat_td"] + w_covid * d["z_covid_deaths_pm"]

    bad_pcts: list[float] = []
    for s in str(args.bad_pcts).split(","):
        s = s.strip()
        if not s:
            continue
        bad_pcts.append(float(s))
    bad_pcts = [p for p in bad_pcts if 0 < p < 1]
    if not bad_pcts:
        bad_pcts = [0.05, 0.01]
    bad_pcts = sorted(set(bad_pcts), reverse=True)

    thresholds = {}
    for p in bad_pcts:
        q = float(d["U_t"].quantile(1.0 - p))
        thresholds[str(p)] = q
        d[f"is_bad_{int(round(p*100))}p"] = d["U_t"] >= q

    # 2.2 analysis similar to Part 1.
    # A) Mean differences
    means = (
        d.groupby("is_friday_13", as_index=False)["U_t"]
        .agg(mean="mean", median="median", std="std", n="count")
        .assign(is_friday_13=lambda x: x["is_friday_13"].astype(bool))
    )

    # B) Linear model (robust SE): U_t ~ Friday13 (+ decomposed controls)
    m0 = smf.ols("U_t ~ is_friday_13", data=d).fit(cov_type="HC0")
    m1 = smf.ols("U_t ~ C(dow) + C(dom) + C(month) + C(year) + is_friday_13", data=d).fit(cov_type="HC0")
    ols0 = _coef_table(m0)
    ols1 = _coef_table(m1)

    # C) Bad-day probability: use Fisher exact test (robust to separation/rare events).
    fisher_rows: list[dict[str, Any]] = []
    for p in bad_pcts:
        col = f"is_bad_{int(round(p*100))}p"
        a = int((d["is_friday_13"] & d[col]).sum())
        b = int((d["is_friday_13"] & ~d[col]).sum())
        c = int((~d["is_friday_13"] & d[col]).sum())
        dd = int((~d["is_friday_13"] & ~d[col]).sum())
        # scipy Fisher exact: [[a,b],[c,d]]
        odds, pv = st.fisher_exact([[a, b], [c, dd]], alternative="two-sided")
        # Haldane-Anscombe correction for readable OR when zeros exist.
        odds_ha = ((a + 0.5) * (dd + 0.5)) / ((b + 0.5) * (c + 0.5))
        fisher_rows.append(
            {
                "p_tail": float(p),
                "threshold_U_t": float(thresholds[str(p)]),
                "bad_f13": a,
                "good_f13": b,
                "bad_non_f13": c,
                "good_non_f13": dd,
                "odds_ratio_fisher": float(odds) if np.isfinite(odds) else None,
                "odds_ratio_haldane_anscombe": float(odds_ha),
                "p_value_two_sided": float(pv),
            }
        )

    # Save artifacts.
    overview = {
        "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "panel": str(panel).replace("\\", "/"),
        "window": {"min_day": str(d["day"].min().date()), "max_day": str(d["day"].max().date())},
        "days": int(len(d)),
        "friday13_days": int(d["is_friday_13"].sum()),
        "weights": {"w_emdat_total_deaths": w_emdat, "w_covid_new_deaths_per_million": w_covid},
        "covid_mode": str(args.covid_mode),
        "bad_pcts": bad_pcts,
        "thresholds": thresholds,
    }
    _write_json(out_dir / "overview.json", overview)
    means.to_csv(out_dir / "means_by_friday13.csv", index=False, encoding="utf-8")
    ols0.to_csv(out_dir / "ols__U_t__f13_only.csv", index=False, encoding="utf-8")
    ols1.to_csv(out_dir / "ols__U_t__controls_plus_f13.csv", index=False, encoding="utf-8")
    fisher = pd.DataFrame(fisher_rows).sort_values("p_tail", ascending=False)
    fisher.to_csv(out_dir / "bad_day_fisher.csv", index=False, encoding="utf-8")

    # Calendar attribute summaries (for "good/bad day" flavor).
    by_dow = d.groupby("dow", as_index=False)["U_t"].agg(mean="mean", median="median", n="count")
    by_dom = d.groupby("dom", as_index=False)["U_t"].agg(mean="mean", median="median", n="count").sort_values("dom")
    by_dow.to_csv(out_dir / "U_t_by_dow.csv", index=False, encoding="utf-8")
    by_dom.to_csv(out_dir / "U_t_by_dom.csv", index=False, encoding="utf-8")

    # Store the daily series used for analysis.
    keep = [
        "day",
        "year",
        "month",
        "dom",
        "dow",
        "is_friday_13",
        "emdat_total_deaths",
        "covid_deaths_pm_raw",
        "covid_deaths_pm_ma7",
        "covid_new_deaths_pm",
        "U_t",
    ]
    keep += [c for c in d.columns if c.startswith("is_bad_")]
    _write_parquet(out_dir / "luck_index_daily.parquet", d[keep].copy())

    # Render concise markdown.
    def _f13_term(tab: pd.DataFrame) -> Optional[CoefRow]:
        m = tab[tab["term"] == "is_friday_13[T.True]"]
        if m.empty:
            return None
        r = m.iloc[0].to_dict()
        return CoefRow(term=str(r["term"]), coef=float(r["coef"]), se=float(r["se"]), z=float(r["z"]), p=float(r["p"]))

    f13_ols0 = _f13_term(ols0)
    f13_ols1 = _f13_term(ols1)

    lines = []
    lines.append("# Checkpoint D (Part 2.0–2.2) — Luck index U_t (World, TD main)")
    lines.append("")
    lines.append("- Data sources: EM-DAT (Total Deaths) + OWID COVID (World, new_deaths_per_million)")
    lines.append(f"- Window (overlap): {overview['window']['min_day']}..{overview['window']['max_day']} ({overview['days']} days)")
    lines.append(f"- Friday-13 days in window: {overview['friday13_days']}")
    lines.append(f"- COVID mode: `{overview['covid_mode']}` (raw daily vs 7-day trailing mean to reduce reporting periodicity)")
    lines.append(f"- U_t construction: log1p + zscore within window; U_t = {w_emdat:g}*z(EM-DAT TD) + {w_covid:g}*z(COVID deaths/million)")
    lines.append(f"- Bad-day thresholds (top tail): {', '.join([f'{p:g}' for p in bad_pcts])}")
    lines.append("")
    lines.append("## Does Friday-13 look worse on U_t?")
    if f13_ols0:
        lines.append(f"- OLS U_t ~ Friday13: coef={f13_ols0.coef:+.3f}, p={f13_ols0.p:.4g}")
    if f13_ols1:
        lines.append(f"- OLS with controls (dow+dom+month+year): coef={f13_ols1.coef:+.3f}, p={f13_ols1.p:.4g}")
    lines.append("")
    lines.append("## Bad-day probability")
    for r in fisher.itertuples(index=False):
        lines.append(
            f"- p={r.p_tail:g}: bad(F13)={int(r.bad_f13)}/{int(r.bad_f13+r.good_f13)} vs bad(!F13)={int(r.bad_non_f13)}/{int(r.bad_non_f13+r.good_non_f13)}; "
            f"Fisher p={float(r.p_value_two_sided):.4g}, OR(HA)={float(r.odds_ratio_haldane_anscombe):.3g}"
        )
    lines.append("")
    lines.append("## Friday-13 days (small-sample list)")
    f13_days = d[d["is_friday_13"]].copy()
    if not f13_days.empty:
        for rr in f13_days.itertuples(index=False):
            lines.append(
                f"- {rr.day.date()}: EM-DAT TD={float(rr.emdat_total_deaths):.0f}, COVID raw/ma7={float(rr.covid_deaths_pm_raw):.3f}/{float(rr.covid_deaths_pm_ma7):.3f}, used={float(rr.covid_new_deaths_pm):.3f}, U_t={float(rr.U_t):+.3f}"
            )
    else:
        lines.append("- (none in overlap window)")
    lines.append("")
    lines.append("## Outputs")
    lines.append("- `luck_index_daily.parquet`: U_t and bad-day flags for the overlap window")
    lines.append("- `ols__*.csv`: coefficient tables (robust SE)")
    lines.append("- `bad_day_fisher.csv`: bad-day Fisher tests vs Friday-13")
    lines.append("- `U_t_by_dow.csv`, `U_t_by_dom.csv`: calendar attribute summaries")
    _write_text(out_dir / "report.md", "\n".join(lines) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
