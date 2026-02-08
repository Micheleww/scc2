#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _save(fig: go.Figure, path: Path, *, scale: int = 2) -> None:
    _ensure_dir(path.parent)
    fig.write_image(str(path), scale=scale)


def _emdat_surface(fig_dir: Path) -> None:
    df = pd.read_csv("artifacts/black_friday13/emdat_counts_A/good_bad_dow_dom.csv")
    df["dow"] = df["dow"].astype(int)
    df["dom"] = df["dom"].astype(int)
    pivot = df.pivot(index="dow", columns="dom", values="rate").reindex(index=range(7), columns=range(1, 32))
    z = pivot.to_numpy(dtype=float)
    x = np.array(list(range(1, 32)))
    y = np.array(list(range(0, 7)))

    surf = go.Figure(
        data=[
            go.Surface(
                x=x,
                y=y,
                z=z,
                colorscale="Viridis",
                showscale=True,
                colorbar=dict(title="events/day"),
            )
        ]
    )
    surf.update_layout(
        title="EM-DAT Natural (post-2000, drop): daily event-start rate surface (dow×dom)",
        scene=dict(
            xaxis_title="day of month (1..31)",
            yaxis_title="day of week (Mon=0..Sun=6)",
            zaxis_title="events/day",
        ),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    _save(surf, fig_dir / "fig1_emdat_rate_surface.png")

    # 2D heatmap with Friday-13 marker
    heat = px.imshow(
        pivot,
        aspect="auto",
        origin="lower",
        color_continuous_scale="Viridis",
        labels=dict(x="dom", y="dow", color="events/day"),
        title="EM-DAT Natural (post-2000, drop): rate heatmap (dow×dom)",
    )
    heat.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    heat.add_trace(
        go.Scatter(
            x=[13],
            y=[4],
            mode="markers+text",
            marker=dict(size=10, color="red", symbol="x"),
            text=["F13"],
            textposition="top center",
            showlegend=False,
        )
    )
    _save(heat, fig_dir / "fig2_emdat_rate_heatmap.png")


def _dom_stacking(fig_dir: Path) -> None:
    em = pd.read_parquet("artifacts/black_friday13/ingest/emdat_events.parquet", columns=["disaster_group", "start_year", "start_date"])
    em = em[(em["disaster_group"] == "Natural") & (em["start_year"].notna())]
    em = em[em["start_year"].astype(int) >= 2000]
    em = em[em["start_date"].notna()].copy()
    em["dom"] = pd.to_datetime(em["start_date"]).dt.day.astype(int)
    counts = em["dom"].value_counts().reindex(range(1, 32), fill_value=0).reset_index()
    counts.columns = ["dom", "events"]
    fig = px.bar(counts, x="dom", y="events", title="EM-DAT Natural (post-2000, drop): Start-date day-of-month counts (dom stacking)")
    fig.update_layout(xaxis=dict(dtick=1), margin=dict(l=10, r=10, t=40, b=10))
    fig.add_vline(x=1, line_width=2, line_dash="dash", line_color="red")
    fig.add_annotation(x=1, y=counts["events"].max(), text="dom=1", showarrow=False, yshift=10, font=dict(color="red"))
    _save(fig, fig_dir / "fig3_dom_stacking.png")


def _robustness_summary(fig_dir: Path) -> None:
    variants: Dict[str, Tuple[str, str]] = {
        "A (Natural drop post2000)": ("artifacts/black_friday13/emdat_counts_A/glm__f13_only.csv", "artifacts/black_friday13/emdat_counts_A/glm__dow_dom_month_year_plus_f13.csv"),
        "A excl dom=1": ("artifacts/black_friday13/emdat_counts_A_excl_dom1/glm__f13_only.csv", "artifacts/black_friday13/emdat_counts_A_excl_dom1/glm__dow_dom_month_year_plus_f13.csv"),
        "Natural uniform_month": (
            "artifacts/black_friday13/emdat_counts_natural_uniform_month_post2000/glm__f13_only.csv",
            "artifacts/black_friday13/emdat_counts_natural_uniform_month_post2000/glm__dow_dom_month_year_plus_f13.csv",
        ),
        "Natural+Tech drop": (
            "artifacts/black_friday13/emdat_counts_nat_tech_drop_post2000/glm__f13_only.csv",
            "artifacts/black_friday13/emdat_counts_nat_tech_drop_post2000/glm__dow_dom_month_year_plus_f13.csv",
        ),
    }

    rows = []
    for name, (f0, f1) in variants.items():
        t0 = pd.read_csv(f0)
        t1 = pd.read_csv(f1)
        r0 = t0[t0["term"] == "is_friday_13[T.True]"].iloc[0].to_dict()
        r1 = t1[t1["term"] == "is_friday_13[T.True]"].iloc[0].to_dict()
        rows.append(
            {
                "variant": name,
                "IRR (f13 only)": float(r0["irr"]),
                "p (f13 only)": float(r0["p"]),
                "IRR (controls)": float(r1["irr"]),
                "p (controls)": float(r1["p"]),
            }
        )

    df = pd.DataFrame(rows)
    fig = go.Figure()
    fig.add_trace(go.Bar(name="IRR (f13 only)", x=df["variant"], y=df["IRR (f13 only)"]))
    fig.add_trace(go.Bar(name="IRR (controls)", x=df["variant"], y=df["IRR (controls)"]))
    fig.add_hline(y=1.0, line_dash="dash", line_color="black")
    fig.update_layout(
        barmode="group",
        title="Friday-13 effect robustness (EM-DAT frequency): IRR across variants",
        yaxis_title="IRR (rate ratio vs non-F13)",
        margin=dict(l=10, r=10, t=50, b=10),
    )
    _save(fig, fig_dir / "fig4_f13_irr_robustness.png")


def _luck_surfaces(fig_dir: Path) -> None:
    u = pd.read_parquet("artifacts/black_friday13/luck_index_world_td/luck_index_daily.parquet")
    u["dow"] = u["dow"].astype(int)
    u["dom"] = u["dom"].astype(int)
    g = u.groupby(["dow", "dom"], as_index=False).agg(mean_U_t=("U_t", "mean"))
    pivot = g.pivot(index="dow", columns="dom", values="mean_U_t").reindex(index=range(7), columns=range(1, 32))
    z = pivot.to_numpy(dtype=float)
    x = np.array(list(range(1, 32)))
    y = np.array(list(range(0, 7)))

    surf = go.Figure(data=[go.Surface(x=x, y=y, z=z, colorscale="RdBu", reversescale=True, colorbar=dict(title="mean U_t"))])
    surf.update_layout(
        title="Luck index U_t (World 2020–2024 overlap): mean surface (dow×dom)",
        scene=dict(xaxis_title="dom", yaxis_title="dow", zaxis_title="mean U_t"),
        margin=dict(l=0, r=0, t=40, b=0),
    )
    _save(surf, fig_dir / "fig5_Ut_surface.png")

    heat = px.imshow(
        pivot,
        aspect="auto",
        origin="lower",
        color_continuous_scale="RdBu",
        labels=dict(x="dom", y="dow", color="mean U_t"),
        title="Luck index U_t (World): mean heatmap (dow×dom)",
    )
    heat.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    heat.add_trace(go.Scatter(x=[13], y=[4], mode="markers+text", marker=dict(size=10, color="black", symbol="x"), text=["F13"], textposition="top center"))
    _save(heat, fig_dir / "fig6_Ut_heatmap.png")

    # Distribution: U_t by Friday13 vs others (overlap window).
    u2 = u.copy()
    u2["group"] = np.where(u2["is_friday_13"].astype(bool), "Friday-13", "Other days")
    box = px.box(u2, x="group", y="U_t", points="all", title="U_t distribution: Friday-13 vs other days (overlap window)")
    box.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    _save(box, fig_dir / "fig7_Ut_boxplot.png")


def _omen_coeffs(fig_dir: Path) -> None:
    coef = pd.read_csv("artifacts/black_friday13/omen_rules_world_td/logit_l1_top_coefs.csv")
    coef = coef[coef["target"] == "is_bad_5p"].copy()
    coef["abs_coef"] = coef["coef"].abs()
    coef = coef.sort_values("abs_coef", ascending=False).head(20).sort_values("coef")
    fig = px.bar(coef, x="coef", y="feature", orientation="h", title="Omen rule (is_bad_5p): top L1-logit coefficients (date-only features)")
    fig.update_layout(margin=dict(l=10, r=10, t=40, b=10))
    _save(fig, fig_dir / "fig8_omen_top_coefs.png")


def _region_bar(fig_dir: Path) -> None:
    reg = pd.read_csv("artifacts/black_friday13/emdat_region_appendix_post2000/region_f13_tests.csv")
    reg = reg.sort_values("rate_ratio_f13_vs_nonf13", ascending=False)
    fig = px.bar(
        reg,
        x="group",
        y="rate_ratio_f13_vs_nonf13",
        title="Regional appendix (EM-DAT Natural post-2000): RR(F13 vs non-F13) by region",
        hover_data=["total_events", "p_poisson_f13_vs_global", "q_poisson_fdr"],
    )
    fig.add_hline(y=1.0, line_dash="dash", line_color="black")
    fig.update_layout(yaxis_title="rate ratio", margin=dict(l=10, r=10, t=50, b=10))
    _save(fig, fig_dir / "fig9_region_rr.png")


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate visualization figures for the Friday-13 report.")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/figures")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    _emdat_surface(out_dir)
    _dom_stacking(out_dir)
    _robustness_summary(out_dir)
    _luck_surfaces(out_dir)
    _omen_coeffs(out_dir)
    _region_bar(out_dir)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
