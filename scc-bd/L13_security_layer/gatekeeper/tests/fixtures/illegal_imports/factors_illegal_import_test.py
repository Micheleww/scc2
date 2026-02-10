"""
Negative sample: factor layer illegally imports execution layer.

This file is a fixture for gatekeeper import-scan rules (e.g., D04/D09).
It MUST NOT live under src/ or user_data/strategies/, otherwise repo-wide import-scan will fail permanently.
"""

from src.quantsys.execution.order_execution import OrderExecution


def illegal_factor_function():
    order_exec = OrderExecution(config={})
    return order_exec

