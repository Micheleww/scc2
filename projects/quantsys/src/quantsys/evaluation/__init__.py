"""
Evaluation layer modules.
"""

from .hyperopt import (
    GridSearchOptimizer,
    HyperoptGuardrails,
    RandomSearchOptimizer,
    validate_hyperopt_report,
    write_hyperopt_reports,
)
from .metrics import (
    compute_equity_metrics,
    distribution_summary,
    ranking_correlations,
    spearman_rank_correlation,
    topk_intersection_rate,
)
from .walkforward import (
    WalkForwardRunner,
    WalkForwardSplitter,
    WalkForwardWindow,
    validate_report_structure,
)

__all__ = [
    # Metrics
    "compute_equity_metrics",
    "distribution_summary",
    "ranking_correlations",
    "spearman_rank_correlation",
    "topk_intersection_rate",
    # Walkforward
    "WalkForwardSplitter",
    "WalkForwardWindow",
    "WalkForwardRunner",
    "validate_report_structure",
    # Hyperopt
    "HyperoptGuardrails",
    "GridSearchOptimizer",
    "RandomSearchOptimizer",
    "write_hyperopt_reports",
    "validate_hyperopt_report",
]
