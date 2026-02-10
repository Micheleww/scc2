"""
Evaluation metrics for walk-forward and portfolio reports.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _safe_series(values: list[float]) -> pd.Series:
    if not values:
        return pd.Series(dtype=float)
    return pd.Series(values, dtype=float)


def compute_equity_metrics(
    equity_curve: list[float], positions: list[dict[str, float]] = None
) -> dict[str, float]:
    series = _safe_series(equity_curve)
    if series.empty:
        return {
            "total_return": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "turnover": 0.0,
        }
    returns = series.pct_change().dropna()
    total_return = (series.iloc[-1] / series.iloc[0]) - 1 if series.iloc[0] != 0 else 0.0
    volatility = float(returns.std()) if not returns.empty else 0.0
    sharpe = float(returns.mean() / returns.std()) if returns.std() not in (0, np.nan) else 0.0
    drawdowns = (series / series.cummax()) - 1.0
    max_drawdown = float(drawdowns.min()) if not drawdowns.empty else 0.0

    # Calculate turnover
    turnover = 0.0
    if positions and len(positions) > 1:
        # Simple turnover calculation: sum of absolute changes in position weights
        total_turnover = 0.0
        for i in range(1, len(positions)):
            prev_pos = positions[i - 1]
            curr_pos = positions[i]
            # Get all symbols in either position
            symbols = set(prev_pos.keys()) | set(curr_pos.keys())
            for symbol in symbols:
                prev_weight = prev_pos.get(symbol, 0.0)
                curr_weight = curr_pos.get(symbol, 0.0)
                total_turnover += abs(curr_weight - prev_weight)
        # Average daily turnover
        turnover = total_turnover / (len(positions) - 1) if len(positions) > 1 else 0.0

    return {
        "total_return": float(total_return),
        "volatility": float(volatility),
        "sharpe": float(sharpe),
        "max_drawdown": float(abs(max_drawdown)),
        "turnover": float(turnover),
    }


def distribution_summary(values: list[float]) -> dict[str, float]:
    series = _safe_series(values)
    if series.empty:
        return {"min": 0.0, "p25": 0.0, "p50": 0.0, "p75": 0.0, "max": 0.0, "mean": 0.0}
    return {
        "min": float(series.min()),
        "p25": float(series.quantile(0.25)),
        "p50": float(series.quantile(0.5)),
        "p75": float(series.quantile(0.75)),
        "max": float(series.max()),
        "mean": float(series.mean()),
    }


def topk_intersection_rate(rankings: list[list[str]], k: int) -> float:
    if not rankings or k <= 0:
        return 0.0
    top_sets = [set(r[:k]) for r in rankings if r]
    if len(top_sets) < 2:
        return 1.0 if top_sets else 0.0
    intersection = set.intersection(*top_sets)
    union = set.union(*top_sets)
    return float(len(intersection) / len(union)) if union else 0.0


def spearman_rank_correlation(rank_a: list[str], rank_b: list[str]) -> float:
    if not rank_a or not rank_b:
        return 0.0
    common = [item for item in rank_a if item in rank_b]
    if len(common) < 2:
        return 0.0
    rank_a_idx = {name: i for i, name in enumerate(rank_a)}
    rank_b_idx = {name: i for i, name in enumerate(rank_b)}
    a = [rank_a_idx[name] for name in common]
    b = [rank_b_idx[name] for name in common]
    return float(pd.Series(a).corr(pd.Series(b), method="spearman"))


def ranking_correlations(rankings: list[list[str]]) -> list[tuple[str, float]]:
    correlations = []
    for i in range(len(rankings) - 1):
        corr = spearman_rank_correlation(rankings[i], rankings[i + 1])
        correlations.append((f"{i}-{i + 1}", corr))
    return correlations
