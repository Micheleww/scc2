# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401
"""
Negative sample: strategy layer imports multiple forbidden layers (execution/risk).

This file is intentionally violating import-scan rules and is kept as a gatekeeper fixture.
"""

from datetime import datetime
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from base_strategy import OrderProposal
from execution.gate import ExecutionGate
from features.feature_engine import FeatureEngine
from features.talib_features import BBANDS, EMA, MACD, RSI
from observability.logger import ObservabilityLogger
from risk.budget import RiskBudget
from risk.circuit import CircuitState, RiskCircuitBreaker
from state.estimator import StateEstimator
from state.labeler import StateLabeler

