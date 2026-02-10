"""
Walk-forward evaluation pipeline with OOS metrics and strategy ranking.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from src.quantsys.backtest.backtest_engine import BacktestEngine
from src.quantsys.evaluation.metrics import (
    compute_equity_metrics,
    distribution_summary,
    ranking_correlations,
    topk_intersection_rate,
)


def validate_report_structure(report: dict[str, Any]) -> bool:
    required_top = {"generated_at", "seed", "strategies", "windows", "stability"}
    if not required_top.issubset(set(report.keys())):
        return False
    if not isinstance(report.get("windows"), list):
        return False
    if not isinstance(report.get("stability"), dict):
        return False
    return True


@dataclass
class WalkForwardWindow:
    train_start: datetime
    train_end: datetime
    val_start: datetime | None
    val_end: datetime | None
    test_start: datetime
    test_end: datetime


class WalkForwardSplitter:
    @staticmethod
    def fixed_ratio(
        start: datetime,
        end: datetime,
        train_ratio: float,
        val_ratio: float,
        test_ratio: float,
    ) -> WalkForwardWindow:
        total_days = (end - start).days
        train_days = int(total_days * train_ratio)
        val_days = int(total_days * val_ratio)
        test_days = total_days - train_days - val_days
        train_end = start + timedelta(days=train_days)
        val_end = train_end + timedelta(days=val_days)
        test_end = val_end + timedelta(days=test_days)
        return WalkForwardWindow(
            train_start=start,
            train_end=train_end,
            val_start=train_end,
            val_end=val_end if val_ratio > 0 else None,
            test_start=val_end if val_ratio > 0 else train_end,
            test_end=test_end,
        )

    @staticmethod
    def rolling_windows(
        start: datetime,
        end: datetime,
        train_days: int,
        val_days: int,
        test_days: int,
        step_days: int,
    ) -> list[WalkForwardWindow]:
        windows = []
        cursor = start
        while True:
            train_start = cursor
            train_end = train_start + timedelta(days=train_days)
            val_start = train_end
            val_end = val_start + timedelta(days=val_days) if val_days > 0 else None
            test_start = val_end if val_days > 0 else train_end
            test_end = test_start + timedelta(days=test_days)
            if test_end > end:
                break
            windows.append(
                WalkForwardWindow(
                    train_start=train_start,
                    train_end=train_end,
                    val_start=val_start if val_days > 0 else None,
                    val_end=val_end,
                    test_start=test_start,
                    test_end=test_end,
                )
            )
            cursor = cursor + timedelta(days=step_days)
        return windows


class WalkForwardRunner:
    def __init__(
        self, base_config: dict[str, Any], strategies: list[dict[str, Any]], seed: int = 42
    ) -> None:
        self.base_config = base_config
        self.strategies = strategies
        self.seed = seed
        np.random.seed(seed)
        self.data_info = self._get_data_info()

    def _get_data_info(self) -> dict[str, Any]:
        data_path = self.base_config.get("backtest", {}).get("data_path")
        if not data_path:
            return {}
        try:
            path = Path(data_path)
            return {
                "data_path": str(path),
                "last_modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }
        except OSError:
            return {"data_path": data_path, "last_modified": None}

    def _run_window(self, window: WalkForwardWindow) -> dict[str, Any]:
        window_results = {"train": {}, "val": {}, "test": {}}
        for strategy in self.strategies:
            strat_name = strategy["name"]
            window_results["train"][strat_name] = self._run_strategy(
                strategy, window.train_start, window.train_end
            )
            if window.val_start and window.val_end:
                window_results["val"][strat_name] = self._run_strategy(
                    strategy, window.val_start, window.val_end
                )
            window_results["test"][strat_name] = self._run_strategy(
                strategy, window.test_start, window.test_end
            )
        return window_results

    def _run_strategy(
        self, strategy: dict[str, Any], start: datetime, end: datetime
    ) -> dict[str, Any]:
        config = copy.deepcopy(self.base_config)
        config["backtest"]["start_date"] = start.strftime("%Y-%m-%d")
        config["backtest"]["end_date"] = end.strftime("%Y-%m-%d")
        config["backtest"]["random_seed"] = self.seed
        config["backtest"]["use_local_data_only"] = True

        engine = BacktestEngine(config)
        result = engine.run_backtest(
            strategy_file=strategy.get("strategy_file"),
            strategy_class=strategy.get("strategy_class"),
            strategy_id=strategy.get("strategy_id"),
        )
        if result is None:
            return {"metrics": {}, "raw": None}
        metrics = compute_equity_metrics(
            result.get("equity_curve", []), result.get("positions", [])
        )
        metrics.update(
            {
                "total_trades": result.get("total_trades", 0),
                "win_rate": result.get("win_rate", 0.0),
            }
        )
        return {"metrics": metrics, "raw": result}

    def run(self, windows: list[WalkForwardWindow]) -> dict[str, Any]:
        window_outputs = []
        rankings = []
        for window in windows:
            results = self._run_window(window)
            test_metrics = {
                name: res["metrics"] for name, res in results["test"].items() if res["metrics"]
            }
            ranking = sorted(
                test_metrics.keys(), key=lambda n: test_metrics[n]["total_return"], reverse=True
            )
            rankings.append(ranking)
            window_outputs.append(
                {
                    "window": {
                        "train_start": window.train_start.isoformat(),
                        "train_end": window.train_end.isoformat(),
                        "val_start": window.val_start.isoformat() if window.val_start else None,
                        "val_end": window.val_end.isoformat() if window.val_end else None,
                        "test_start": window.test_start.isoformat(),
                        "test_end": window.test_end.isoformat(),
                    },
                    "results": results,
                    "ranking": ranking,
                }
            )

        stability = self._stability_summary(window_outputs, rankings)
        return {
            "generated_at": datetime.utcnow().isoformat(),
            "seed": self.seed,
            "strategies": self.strategies,
            "config_summary": {
                "symbol": self.base_config.get("backtest", {}).get("symbol"),
                "timeframe": self.base_config.get("backtest", {}).get("timeframe"),
            },
            "data_info": self.data_info,
            "windows": window_outputs,
            "stability": stability,
        }

    def _stability_summary(
        self, windows: list[dict[str, Any]], rankings: list[list[str]]
    ) -> dict[str, Any]:
        returns = []
        drawdowns = []
        turnovers = []
        trade_counts = []
        win_rates = []

        for window in windows:
            test_results = window["results"]["test"]
            for _, payload in test_results.items():
                metrics = payload.get("metrics", {})
                if metrics:
                    returns.append(metrics.get("total_return", 0.0))
                    drawdowns.append(metrics.get("max_drawdown", 0.0))
                    turnovers.append(metrics.get("turnover", 0.0))
                    trade_counts.append(metrics.get("total_trades", 0))
                    win_rates.append(metrics.get("win_rate", 0.0))

        # Calculate strategy-wise stability metrics
        strategy_metrics = {}
        for window in windows:
            test_results = window["results"]["test"]
            for strat_name, payload in test_results.items():
                metrics = payload.get("metrics", {})
                if metrics:
                    if strat_name not in strategy_metrics:
                        strategy_metrics[strat_name] = {
                            "returns": [],
                            "drawdowns": [],
                            "turnovers": [],
                            "trade_counts": [],
                            "win_rates": [],
                        }
                    strategy_metrics[strat_name]["returns"].append(metrics.get("total_return", 0.0))
                    strategy_metrics[strat_name]["drawdowns"].append(
                        metrics.get("max_drawdown", 0.0)
                    )
                    strategy_metrics[strat_name]["turnovers"].append(metrics.get("turnover", 0.0))
                    strategy_metrics[strat_name]["trade_counts"].append(
                        metrics.get("total_trades", 0)
                    )
                    strategy_metrics[strat_name]["win_rates"].append(metrics.get("win_rate", 0.0))

        # Calculate stability scores for each strategy
        strategy_stability = {}
        for strat_name, metrics in strategy_metrics.items():
            # Stability score: lower variation = higher stability (0-1 range)
            return_std = np.std(metrics["returns"]) if metrics["returns"] else 0
            drawdown_std = np.std(metrics["drawdowns"]) if metrics["drawdowns"] else 0
            turnover_std = np.std(metrics["turnovers"]) if metrics["turnovers"] else 0

            # Normalize standard deviations (simple approach: 1/(1+std))
            return_stability = 1.0 / (1.0 + return_std) if return_std > 0 else 1.0
            drawdown_stability = 1.0 / (1.0 + drawdown_std) if drawdown_std > 0 else 1.0
            turnover_stability = 1.0 / (1.0 + turnover_std) if turnover_std > 0 else 1.0

            # Combine stability metrics (equal weights)
            overall_stability = (return_stability + drawdown_stability + turnover_stability) / 3.0

            strategy_stability[strat_name] = {
                "overall_stability": float(overall_stability),
                "return_stability": float(return_stability),
                "drawdown_stability": float(drawdown_stability),
                "turnover_stability": float(turnover_stability),
                "return_distribution": distribution_summary(metrics["returns"]),
                "drawdown_distribution": distribution_summary(metrics["drawdowns"]),
                "turnover_distribution": distribution_summary(metrics["turnovers"]),
                "trade_count_distribution": distribution_summary(metrics["trade_counts"]),
                "win_rate_distribution": distribution_summary(metrics["win_rates"]),
            }

        return {
            "topk_intersection_rate": topk_intersection_rate(rankings, k=3),
            "rank_correlations": ranking_correlations(rankings),
            "aggregate": {
                "return_distribution": distribution_summary(returns),
                "drawdown_distribution": distribution_summary(drawdowns),
                "turnover_distribution": distribution_summary(turnovers),
                "trade_count_distribution": distribution_summary(trade_counts),
                "win_rate_distribution": distribution_summary(win_rates),
            },
            "strategy_stability": strategy_stability,
        }

    def write_reports(self, report: dict[str, Any]) -> dict[str, str]:
        root = Path(__file__).resolve().parents[3]
        reports_dir = root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Create unique filename with timestamp to avoid overwriting
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = reports_dir / f"walkforward_report_{timestamp}.json"
        md_path = reports_dir / f"walkforward_summary_{timestamp}.md"

        # Also update the latest symlink or file
        latest_json = reports_dir / "walkforward_report_latest.json"
        latest_md = reports_dir / "walkforward_summary_latest.md"

        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

        # Update latest files
        if latest_json.exists():
            latest_json.unlink()
        latest_json.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

        # Generate comprehensive markdown report
        stability = report.get("stability", {})

        lines = [
            "# Walk-Forward Strategy Evaluation Report",
            "",
            f"**Generated At**: {report.get('generated_at')}",
            f"**Seed**: {report.get('seed')}",
            f"**Data Info**: {json.dumps(report.get('data_info', {}), indent=2)}",
            f"**Config**: {json.dumps(report.get('config_summary', {}), indent=2)}",
            "",
            "## Summary Statistics",
            "",
            "### Overall Performance",
        ]

        # Add aggregate metrics
        aggregate = stability.get("aggregate", {})
        lines.extend(
            [
                f"- **Top-k Intersection Rate**: {stability.get('topk_intersection_rate', 0.0):.4f}",
                "",
                "### Return Distribution",
                f"- Mean: {aggregate.get('return_distribution', {}).get('mean', 0.0):.4f}",
                f"- Median: {aggregate.get('return_distribution', {}).get('p50', 0.0):.4f}",
                f"- Min: {aggregate.get('return_distribution', {}).get('min', 0.0):.4f}",
                f"- Max: {aggregate.get('return_distribution', {}).get('max', 0.0):.4f}",
                "",
                "### Drawdown Distribution",
                f"- Mean: {aggregate.get('drawdown_distribution', {}).get('mean', 0.0):.4f}",
                f"- Median: {aggregate.get('drawdown_distribution', {}).get('p50', 0.0):.4f}",
                f"- Min: {aggregate.get('drawdown_distribution', {}).get('min', 0.0):.4f}",
                f"- Max: {aggregate.get('drawdown_distribution', {}).get('max', 0.0):.4f}",
                "",
                "### Turnover Distribution",
                f"- Mean: {aggregate.get('turnover_distribution', {}).get('mean', 0.0):.4f}",
                f"- Median: {aggregate.get('turnover_distribution', {}).get('p50', 0.0):.4f}",
                f"- Min: {aggregate.get('turnover_distribution', {}).get('min', 0.0):.4f}",
                f"- Max: {aggregate.get('turnover_distribution', {}).get('max', 0.0):.4f}",
                "",
                "### Trade Count Distribution",
                f"- Mean: {aggregate.get('trade_count_distribution', {}).get('mean', 0.0):.2f}",
                f"- Median: {aggregate.get('trade_count_distribution', {}).get('p50', 0.0):.2f}",
                f"- Min: {aggregate.get('trade_count_distribution', {}).get('min', 0.0):.2f}",
                f"- Max: {aggregate.get('trade_count_distribution', {}).get('max', 0.0):.2f}",
                "",
                "## Strategy Stability Analysis",
                "",
                "### Strategy Rankings Stability",
                f"- **Top-k Intersection Rate**: {stability.get('topk_intersection_rate', 0.0):.4f}",
                f"- **Rank Correlations**: {json.dumps(stability.get('rank_correlations', []), indent=2)}",
                "",
                "### Strategy-wise Metrics",
            ]
        )

        # Add strategy-wise metrics
        strategy_stability = stability.get("strategy_stability", {})
        for strat_name, metrics in sorted(
            strategy_stability.items(),
            key=lambda x: x[1].get("overall_stability", 0.0),
            reverse=True,
        ):
            lines.extend(
                [
                    f"#### {strat_name}",
                    f"- **Overall Stability Score**: {metrics.get('overall_stability', 0.0):.4f}",
                    f"- **Return Stability**: {metrics.get('return_stability', 0.0):.4f}",
                    f"- **Drawdown Stability**: {metrics.get('drawdown_stability', 0.0):.4f}",
                    f"- **Turnover Stability**: {metrics.get('turnover_stability', 0.0):.4f}",
                    "",
                    "  **Return Distribution**:",
                    f"  - Mean: {metrics.get('return_distribution', {}).get('mean', 0.0):.4f}",
                    f"  - Median: {metrics.get('return_distribution', {}).get('p50', 0.0):.4f}",
                    f"  - Min: {metrics.get('return_distribution', {}).get('min', 0.0):.4f}",
                    f"  - Max: {metrics.get('return_distribution', {}).get('max', 0.0):.4f}",
                    "",
                    "  **Drawdown Distribution**:",
                    f"  - Mean: {metrics.get('drawdown_distribution', {}).get('mean', 0.0):.4f}",
                    f"  - Median: {metrics.get('drawdown_distribution', {}).get('p50', 0.0):.4f}",
                    "",
                    "  **Turnover Distribution**:",
                    f"  - Mean: {metrics.get('turnover_distribution', {}).get('mean', 0.0):.4f}",
                    "",
                    "  **Trade Count Distribution**:",
                    f"  - Mean: {metrics.get('trade_count_distribution', {}).get('mean', 0.0):.2f}",
                    "",
                ]
            )

        # Add window details
        lines.extend(
            [
                "## Window Details",
                "",
            ]
        )

        for i, window in enumerate(report.get("windows", [])):
            window_info = window.get("window", {})
            lines.extend(
                [
                    f"### Window {i + 1}",
                    f"- **Train**: {window_info.get('train_start')} to {window_info.get('train_end')}",
                    f"- **Val**: {window_info.get('val_start', 'N/A')} to {window_info.get('val_end', 'N/A')}",
                    f"- **Test**: {window_info.get('test_start')} to {window_info.get('test_end')}",
                    "",
                ]
            )

        # Add risk notes
        lines.extend(
            [
                "## Risk Notes",
                "",
                "- Rankings stability depends on window boundaries; review rank correlations carefully.",
                "- Worst OOS windows should be inspected for regime shifts or data gaps.",
                "- High turnover strategies may have higher transaction costs in live trading.",
                "- Strategies with high overall stability scores tend to perform more consistently across market regimes.",
                "",
            ]
        )

        md_path.write_text("\n".join(lines), encoding="utf-8")

        # Update latest markdown
        if latest_md.exists():
            latest_md.unlink()
        latest_md.write_text("\n".join(lines), encoding="utf-8")

        return {
            "report": str(json_path),
            "summary": str(md_path),
            "latest_report": str(latest_json),
            "latest_summary": str(latest_md),
        }
