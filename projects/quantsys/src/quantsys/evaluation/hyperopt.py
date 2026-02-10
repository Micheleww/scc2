"""
Hyperparameter optimization with guardrails.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.quantsys.evaluation.walkforward import WalkForwardWindow


def validate_hyperopt_report(report: dict[str, Any]) -> bool:
    """Validate the hyperopt report structure."""
    required = {
        "generated_at",
        "seed",
        "best_params",
        "search_space",
        "cv_results",
        "guardrails",
        "test_results",
    }
    return required.issubset(set(report.keys()))


@dataclass
class HyperoptResult:
    params: dict[str, Any]
    train_score: float
    val_score: float
    test_score: float
    rank: int


class HyperoptGuardrails:
    """Guardrails for hyperparameter optimization."""

    def __init__(
        self,
        min_trades: int = 10,
        max_complexity: int | None = None,
        stability_threshold: float = 0.5,
    ):
        self.min_trades = min_trades
        self.max_complexity = max_complexity
        self.stability_threshold = stability_threshold

    def validate(self, params: dict[str, Any], results: dict[str, Any]) -> bool:
        """Validate if parameters meet guardrail requirements."""
        # Check minimum number of trades
        if results.get("total_trades", 0) < self.min_trades:
            return False

        # Check complexity (if defined)
        if self.max_complexity is not None:
            complexity = self._calculate_complexity(params)
            if complexity > self.max_complexity:
                return False

        # Check stability (if available)
        if "stability" in results:
            if results["stability"] < self.stability_threshold:
                return False

        return True

    def _calculate_complexity(self, params: dict[str, Any]) -> int:
        """Calculate parameter complexity (default: count of parameters)."""

        def count_params(d: dict[str, Any]) -> int:
            count = 0
            for v in d.values():
                if isinstance(v, dict):
                    count += count_params(v)
                else:
                    count += 1
            return count

        return count_params(params)


class GridSearchOptimizer:
    """Simple grid search optimizer with guardrails."""

    def __init__(
        self,
        base_config: dict[str, Any],
        search_space: dict[str, list[Any]],
        seed: int = 42,
        guardrails: HyperoptGuardrails | None = None,
    ):
        self.base_config = base_config
        self.search_space = search_space
        self.seed = seed
        self.guardrails = guardrails or HyperoptGuardrails()
        self.param_grids = self._generate_param_grids()

    def _generate_param_grids(self) -> list[dict[str, Any]]:
        """Generate all parameter combinations from search space."""

        def recursive_grid(
            params: dict[str, Any], path: list[str], current: dict[str, Any]
        ) -> list[dict[str, Any]]:
            if not params:
                return [current]

            key, values = list(params.items())[0]
            rest = dict(list(params.items())[1:])
            grids = []

            if isinstance(values, list):
                for val in values:
                    new_current = current.copy()
                    new_path = path + [key]
                    if isinstance(val, dict):
                        sub_grids = recursive_grid(val, new_path, {})
                        for sub_grid in sub_grids:
                            new_current[key] = sub_grid
                            grids.extend(recursive_grid(rest, path, new_current))
                    else:
                        new_current[key] = val
                        grids.extend(recursive_grid(rest, path, new_current))
            elif isinstance(values, dict):
                sub_grids = recursive_grid(values, path + [key], {})
                for sub_grid in sub_grids:
                    new_current = current.copy()
                    new_current[key] = sub_grid
                    grids.extend(recursive_grid(rest, path, new_current))
            else:
                new_current = current.copy()
                new_current[key] = values
                grids.extend(recursive_grid(rest, path, new_current))

            return grids

        return recursive_grid(self.search_space, [], {})

    def _evaluate_params(
        self, params: dict[str, Any], window: WalkForwardWindow, run_strategy: Callable
    ) -> dict[str, Any]:
        """Evaluate parameters on a single window."""
        # Run on training data
        train_results = run_strategy(params, window.train_start, window.train_end)
        train_metrics = train_results.get("metrics", {})

        # Run on validation data
        val_results = run_strategy(params, window.val_start, window.val_end)
        val_metrics = val_results.get("metrics", {})

        # Apply guardrails on validation results
        if not self.guardrails.validate(params, val_results):
            return {
                "params": params,
                "train_score": -np.inf,
                "val_score": -np.inf,
                "test_score": -np.inf,
                "valid": False,
            }

        # Return scores (use negative max_drawdown as objective)
        return {
            "params": params,
            "train_score": -train_metrics.get("max_drawdown", np.inf),
            "val_score": -val_metrics.get("max_drawdown", np.inf),
            "test_score": 0.0,  # Will be filled later
            "valid": True,
        }

    def optimize(self, windows: list[WalkForwardWindow], run_strategy: Callable) -> dict[str, Any]:
        """Run grid search across multiple windows."""
        np.random.seed(self.seed)
        random.seed(self.seed)

        # Evaluate all parameter combinations on each window
        cv_results = []
        for window in windows:
            window_results = []
            for params in self.param_grids:
                result = self._evaluate_params(params, window, run_strategy)
                window_results.append(result)
            cv_results.append(window_results)

        # Aggregate results across windows
        aggregated = []
        for i, params in enumerate(self.param_grids):
            valid_count = 0
            total_train_score = 0.0
            total_val_score = 0.0

            for window_results in cv_results:
                if window_results[i]["valid"]:
                    valid_count += 1
                    total_train_score += window_results[i]["train_score"]
                    total_val_score += window_results[i]["val_score"]

            if valid_count > 0:
                aggregated.append(
                    {
                        "params": params,
                        "avg_train_score": total_train_score / valid_count,
                        "avg_val_score": total_val_score / valid_count,
                        "valid_windows": valid_count,
                        "total_windows": len(cv_results),
                    }
                )

        # Sort by validation score
        aggregated.sort(key=lambda x: x["avg_val_score"], reverse=True)

        # Get best parameters
        if not aggregated:
            raise ValueError("No valid parameter combinations found")

        best_params = aggregated[0]["params"]

        # Evaluate best params on test data for all windows
        test_results = []
        for window in windows:
            test_run = run_strategy(best_params, window.test_start, window.test_end)
            test_metrics = test_run.get("metrics", {})
            test_results.append(
                {
                    "window": {
                        "test_start": window.test_start.isoformat(),
                        "test_end": window.test_end.isoformat(),
                    },
                    "metrics": test_metrics,
                    "total_trades": test_run.get("total_trades", 0),
                }
            )

        # Generate final report
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "seed": self.seed,
            "search_space": self.search_space,
            "best_params": best_params,
            "guardrails": {
                "min_trades": self.guardrails.min_trades,
                "max_complexity": self.guardrails.max_complexity,
                "stability_threshold": self.guardrails.stability_threshold,
            },
            "cv_results": aggregated,
            "test_results": test_results,
            "summary": {
                "total_param_combinations": len(self.param_grids),
                "valid_combinations": len(aggregated),
                "best_val_score": aggregated[0]["avg_val_score"],
                "best_train_score": aggregated[0]["avg_train_score"],
            },
        }

        return report


class RandomSearchOptimizer:
    """Random search optimizer with guardrails."""

    def __init__(
        self,
        base_config: dict[str, Any],
        search_space: dict[str, Any],
        n_trials: int = 50,
        seed: int = 42,
        guardrails: HyperoptGuardrails | None = None,
    ):
        self.base_config = base_config
        self.search_space = search_space
        self.n_trials = n_trials
        self.seed = seed
        self.guardrails = guardrails or HyperoptGuardrails()

    def _sample_params(self) -> dict[str, Any]:
        """Sample parameters from the search space."""

        def sample_recursive(space: dict[str, Any]) -> dict[str, Any]:
            sampled = {}
            for key, val in space.items():
                if isinstance(val, dict):
                    sampled[key] = sample_recursive(val)
                elif isinstance(val, list):
                    sampled[key] = random.choice(val)
                elif isinstance(val, tuple) and len(val) == 2:
                    # Handle range: (min, max)
                    min_val, max_val = val
                    if isinstance(min_val, int) and isinstance(max_val, int):
                        sampled[key] = random.randint(min_val, max_val)
                    else:
                        sampled[key] = random.uniform(min_val, max_val)
                else:
                    sampled[key] = val
            return sampled

        return sample_recursive(self.search_space)

    def optimize(self, windows: list[WalkForwardWindow], run_strategy: Callable) -> dict[str, Any]:
        """Run random search across multiple windows."""
        np.random.seed(self.seed)
        random.seed(self.seed)

        # Generate parameter samples
        param_samples = [self._sample_params() for _ in range(self.n_trials)]

        # Evaluate all parameter samples on each window
        cv_results = []
        for window in windows:
            window_results = []
            for params in param_samples:
                result = self._evaluate_params(params, window, run_strategy)
                window_results.append(result)
            cv_results.append(window_results)

        # Aggregate results across windows
        aggregated = []
        for i, params in enumerate(param_samples):
            valid_count = 0
            total_train_score = 0.0
            total_val_score = 0.0

            for window_results in cv_results:
                if window_results[i]["valid"]:
                    valid_count += 1
                    total_train_score += window_results[i]["train_score"]
                    total_val_score += window_results[i]["val_score"]

            if valid_count > 0:
                aggregated.append(
                    {
                        "params": params,
                        "avg_train_score": total_train_score / valid_count,
                        "avg_val_score": total_val_score / valid_count,
                        "valid_windows": valid_count,
                        "total_windows": len(cv_results),
                    }
                )

        # Sort by validation score
        aggregated.sort(key=lambda x: x["avg_val_score"], reverse=True)

        # Get best parameters
        if not aggregated:
            raise ValueError("No valid parameter combinations found")

        best_params = aggregated[0]["params"]

        # Evaluate best params on test data for all windows
        test_results = []
        for window in windows:
            test_run = run_strategy(best_params, window.test_start, window.test_end)
            test_metrics = test_run.get("metrics", {})
            test_results.append(
                {
                    "window": {
                        "test_start": window.test_start.isoformat(),
                        "test_end": window.test_end.isoformat(),
                    },
                    "metrics": test_metrics,
                    "total_trades": test_run.get("total_trades", 0),
                }
            )

        # Generate final report
        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "seed": self.seed,
            "search_space": self.search_space,
            "best_params": best_params,
            "guardrails": {
                "min_trades": self.guardrails.min_trades,
                "max_complexity": self.guardrails.max_complexity,
                "stability_threshold": self.guardrails.stability_threshold,
            },
            "cv_results": aggregated,
            "test_results": test_results,
            "summary": {
                "total_param_combinations": self.n_trials,
                "valid_combinations": len(aggregated),
                "best_val_score": aggregated[0]["avg_val_score"],
                "best_train_score": aggregated[0]["avg_train_score"],
            },
        }

        return report

    def _evaluate_params(
        self, params: dict[str, Any], window: WalkForwardWindow, run_strategy: Callable
    ) -> dict[str, Any]:
        """Evaluate parameters on a single window."""
        # Run on training data
        train_results = run_strategy(params, window.train_start, window.train_end)
        train_metrics = train_results.get("metrics", {})

        # Run on validation data
        val_results = run_strategy(params, window.val_start, window.val_end)
        val_metrics = val_results.get("metrics", {})

        # Apply guardrails on validation results
        if not self.guardrails.validate(params, val_results):
            return {
                "params": params,
                "train_score": -np.inf,
                "val_score": -np.inf,
                "test_score": -np.inf,
                "valid": False,
            }

        # Return scores (use negative max_drawdown as objective)
        return {
            "params": params,
            "train_score": -train_metrics.get("max_drawdown", np.inf),
            "val_score": -val_metrics.get("max_drawdown", np.inf),
            "test_score": 0.0,  # Will be filled later
            "valid": True,
        }


def write_hyperopt_reports(report: dict[str, Any]) -> dict[str, str]:
    """Write hyperopt reports to disk."""
    root = Path(__file__).resolve().parents[3]
    reports_dir = root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Write JSON report
    json_path = reports_dir / "hyperopt_report.json"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")

    # Write markdown summary
    md_path = reports_dir / "hyperopt_summary.md"

    summary = report.get("summary", {})
    best_params = report.get("best_params", {})
    guardrails = report.get("guardrails", {})

    lines = [
        "# Hyperparameter Optimization Summary",
        "",
        f"- Generated: {report.get('generated_at')}",
        f"- Seed: {report.get('seed')}",
        f"- Best Validation Score: {summary.get('best_val_score', 0.0):.4f}",
        f"- Total Parameter Combinations: {summary.get('total_param_combinations', 0)}",
        f"- Valid Combinations: {summary.get('valid_combinations', 0)}",
        "",
        "## Best Parameters",
        "```json",
        json.dumps(best_params, indent=2),
        "```",
        "",
        "## Guardrails",
        f"- Min Trades: {guardrails.get('min_trades', 0)}",
        f"- Max Complexity: {guardrails.get('max_complexity', 'None')}",
        f"- Stability Threshold: {guardrails.get('stability_threshold', 0.0)}",
        "",
        "## Test Results",
    ]

    # Add test results
    for i, test_result in enumerate(report.get("test_results", [])):
        metrics = test_result.get("metrics", {})
        window = test_result.get("window", {})
        lines.extend(
            [
                f"### Window {i + 1}: {window.get('test_start')} to {window.get('test_end')}",
                f"- Total Return: {metrics.get('total_return', 0.0):.4f}",
                f"- Sharpe Ratio: {metrics.get('sharpe', 0.0):.4f}",
                f"- Max Drawdown: {metrics.get('max_drawdown', 0.0):.4f}",
                f"- Total Trades: {test_result.get('total_trades', 0)}",
                "",
            ]
        )

    md_path.write_text("\n".join(lines), encoding="utf-8")

    return {"report": str(json_path), "summary": str(md_path)}
