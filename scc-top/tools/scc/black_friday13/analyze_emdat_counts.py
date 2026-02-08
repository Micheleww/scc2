#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

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


def _bh_fdr(pvals: np.ndarray) -> np.ndarray:
    p = np.asarray(pvals, dtype=float)
    n = p.size
    order = np.argsort(p)
    ranked = p[order]
    q = ranked * n / (np.arange(n) + 1.0)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty_like(q)
    out[order] = np.clip(q, 0.0, 1.0)
    return out


def _poisson_2sided_p(k: float, mu: float) -> float:
    # Use integer k for counts; if fractional (from distribution), round to nearest for conservative test.
    kk = int(round(float(k)))
    mu = float(mu)
    if mu <= 0:
        return 1.0 if kk == 0 else 0.0
    cdf = st.poisson.cdf(kk, mu)
    sf = st.poisson.sf(kk - 1, mu)  # P(X>=kk)
    return float(min(1.0, 2.0 * min(cdf, sf)))


@dataclass(frozen=True)
class GlmCoef:
    term: str
    coef: float
    se: float
    z: float
    p: float
    irr: float
    irr_ci_low: float
    irr_ci_high: float


def _glm_poisson_robust(df: pd.DataFrame, formula: str) -> Tuple[sm.GLM, Any, pd.DataFrame]:
    model = smf.glm(formula=formula, data=df, family=sm.families.Poisson())
    res = model.fit(cov_type="HC0")
    params = res.params
    bse = res.bse
    z = params / bse
    p = 2.0 * (1.0 - st.norm.cdf(np.abs(z)))
    ci = res.conf_int()
    irr = np.exp(params)
    irr_lo = np.exp(ci[0])
    irr_hi = np.exp(ci[1])
    out = pd.DataFrame(
        {
            "term": params.index.astype(str),
            "coef": params.values.astype(float),
            "se": bse.values.astype(float),
            "z": z.values.astype(float),
            "p": p.astype(float),
            "irr": irr.values.astype(float),
            "irr_ci_low": irr_lo.values.astype(float),
            "irr_ci_high": irr_hi.values.astype(float),
        }
    )
    return model, res, out


def _basic_groups(df: pd.DataFrame) -> pd.DataFrame:
    y = df["emdat_event_count"].astype(float)
    f13 = df["is_friday_13"].astype(bool)
    friday = df["is_friday"].astype(bool)
    dom13 = df["dom"].astype(int) == 13

    def _grp(mask: pd.Series, name: str) -> Dict[str, Any]:
        m = mask.astype(bool)
        days = int(m.sum())
        total = float(y[m].sum())
        mean = float(total / days) if days else float("nan")
        return {"group": name, "days": days, "total_events": total, "mean_events_per_day": mean}

    rows = [
        _grp(pd.Series([True] * len(df)), "all_days"),
        _grp(f13, "friday_13"),
        _grp(friday & ~dom13, "friday_not_13"),
        _grp(dom13 & ~friday, "dom_13_not_friday"),
        _grp(~f13, "not_friday_13"),
    ]
    out = pd.DataFrame(rows)
    base = out[out["group"] == "not_friday_13"].iloc[0]
    f13r = out[out["group"] == "friday_13"].iloc[0]
    if base["mean_events_per_day"] > 0 and np.isfinite(f13r["mean_events_per_day"]):
        out.loc[out["group"] == "friday_13", "rate_ratio_vs_not_friday_13"] = float(f13r["mean_events_per_day"] / base["mean_events_per_day"])
    else:
        out.loc[out["group"] == "friday_13", "rate_ratio_vs_not_friday_13"] = float("nan")
    return out


