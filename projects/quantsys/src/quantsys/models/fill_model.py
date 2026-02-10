"""
Minimal fill model for backtests.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FillResult:
    filled: bool
    fill_price: float | None
    fill_qty: float
    base_price: float | None
    reason: str


class FillModel:
    def __init__(self, slippage_bps: float = 0.0) -> None:
        self.slippage_bps = slippage_bps

    def _apply_slippage(self, price: float, side: int) -> float:
        if price <= 0 or self.slippage_bps <= 0:
            return price
        slip = self.slippage_bps / 10000.0
        if side > 0:
            return price * (1 + slip)
        return price * (1 - slip)

    def fill_order(
        self,
        order_type: str,
        side: int,
        qty: float,
        limit_price: float | None,
        stop_price: float | None,
        next_open: float,
        next_high: float,
        next_low: float,
    ) -> FillResult:
        if qty <= 0:
            return FillResult(False, None, 0.0, None, "zero_qty")

        order_type = order_type.lower()

        if order_type == "market":
            base_price = next_open
            fill_price = self._apply_slippage(base_price, side)
            return FillResult(True, fill_price, qty, base_price, "market")

        if order_type == "limit":
            if limit_price is None:
                return FillResult(False, None, 0.0, None, "limit_missing_price")
            if next_low <= limit_price <= next_high:
                return FillResult(True, limit_price, qty, limit_price, "limit_touch")
            return FillResult(False, None, 0.0, None, "limit_not_touched")

        if order_type == "stop":
            if stop_price is None:
                return FillResult(False, None, 0.0, None, "stop_missing_price")
            if side > 0:
                triggered = next_high >= stop_price
                if not triggered:
                    return FillResult(False, None, 0.0, None, "stop_not_triggered")
                base_price = max(stop_price, next_open)
            else:
                triggered = next_low <= stop_price
                if not triggered:
                    return FillResult(False, None, 0.0, None, "stop_not_triggered")
                base_price = min(stop_price, next_open)
            fill_price = self._apply_slippage(base_price, side)
            return FillResult(True, fill_price, qty, base_price, "stop_triggered")

        return FillResult(False, None, 0.0, None, "unsupported_order_type")
