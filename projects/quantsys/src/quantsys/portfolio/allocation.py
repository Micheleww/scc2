"""
Portfolio allocation methods.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def equal_weight(strategies: list[str]) -> dict[str, float]:
    if not strategies:
        return {}
    weight = 1.0 / len(strategies)
    return dict.fromkeys(strategies, weight)


def risk_parity(returns: pd.DataFrame) -> dict[str, float]:
    if returns.empty:
        return {}
    vol = returns.std().replace(0, np.nan)
    inv_vol = 1.0 / vol
    inv_vol = inv_vol.replace([np.inf, -np.inf], np.nan).dropna()
    if inv_vol.empty:
        return {}
    weights = inv_vol / inv_vol.sum()
    return weights.to_dict()


def vol_target_scale(portfolio_returns: pd.Series, target_vol: float) -> float:
    realized_vol = float(portfolio_returns.std()) if not portfolio_returns.empty else 0.0
    if realized_vol <= 0:
        return 1.0
    return float(min(1.0, target_vol / realized_vol))


def drawdown_scale(equity_curve: pd.Series, max_drawdown_threshold: float) -> float:
    if equity_curve.empty:
        return 1.0
    drawdown = (equity_curve / equity_curve.cummax()) - 1.0
    max_dd = abs(float(drawdown.min()))
    if max_dd <= max_drawdown_threshold:
        return 1.0
    return float(max(0.1, max_drawdown_threshold / max_dd))
