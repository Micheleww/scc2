"""
Negative sample: strategy layer illegally imports execution layer.

This file is a fixture for gatekeeper import-scan rules (e.g., D01/D07).
It MUST NOT live under src/ or user_data/strategies/, otherwise repo-wide import-scan will fail permanently.
"""

from src.quantsys.execution.order_execution import OrderExecution


def illegal_strategy_function():
    order_exec = OrderExecution(config={})
    return order_exec

