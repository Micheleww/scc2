"""
Portfolio manager for combining strategy results without touching backtest logic.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.quantsys.evaluation.metrics import compute_equity_metrics
from src.quantsys.portfolio.allocation import (
    drawdown_scale,
    equal_weight,
    risk_parity,
    vol_target_scale,
)


class PortfolioManager:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.target_vol = float(self.config.get("target_vol", 0.02))
        self.max_drawdown_threshold = float(self.config.get("max_drawdown_threshold", 0.2))
        self.allocation_method = self.config.get("allocation_method", "equal")

    def build_portfolio(self, strategy_results: list[dict[str, Any]]) -> dict[str, Any]:
        equity_frames = {}
        for result in strategy_results:
            name = result["name"]
            equity = result["equity_curve"]
            equity_frames[name] = pd.Series(equity, dtype=float)

        equity_df = pd.DataFrame(equity_frames).dropna(how="all")
        returns_df = equity_df.pct_change().dropna()

        if self.allocation_method == "risk_parity":
            weights = risk_parity(returns_df)
        else:
            weights = equal_weight(list(equity_df.columns))

        weighted_returns = pd.Series(0.0, index=returns_df.index)
        for name, weight in weights.items():
            if name in returns_df.columns:
                weighted_returns += returns_df[name] * weight

        equity_curve = (1 + weighted_returns).cumprod()
        scale = vol_target_scale(weighted_returns, self.target_vol)
        equity_curve = equity_curve * scale
        scale_dd = drawdown_scale(equity_curve, self.max_drawdown_threshold)
        equity_curve = equity_curve * scale_dd

        metrics = compute_equity_metrics(equity_curve.tolist())
        contribution = {
            name: float(returns_df[name].mean() * weights.get(name, 0.0))
            for name in returns_df.columns
        }

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "allocation_method": self.allocation_method,
            "weights": weights,
            "scale_vol_target": scale,
            "scale_drawdown": scale_dd,
            "equity_curve": equity_curve.tolist(),
            "metrics": metrics,
            "contribution": contribution,
        }

    def write_reports(self, report: dict[str, Any]) -> dict[str, str]:
        root = Path(__file__).resolve().parents[3]
        reports_dir = root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        json_path = reports_dir / "portfolio_report.json"
        md_path = reports_dir / "portfolio_summary.md"

        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
        metrics = report.get("metrics", {})

        lines = [
            "# Portfolio Summary",
            "",
            f"- generated_at: {report.get('generated_at')}",
            f"- allocation_method: {report.get('allocation_method')}",
            f"- total_return: {metrics.get('total_return')}",
            f"- max_drawdown: {metrics.get('max_drawdown')}",
            f"- volatility: {metrics.get('volatility')}",
            "",
            "## Risk Notes",
            "- Portfolio scaling applies vol target and drawdown cap at portfolio layer.",
        ]
        md_path.write_text("\n".join(lines), encoding="utf-8")
        return {"report": str(json_path), "summary": str(md_path)}
