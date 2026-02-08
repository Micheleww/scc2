#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
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


def _bh_fdr(pvals: np.ndarray) -> np.ndarray:
    p = np.asarray(pvals, dtype=float)
    n = p.size
    if n == 0:
        return p
    order = np.argsort(p)
    ranked = p[order]
    q = ranked * n / (np.arange(n) + 1.0)
    q = np.minimum.accumulate(q[::-1])[::-1]
    out = np.empty_like(q)
    out[order] = np.clip(q, 0.0, 1.0)
    return out


@dataclass(frozen=True)
class GlmF13:
    irr: float
    p: float
    irr_ci_low: float
    irr_ci_high: float


def _glm_poisson_f13(df: pd.DataFrame, formula: str) -> Optional[GlmF13]:
    try:
        model = smf.glm(formula=formula, data=df, family=sm.families.Poisson())
        res = model.fit(cov_type="HC0")
        params = res.params
        if "is_friday_13[T.True]" not in params.index:
            return None
        b = float(params["is_friday_13[T.True]"])
        se = float(res.bse["is_friday_13[T.True]"])
        z = b / se if se > 0 else float("nan")
        p = float(2.0 * (1.0 - st.norm.cdf(abs(z)))) if np.isfinite(z) else float("nan")
        ci = res.conf_int().loc["is_friday_13[T.True]"].to_numpy(dtype=float)
        irr = float(np.exp(b))
        return GlmF13(irr=irr, p=p, irr_ci_low=float(np.exp(ci[0])), irr_ci_high=float(np.exp(ci[1])))
    except Exception:
        return None


def _poisson_2sided_p(k: float, mu: float) -> float:
    kk = int(round(float(k)))
    mu = float(mu)
    if mu <= 0:
        return 1.0 if kk == 0 else 0.0
    cdf = st.poisson.cdf(kk, mu)
    sf = st.poisson.sf(kk - 1, mu)
    return float(min(1.0, 2.0 * min(cdf, sf)))


