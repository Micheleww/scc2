"""
Standard factor evaluation without strategy backtest or pnl.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.quantsys.factors.factor_registry import FactorMeta, FactorRegistry

PROMPT_POLICY = "因子评价仅限统计相关性与分层表现，不得引用回测交易结果或策略执行逻辑。"


class FactorEvaluator:
    def __init__(self, registry: FactorRegistry, config: dict[str, Any] | None = None) -> None:
        self.registry = registry
        self.config = config or {}
        self.random_seed = int(self.config.get("random_seed", 42))
        self.horizons = self.config.get("horizons", [1])
        self.quantiles = int(self.config.get("quantiles", 5))
        self.rolling_window = int(self.config.get("rolling_window", 60))
        self.decay_lags = int(self.config.get("decay_lags", 5))
        self.leakage_check_window = int(self.config.get("leakage_check_window", 5))
        self.leakage_tolerance = float(self.config.get("leakage_tolerance", 1e-9))

        np.random.seed(self.random_seed)

    def _get_forward_returns(self, close: pd.Series, horizon: int) -> pd.Series:
        return close.pct_change(periods=horizon).shift(-horizon)

    def _compute_ic(self, factor: pd.Series, returns: pd.Series) -> float:
        aligned = pd.concat([factor, returns], axis=1).dropna()
        if len(aligned) < 3:
            return float("nan")
        return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1], method="spearman"))

    def _decay_profile(self, factor: pd.Series, returns: pd.Series) -> dict[str, float]:
        profile = {}
        for lag in range(1, self.decay_lags + 1):
            profile[str(lag)] = self._compute_ic(factor, returns.shift(-lag))
        return profile

    def _layered_returns(self, factor: pd.Series, returns: pd.Series) -> dict[str, Any]:
        aligned = pd.concat([factor, returns], axis=1).dropna()
        if aligned.empty or aligned.iloc[:, 0].nunique() < self.quantiles:
            return {"quantiles": {}, "top_bottom_spread": float("nan")}
        buckets = pd.qcut(aligned.iloc[:, 0], self.quantiles, labels=False, duplicates="drop")
        grouped = aligned.iloc[:, 1].groupby(buckets).mean()
        quantile_returns = {str(int(k)): float(v) for k, v in grouped.items()}
        if len(grouped) >= 2:
            top_bottom = float(grouped.iloc[-1] - grouped.iloc[0])
        else:
            top_bottom = float("nan")
        return {"quantiles": quantile_returns, "top_bottom_spread": top_bottom}

    def _rolling_stability(self, factor: pd.Series, returns: pd.Series) -> dict[str, float]:
        aligned = pd.concat([factor, returns], axis=1).dropna()
        if len(aligned) < self.rolling_window:
            return {"mean_ic": float("nan"), "std_ic": float("nan"), "ic_ir": float("nan")}
        ic_values = []
        for i in range(self.rolling_window, len(aligned) + 1):
            window = aligned.iloc[i - self.rolling_window : i]
            ic_values.append(window.iloc[:, 0].corr(window.iloc[:, 1], method="spearman"))
        ic_series = pd.Series(ic_values).dropna()
        if ic_series.empty:
            return {"mean_ic": float("nan"), "std_ic": float("nan"), "ic_ir": float("nan")}
        mean_ic = float(ic_series.mean())
        std_ic = float(ic_series.std())
        ic_ir = float(mean_ic / std_ic) if std_ic > 0 else float("nan")
        return {"mean_ic": mean_ic, "std_ic": std_ic, "ic_ir": ic_ir}

    def _detect_future_leakage(
        self,
        factor_code: str,
        factor_func,
        df: pd.DataFrame,
    ) -> dict[str, Any]:
        if self.leakage_check_window <= 0 or len(df) <= self.leakage_check_window:
            return {"leakage": False, "reason": "insufficient_data"}
        full_values = factor_func(df.copy())
        full_series = self._extract_series(factor_code, full_values)
        truncated = df.iloc[: -self.leakage_check_window]
        trunc_values = factor_func(truncated.copy())
        trunc_series = self._extract_series(factor_code, trunc_values)
        common_index = trunc_series.index.intersection(full_series.index)
        if common_index.empty:
            return {"leakage": False, "reason": "no_overlap"}
        diff = (full_series.loc[common_index] - trunc_series.loc[common_index]).abs()
        max_diff = diff.max(skipna=True)
        if pd.isna(max_diff):
            return {"leakage": False, "reason": "no_valid_values"}
        if max_diff > self.leakage_tolerance:
            return {"leakage": True, "reason": "future_dependency", "max_diff": float(max_diff)}
        # Heuristic: direct match to future close suggests missing shift
        future_close = df["close"].shift(-1)
        aligned = pd.concat([full_series, future_close], axis=1).dropna()
        if not aligned.empty:
            mean_abs = float((aligned.iloc[:, 0] - aligned.iloc[:, 1]).abs().mean())
            if mean_abs <= self.leakage_tolerance:
                return {"leakage": True, "reason": "future_shift_match", "mean_abs_diff": mean_abs}
        return {"leakage": False, "reason": "ok", "max_diff": float(max_diff)}

    def _extract_series(
        self, factor_code: str, factor_values: pd.Series | pd.DataFrame
    ) -> pd.Series:
        if isinstance(factor_values, pd.Series):
            series = factor_values
        elif isinstance(factor_values, pd.DataFrame):
            if factor_code in factor_values.columns:
                series = factor_values[factor_code]
            elif len(factor_values.columns) == 1:
                series = factor_values.iloc[:, 0]
            else:
                raise ValueError(f"factor output missing column: {factor_code}")
        else:
            raise ValueError("unsupported factor output type")
        series.name = factor_code
        return series

    def _apply_availability_lag(self, factor: pd.Series, meta: FactorMeta) -> pd.Series:
        if meta.availability_lag < 0:
            raise ValueError("availability_lag must be >= 0")
        if meta.availability_lag == 0:
            return factor
        return factor.shift(meta.availability_lag)

    def evaluate(
        self,
        df: pd.DataFrame,
        factor_functions: dict[str, Any],
        factor_codes: Iterable[str],
        symbol: str,
        timeframe: str,
    ) -> dict[str, Any]:
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        close = df["close"]
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "symbol": symbol,
            "timeframe": timeframe,
            "prompt_policy": PROMPT_POLICY,
            "config": {
                "random_seed": self.random_seed,
                "horizons": self.horizons,
                "quantiles": self.quantiles,
                "rolling_window": self.rolling_window,
                "decay_lags": self.decay_lags,
                "leakage_check_window": self.leakage_check_window,
                "leakage_tolerance": self.leakage_tolerance,
            },
            "factors": {},
        }

        for factor_code in factor_codes:
            meta = self.registry.get_meta(factor_code)
            factor_func = factor_functions[factor_code]
            leakage = self._detect_future_leakage(factor_code, factor_func, df)
            factor_values = factor_func(df.copy())
            factor_series = self._extract_series(factor_code, factor_values)
            factor_series = self._apply_availability_lag(factor_series, meta)

            metrics = {}
            for horizon in self.horizons:
                horizon = int(horizon)
                forward_returns = self._get_forward_returns(close, horizon)
                ic = self._compute_ic(factor_series, forward_returns)
                rank_ic = ic
                decay = self._decay_profile(factor_series, forward_returns)
                layered = self._layered_returns(factor_series, forward_returns)
                stability = self._rolling_stability(factor_series, forward_returns)
                metrics[str(horizon)] = {
                    "ic": ic,
                    "rank_ic": rank_ic,
                    "decay": decay,
                    "layered_returns": layered,
                    "stability": stability,
                }

            report["factors"][factor_code] = {
                "meta": asdict(meta),
                "leakage_check": leakage,
                "metrics": metrics,
            }

        return report

    def write_reports(self, report: dict[str, Any]) -> dict[str, str]:
        root = Path(__file__).resolve().parents[3]
        reports_dir = root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        report_path = reports_dir / "factor_eval_report.json"
        summary_path = reports_dir / "factor_eval_summary.md"

        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

        summary_lines = [
            "# Factor Evaluation Summary",
            "",
            f"- prompt_policy: {PROMPT_POLICY}",
            f"- generated_at: {report['generated_at']}",
            f"- symbol: {report['symbol']}",
            f"- timeframe: {report['timeframe']}",
            "",
            "## Top Factors (abs IC)",
        ]

        rows = []
        for code, entry in report["factors"].items():
            metrics = entry["metrics"]
            if not metrics:
                continue
            first_horizon = sorted(metrics.keys(), key=int)[0]
            ic_val = metrics[first_horizon].get("ic")
            rows.append((code, ic_val))
        rows = sorted(rows, key=lambda x: abs(x[1]) if x[1] is not None else -1, reverse=True)

        for code, ic_val in rows[:10]:
            summary_lines.append(f"- {code}: ic={ic_val:.6f}")

        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
        return {"report": str(report_path), "summary": str(summary_path)}