def _good_bad_by_combo(df: pd.DataFrame) -> pd.DataFrame:
    y = df["emdat_event_count"].astype(float)
    total_events = float(y.sum())
    total_days = float(len(df))
    overall_rate = total_events / total_days if total_days else float("nan")

    g = df.groupby(["dow", "dom"], dropna=False)["emdat_event_count"].agg(["sum", "count"]).reset_index()
    g = g.rename(columns={"sum": "events", "count": "days"})
    g["rate"] = g["events"] / g["days"]
    g["mu_null"] = overall_rate * g["days"]
    g["p_poisson_vs_global"] = [
        _poisson_2sided_p(k, mu) for k, mu in zip(g["events"].values.tolist(), g["mu_null"].values.tolist())
    ]
    g["q_fdr"] = _bh_fdr(g["p_poisson_vs_global"].to_numpy())
    g["direction"] = np.where(g["rate"] > overall_rate, "higher", "lower")
    g["is_friday_13"] = (g["dow"] == 4) & (g["dom"] == 13)
    g = g.sort_values(["q_fdr", "p_poisson_vs_global", "dow", "dom"]).reset_index(drop=True)
    return g


def _save_plots(df: pd.DataFrame, combo: pd.DataFrame, out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        # Repo environments may omit matplotlib; plots are optional evidence.
        return

    _ensure_dir(out_dir)

    # DOW bar
    dow = (
        df.groupby("dow", as_index=False)["emdat_event_count"]
        .agg(events="sum", days="count")
        .assign(rate=lambda x: x["events"] / x["days"])
    )
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.bar(dow["dow"].astype(int), dow["rate"].astype(float))
    ax.set_title("EM-DAT daily event rate by day-of-week (post-2000, Natural, drop)")
    ax.set_xlabel("dow (Mon=0 ... Sun=6)")
    ax.set_ylabel("events per day")
    fig.tight_layout()
    fig.savefig(out_dir / "rate_by_dow.png", dpi=160)
    plt.close(fig)

    # DOM bar (1..31)
    dom = (
        df.groupby("dom", as_index=False)["emdat_event_count"]
        .agg(events="sum", days="count")
        .assign(rate=lambda x: x["events"] / x["days"])
        .sort_values("dom")
    )
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.bar(dom["dom"].astype(int), dom["rate"].astype(float))
    ax.set_title("EM-DAT daily event rate by day-of-month (post-2000, Natural, drop)")
    ax.set_xlabel("dom (1..31)")
    ax.set_ylabel("events per day")
    fig.tight_layout()
    fig.savefig(out_dir / "rate_by_dom.png", dpi=160)
    plt.close(fig)

    # Heatmap: (dow x dom) rate
    pivot = combo.pivot(index="dow", columns="dom", values="rate").reindex(index=range(7), columns=range(1, 32))
    fig, ax = plt.subplots(figsize=(14, 3.6))
    im = ax.imshow(pivot.values, aspect="auto", interpolation="nearest")
    ax.set_title("EM-DAT rate heatmap: dow x dom (post-2000, Natural, drop)")
    ax.set_xlabel("dom (1..31)")
    ax.set_ylabel("dow (Mon=0 ... Sun=6)")
    ax.set_xticks(np.arange(31))
    ax.set_xticklabels([str(i) for i in range(1, 32)], fontsize=7)
    ax.set_yticks(np.arange(7))
    ax.set_yticklabels([str(i) for i in range(7)], fontsize=8)
    fig.colorbar(im, ax=ax, fraction=0.02, pad=0.02, label="events/day")

    # Mark Friday 13 cell.
    ax.scatter([12], [4], s=40, facecolors="none", edgecolors="red", linewidths=1.5)
    ax.text(12, 4, "  F13", color="red", fontsize=8, va="center", ha="left")

    fig.tight_layout()
    fig.savefig(out_dir / "heatmap_dow_dom.png", dpi=160)
    plt.close(fig)


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Analyze EM-DAT daily event counts for Friday-13th effects (variant A).")
    ap.add_argument(
        "--panel",
        default="artifacts/black_friday13/ingest/panel__natural__drop__post2000.parquet",
        help="Panel parquet (must include emdat_event_count + calendar cols).",
    )
    ap.add_argument("--out-dir", default="artifacts/black_friday13/emdat_counts_A", help="Output dir.")
    ap.add_argument(
        "--exclude-dom",
        default="",
        help="Comma-separated day-of-month values to exclude (e.g. '1' for a date-stacking sensitivity).",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    panel = Path(args.panel)
    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    df = pd.read_parquet(panel)
    required = ["day", "year", "month", "dom", "dow", "is_friday", "is_friday_13", "emdat_event_count"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"panel missing columns: {missing}")

    df = df[required].copy()
    df["day"] = pd.to_datetime(df["day"], errors="coerce")
    df = df.dropna(subset=["day"]).sort_values("day").reset_index(drop=True)
    df["year"] = df["year"].astype(int)
    df["month"] = df["month"].astype(int)
    df["dom"] = df["dom"].astype(int)
    df["dow"] = df["dow"].astype(int)
    df["is_friday"] = df["is_friday"].astype(bool)
    df["is_friday_13"] = df["is_friday_13"].astype(bool)
    df["emdat_event_count"] = pd.to_numeric(df["emdat_event_count"], errors="coerce").fillna(0.0)

    exclude_dom: list[int] = []
    if str(args.exclude_dom).strip():
        for s in str(args.exclude_dom).split(","):
            s = s.strip()
            if not s:
                continue
            exclude_dom.append(int(s))
        if exclude_dom:
            df = df[~df["dom"].isin(exclude_dom)].copy().reset_index(drop=True)

    overview = {
        "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "panel": str(panel).replace("\\", "/"),
        "days": int(len(df)),
        "range": {"min_day": str(df["day"].min().date()), "max_day": str(df["day"].max().date())},
        "total_events": float(df["emdat_event_count"].sum()),
        "friday13_days": int(df["is_friday_13"].sum()),
        "exclude_dom": exclude_dom,
    }
    _write_json(out_dir / "overview.json", overview)

    groups = _basic_groups(df)
    groups.to_csv(out_dir / "groups.csv", index=False, encoding="utf-8")

    # 1.1: simplest test via Poisson regression.
    _, res1, coef1 = _glm_poisson_robust(df, "emdat_event_count ~ is_friday_13")
    coef1.to_csv(out_dir / "glm__f13_only.csv", index=False, encoding="utf-8")

    # 1.2: decomposition (weekday + day-of-month), plus season/year controls.
    _, res2, coef2 = _glm_poisson_robust(df, "emdat_event_count ~ C(dow) + C(dom)")
    coef2.to_csv(out_dir / "glm__dow_dom.csv", index=False, encoding="utf-8")

    _, res3, coef3 = _glm_poisson_robust(df, "emdat_event_count ~ C(dow) + C(dom) + C(month) + C(year) + is_friday_13")
    coef3.to_csv(out_dir / "glm__dow_dom_month_year_plus_f13.csv", index=False, encoding="utf-8")

    # 1.3: good/bad date-attributes by combo with FDR control.
    combo = _good_bad_by_combo(df)
    combo.to_csv(out_dir / "good_bad_dow_dom.csv", index=False, encoding="utf-8")

    # Plots for discussion (best-effort; may be skipped if matplotlib is unavailable).
    had_plots_before = any((out_dir / p).exists() for p in ["rate_by_dow.png", "rate_by_dom.png", "heatmap_dow_dom.png"])
    _save_plots(df, combo, out_dir)
    plots_generated = all((out_dir / p).exists() for p in ["rate_by_dow.png", "rate_by_dom.png", "heatmap_dow_dom.png"])

    # Render a short markdown report for checkpoint discussion.
    def _pick_term(coefs: pd.DataFrame, term: str) -> Optional[GlmCoef]:
        m = coefs[coefs["term"] == term]
        if m.empty:
            return None
        r = m.iloc[0].to_dict()
        return GlmCoef(**{k: r[k] for k in asdict(GlmCoef("", 0, 0, 0, 0, 0, 0, 0)).keys()})

    c1 = _pick_term(coef1, "is_friday_13[T.True]")
    c3 = _pick_term(coef3, "is_friday_13[T.True]")

    f13_row = combo[combo["is_friday_13"]].iloc[0].to_dict() if combo["is_friday_13"].any() else None
    top_bad = combo[(combo["q_fdr"] <= 0.05) & (combo["direction"] == "higher")].head(10)
    top_good = combo[(combo["q_fdr"] <= 0.05) & (combo["direction"] == "lower")].head(10)

    def _fmt_glm(g: Optional[GlmCoef]) -> str:
        if g is None:
            return "NA"
        return f"IRR={g.irr:.3f} (95% CI {g.irr_ci_low:.3f}..{g.irr_ci_high:.3f}), p={g.p:.4g}"

    lines = []
    lines.append("# Checkpoint C (Part 1.1–1.3) — EM-DAT daily event frequency (Variant A)")
    lines.append("")
    lines.append("- Variant: Natural only, missing Start Day dropped, post-2000 window")
    if exclude_dom:
        lines.append(f"- Sensitivity: excluded dom in {exclude_dom}")
    lines.append(f"- Days: {overview['days']} ({overview['range']['min_day']}..{overview['range']['max_day']})")
    lines.append(f"- Friday-13 days in window: {overview['friday13_days']}")
    lines.append(f"- Total EM-DAT events (daily start counts): {overview['total_events']:.0f}")
    lines.append("")
    lines.append("## 1.1 Friday-13 frequency")
    lines.append(f"- Poisson GLM (y ~ Friday13): {_fmt_glm(c1)}")
    if f13_row:
        lines.append(f"- Friday13 vs global-rate Poisson test: p={float(f13_row['p_poisson_vs_global']):.4g}, q(FDR)={float(f13_row['q_fdr']):.4g}")
    lines.append("")
    lines.append("## 1.2 Decomposition (weekday + day-of-month)")
    lines.append(f"- Poisson GLM with controls (y ~ dow + dom + month + year + Friday13): {_fmt_glm(c3)}")
    lines.append("- Interpretation: if Friday13 stays significant here, it suggests an interaction beyond independent weekday/day-of-month effects.")
    lines.append("")
    lines.append("## 1.3 ‘Good/Bad’ date attributes (dow x dom)")
    lines.append(f"- Multiple tests: {int(len(combo))} combos, FDR cutoff q<=0.05")
    lines.append(f"- Significant ‘bad’ combos (higher rate): {int(((combo['q_fdr']<=0.05)&(combo['direction']=='higher')).sum())}")
    lines.append(f"- Significant ‘good’ combos (lower rate): {int(((combo['q_fdr']<=0.05)&(combo['direction']=='lower')).sum())}")
    lines.append("")
    if not top_bad.empty:
        lines.append("### Top ‘bad’ (q<=0.05, highest first)")
        for r in top_bad.itertuples(index=False):
            lines.append(f"- dow={int(r.dow)} dom={int(r.dom)} rate={float(r.rate):.4f} p={float(r.p_poisson_vs_global):.3g} q={float(r.q_fdr):.3g}")
        lines.append("")
    if not top_good.empty:
        lines.append("### Top ‘good’ (q<=0.05, lowest first)")
        for r in top_good.itertuples(index=False):
            lines.append(f"- dow={int(r.dow)} dom={int(r.dom)} rate={float(r.rate):.4f} p={float(r.p_poisson_vs_global):.3g} q={float(r.q_fdr):.3g}")
        lines.append("")
    lines.append("## Outputs")
    lines.append("- `groups.csv`: basic group means (Friday13 vs others)")
    lines.append("- `glm__*.csv`: GLM coefficient tables (robust SE)")
    lines.append("- `good_bad_dow_dom.csv`: per (dow,dom) rates + p/q + Friday13 flag")
    if plots_generated:
        lines.append("- `rate_by_dow.png`, `rate_by_dom.png`, `heatmap_dow_dom.png`")
    else:
        lines.append("- Plots: skipped (matplotlib not available in environment)")
    _write_text(out_dir / "report.md", "\n".join(lines) + "\n")

    # Persist model summary stats.
    models = {
        "glm_f13_only": {"formula": res1.model.formula, "nobs": int(res1.nobs), "llf": float(res1.llf)},
        "glm_dow_dom": {"formula": res2.model.formula, "nobs": int(res2.nobs), "llf": float(res2.llf)},
        "glm_dow_dom_month_year_plus_f13": {"formula": res3.model.formula, "nobs": int(res3.nobs), "llf": float(res3.llf)},
    }
    _write_json(out_dir / "models.json", models)
    overview["plots_generated"] = bool(plots_generated)
    if not plots_generated and had_plots_before:
        overview["plots_generated_note"] = "existing plot files were present but could not be regenerated without matplotlib"
    _write_json(out_dir / "overview.json", overview)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
