#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _write_html(fig: go.Figure, path: Path, *, title: str) -> None:
    _ensure_dir(path.parent)
    fig.update_layout(title=title)
    # Self-contained for sharing.
    fig.write_html(str(path), include_plotlyjs="inline", full_html=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate interactive HTML figures (3D/heatmaps) for sharing.")
    ap.add_argument("--out-dir", default="artifacts/black_friday13/interactive")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    _ensure_dir(out_dir)

    # Fig1 interactive: EM-DAT rate surface (Part 1 main).
    em = pd.read_csv("artifacts/black_friday13/emdat_counts_A/good_bad_dow_dom.csv")
    em["dow"] = em["dow"].astype(int)
    em["dom"] = em["dom"].astype(int)
    pivot = em.pivot(index="dow", columns="dom", values="rate").reindex(index=range(7), columns=range(1, 32))
    z = pivot.to_numpy(dtype=float)
    x = np.array(list(range(1, 32)))
    y = np.array(list(range(0, 7)))
    fig1 = go.Figure(data=[go.Surface(x=x, y=y, z=z, colorscale="Viridis", colorbar=dict(title="events/day"))])
    fig1.update_layout(
        scene=dict(xaxis_title="dom (1..31)", yaxis_title="dow (Mon=0..Sun=6)", zaxis_title="events/day"),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    _write_html(fig1, out_dir / "fig1_emdat_rate_surface.html", title="Fig 1 (interactive): EM-DAT event-start rate surface (dow×dom)")

    # Fig5 interactive: U_t mean surface.
    u = pd.read_parquet("artifacts/black_friday13/luck_index_world_td/luck_index_daily.parquet")
    u["dow"] = u["dow"].astype(int)
    u["dom"] = u["dom"].astype(int)
    g = u.groupby(["dow", "dom"], as_index=False).agg(mean_U_t=("U_t", "mean"))
    pivot_u = g.pivot(index="dow", columns="dom", values="mean_U_t").reindex(index=range(7), columns=range(1, 32))
    z2 = pivot_u.to_numpy(dtype=float)
    fig5 = go.Figure(data=[go.Surface(x=x, y=y, z=z2, colorscale="RdBu", reversescale=True, colorbar=dict(title="mean U_t"))])
    fig5.update_layout(
        scene=dict(xaxis_title="dom (1..31)", yaxis_title="dow (Mon=0..Sun=6)", zaxis_title="mean U_t"),
        margin=dict(l=0, r=0, t=50, b=0),
    )
    _write_html(fig5, out_dir / "fig5_Ut_surface.html", title="Fig 5 (interactive): Luck index mean surface (dow×dom)")

    # Heatmaps (handy for quick viewing).
    hm1 = px.imshow(pivot, aspect="auto", origin="lower", color_continuous_scale="Viridis", labels=dict(x="dom", y="dow", color="events/day"))
    _write_html(hm1, out_dir / "fig2_emdat_rate_heatmap.html", title="Fig 2 (interactive): EM-DAT rate heatmap (dow×dom)")
    hm2 = px.imshow(pivot_u, aspect="auto", origin="lower", color_continuous_scale="RdBu", labels=dict(x="dom", y="dow", color="mean U_t"))
    _write_html(hm2, out_dir / "fig6_Ut_heatmap.html", title="Fig 6 (interactive): U_t mean heatmap (dow×dom)")

    # Index page.
    index = out_dir / "index.html"
    index.write_text(
        "\n".join(
            [
                "<!doctype html>",
                "<html><head><meta charset='utf-8'><title>Friday-13 Interactive Figures</title>",
                "<style>body{font-family:Segoe UI,Arial,'Microsoft YaHei',sans-serif;margin:24px;line-height:1.4} a{color:#111827}</style>",
                "</head><body>",
                "<h1>Friday the 13th — Interactive Figures</h1>",
                "<ul>",
                "<li><a href='fig1_emdat_rate_surface.html'>Fig 1: EM-DAT rate surface (3D)</a></li>",
                "<li><a href='fig2_emdat_rate_heatmap.html'>Fig 2: EM-DAT rate heatmap</a></li>",
                "<li><a href='fig5_Ut_surface.html'>Fig 5: U_t mean surface (3D)</a></li>",
                "<li><a href='fig6_Ut_heatmap.html'>Fig 6: U_t mean heatmap</a></li>",
                "</ul>",
                "<p>Tip: open locally in a browser; 3D plots support rotate/zoom/pan.</p>",
                "</body></html>",
            ]
        )
        + "\n",
        encoding="utf-8",
        errors="replace",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