def _daily_counts_by(events: pd.DataFrame, level: str) -> pd.DataFrame:
    if level not in ("region", "subregion"):
        raise ValueError("level must be region or subregion")
    df = events.copy()
    df = df[df["disaster_group"] == "Natural"]
    df = df[df["start_year"].notna() & (df["start_year"].astype(int) >= 2000)]
    df = df[df["start_date"].notna()]
    df[level] = df[level].fillna("Unknown").astype(str)
    df["day"] = pd.to_datetime(df["start_date"]).dt.floor("D")
    out = df.groupby([level, "day"], as_index=False)["disno"].nunique().rename(columns={"disno": "y"})
    return out


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Regional appendix: Friday-13 tests by EM-DAT region/subregion (Natural, drop, post-2000).")
    ap.add_argument("--emdat-events", default="artifacts/black_friday13/ingest/emdat_events.parquet")
    ap.add_argument("--base-calendar", default="artifacts/black_friday13/ingest/panel__natural__drop__post2000.parquet")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/emdat_region_appendix_post2000")
    ap.add_argument("--min-events-for-controls", type=float, default=200.0, help="Skip the controlled GLM if total_events is below this.")
    args = ap.parse_args(list(argv) if argv is not None else None)

    emdat_path = Path(args.emdat_events)
    base_path = Path(args.base_calendar)
    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    base = pd.read_parquet(base_path, columns=["day", "year", "month", "dom", "dow", "is_friday_13"])
    base["day"] = pd.to_datetime(base["day"], errors="coerce")
    base = base.dropna(subset=["day"]).sort_values("day").reset_index(drop=True)
    for c in ("year", "month", "dom", "dow"):
        base[c] = base[c].astype(int)
    base["is_friday_13"] = base["is_friday_13"].astype(bool)

    events = pd.read_parquet(
        emdat_path,
        columns=["disno", "disaster_group", "region", "subregion", "start_year", "start_date"],
    )

    overview = {
        "generated_utc": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "window": {"min_day": str(base["day"].min().date()), "max_day": str(base["day"].max().date()), "days": int(len(base))},
        "friday13_days": int(base["is_friday_13"].sum()),
        "min_events_for_controls": float(args.min_events_for_controls),
    }

    def _run_level(level: str) -> pd.DataFrame:
        daily = _daily_counts_by(events, level=level)
        groups = sorted(daily[level].unique().tolist())
        rows: list[dict[str, Any]] = []
        for g in groups:
            s = base.merge(daily[daily[level] == g][["day", "y"]], on="day", how="left")
            s["y"] = pd.to_numeric(s["y"], errors="coerce").fillna(0.0)
            s["is_friday_13"] = s["is_friday_13"].astype(bool)
            s["dow"] = s["dow"].astype(int)
            s["dom"] = s["dom"].astype(int)
            s["month"] = s["month"].astype(int)
            s["year"] = s["year"].astype(int)

            total_events = float(s["y"].sum())
            f13_events = float(s.loc[s["is_friday_13"], "y"].sum())
            f13_days = float(s["is_friday_13"].sum())
            non_f13_days = float((~s["is_friday_13"]).sum())
            non_f13_events = float(total_events - f13_events)
            rate_f13 = f13_events / f13_days if f13_days else float("nan")
            rate_non_f13 = non_f13_events / non_f13_days if non_f13_days else float("nan")
            rr = (rate_f13 / rate_non_f13) if (np.isfinite(rate_f13) and np.isfinite(rate_non_f13) and rate_non_f13 > 0) else float("nan")
            mu_null = total_events * (f13_days / float(len(s))) if len(s) else float("nan")
            p_poisson = _poisson_2sided_p(f13_events, mu_null) if np.isfinite(mu_null) else float("nan")

            # GLMs: unstable when one side is zero (complete separation in Poisson GLM).
            can_glm = (f13_events > 0.0) and (non_f13_events > 0.0)
            m0 = _glm_poisson_f13(s, "y ~ is_friday_13") if can_glm else None
            m1 = (
                _glm_poisson_f13(s, "y ~ C(dow) + C(dom) + C(month) + C(year) + is_friday_13")
                if (can_glm and total_events >= float(args.min_events_for_controls))
                else None
            )

            rows.append(
                {
                    "level": level,
                    "group": g,
                    "total_events": total_events,
                    "mean_events_per_day": float(s["y"].mean()),
                    "f13_events": f13_events,
                    "rate_f13": rate_f13,
                    "rate_non_f13": rate_non_f13,
                    "rate_ratio_f13_vs_nonf13": rr,
                    "mu_null_f13_days": mu_null,
                    "p_poisson_f13_vs_global": p_poisson,
                    "m0_irr": None if m0 is None else m0.irr,
                    "m0_p": None if m0 is None else m0.p,
                    "m0_ci_low": None if m0 is None else m0.irr_ci_low,
                    "m0_ci_high": None if m0 is None else m0.irr_ci_high,
                    "m1_irr": None if m1 is None else m1.irr,
                    "m1_p": None if m1 is None else m1.p,
                    "m1_ci_low": None if m1 is None else m1.irr_ci_low,
                    "m1_ci_high": None if m1 is None else m1.irr_ci_high,
                }
            )

        out = pd.DataFrame(rows)
        out["m0_p"] = pd.to_numeric(out["m0_p"], errors="coerce")
        out["m1_p"] = pd.to_numeric(out["m1_p"], errors="coerce")
        out["p_poisson_f13_vs_global"] = pd.to_numeric(out["p_poisson_f13_vs_global"], errors="coerce")
        out["q_poisson_fdr"] = _bh_fdr(out["p_poisson_f13_vs_global"].fillna(1.0).to_numpy())
        out["m0_q_fdr"] = _bh_fdr(out["m0_p"].fillna(1.0).to_numpy())
        out["m1_q_fdr"] = _bh_fdr(out["m1_p"].fillna(1.0).to_numpy())
        out = out.sort_values(["q_poisson_fdr", "p_poisson_f13_vs_global", "group"]).reset_index(drop=True)
        return out

    region_tbl = _run_level("region")
    subregion_tbl = _run_level("subregion")
    region_tbl.to_csv(out_dir / "region_f13_tests.csv", index=False, encoding="utf-8")
    subregion_tbl.to_csv(out_dir / "subregion_f13_tests.csv", index=False, encoding="utf-8")
    _write_json(out_dir / "overview.json", overview)

    # Markdown summary: show exact Poisson comparison first; controlled GLM as a secondary check.
    def _top(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
        return df[["group", "total_events", "rate_ratio_f13_vs_nonf13", "p_poisson_f13_vs_global", "q_poisson_fdr", "m1_irr", "m1_p", "m1_q_fdr"]].head(n)

    lines: list[str] = []
    lines.append("# Regional appendix — EM-DAT Friday-13 tests (post-2000, Natural, drop)")
    lines.append("")
    lines.append(f"- Window: {overview['window']['min_day']}..{overview['window']['max_day']} ({overview['window']['days']} days)")
    lines.append(f"- Friday-13 days: {overview['friday13_days']}")
    lines.append("- Model m1: Poisson GLM with robust SE: y ~ dow + dom + month + year + Friday13")
    lines.append("- Multiple testing: BH-FDR q reported within each table (region vs subregion separately)")
    lines.append("")

    def _emit_section(title: str, tbl: pd.DataFrame) -> None:
        lines.append(f"## {title}")
        sig = tbl[(tbl["q_poisson_fdr"] <= 0.1) & tbl["p_poisson_f13_vs_global"].notna()].copy()
        lines.append(f"- Groups: {len(tbl)}; q<=0.1 hits (Poisson): {len(sig)}")
        lines.append("")
        lines.append("Top by (q, p):")
        for r in _top(tbl, 10).itertuples(index=False):
            rr = float(r.rate_ratio_f13_vs_nonf13) if pd.notna(r.rate_ratio_f13_vs_nonf13) else float("nan")
            p0 = float(r.p_poisson_f13_vs_global) if pd.notna(r.p_poisson_f13_vs_global) else float("nan")
            q0 = float(r.q_poisson_fdr) if pd.notna(r.q_poisson_fdr) else float("nan")
            irr = float(r.m1_irr) if pd.notna(r.m1_irr) else float("nan")
            p1 = float(r.m1_p) if pd.notna(r.m1_p) else float("nan")
            q1 = float(r.m1_q_fdr) if pd.notna(r.m1_q_fdr) else float("nan")
            lines.append(
                f"- {r.group}: events={float(r.total_events):.0f}, RR={rr:.3f}, Poisson p={p0:.4g} q={q0:.4g}; m1(IRR)={irr:.3f} p={p1:.4g} q={q1:.4g}"
            )
        lines.append("")

    _emit_section("By region", region_tbl)
    _emit_section("By subregion", subregion_tbl)

    lines.append("## Outputs")
    lines.append("- `region_f13_tests.csv`, `subregion_f13_tests.csv`")
    lines.append("- `overview.json`")
    _write_text(out_dir / "report.md", "\n".join(lines) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
