"""
Liquidation model for perpetual contracts.
"""

from __future__ import annotations

from dataclasses import dataclass

from .margin_model import MarginState


@dataclass
class LiquidationEvent:
    """
    Liquidation event details.
    """

    timestamp: str
    position_qty: float
    position_side: int
    entry_price: float
    liquidation_price: float
    equity: float
    maintenance_margin: float
    margin_ratio: float
    liquidation_reason: str
    is_liquidated: bool


class LiquidationModel:
    """
    Liquidation model for perpetual contracts.
    """

    def __init__(self, liquidation_ratio: float = 0.8) -> None:
        """
        Initialize liquidation model parameters.

        Args:
            liquidation_ratio: Equity / maintenance_margin ratio that triggers liquidation
        """
        self.liquidation_ratio = liquidation_ratio

    def check_liquidation(self, margin_state: MarginState) -> tuple[bool, float]:
        """
        Check if liquidation is required based on current margin state.

        Args:
            margin_state: Current margin state

        Returns:
            tuple[bool, float]: (True if liquidation is required, liquidation price)
        """
        if margin_state.position_qty == 0:
            return False, 0.0

        # Check if margin ratio is below liquidation threshold
        if margin_state.margin_ratio < self.liquidation_ratio:
            # Calculate liquidation price
            liquidation_price = self.calculate_liquidation_price(margin_state)
            return True, liquidation_price

        return False, 0.0

    def calculate_liquidation_price(self, margin_state: MarginState) -> float:
        """
        Calculate liquidation price based on current margin state.

        Args:
            margin_state: Current margin state

        Returns:
            float: Liquidation price
        """
        if margin_state.position_qty == 0:
            return 0.0

        # For long position: liquidation occurs when equity <= maintenance_margin
        # Equity = balance + (current_price - entry_price) * position_qty
        # Maintenance_margin = position_qty * liquidation_price * maintenance_margin_rate
        # Solve for current_price when equity = maintenance_margin * liquidation_ratio

        if margin_state.position_side == 1:  # Long position
            # Equity = balance + (liquidation_price - entry_price) * position_qty
            # Maintenance_margin = position_qty * liquidation_price * maintenance_margin_rate
            # Equity = maintenance_margin * liquidation_ratio

            numerator = (
                (margin_state.maintenance_margin * self.liquidation_ratio)
                - margin_state.balance
                + (margin_state.entry_price * margin_state.position_qty)
            )
            denominator = margin_state.position_qty * (
                1
                - self.liquidation_ratio
                * margin_state.maintenance_margin
                / margin_state.notional_value
            )

            if denominator <= 0:
                # Safety check to avoid division by zero or negative denominator
                liquidation_price = margin_state.entry_price * (1 - 0.01)  # 1% below entry price
            else:
                liquidation_price = numerator / denominator
                # Ensure liquidation price is below current price for long position
                liquidation_price = min(liquidation_price, margin_state.current_price * 0.99)
        else:  # Short position
            # Equity = balance + (entry_price - liquidation_price) * position_qty
            # Maintenance_margin = position_qty * liquidation_price * maintenance_margin_rate
            # Equity = maintenance_margin * liquidation_ratio

            numerator = (
                (margin_state.maintenance_margin * self.liquidation_ratio)
                - margin_state.balance
                + (margin_state.entry_price * margin_state.position_qty)
            )
            denominator = margin_state.position_qty * (
                -1
                + self.liquidation_ratio
                * margin_state.maintenance_margin
                / margin_state.notional_value
            )

            if denominator >= 0:
                # Safety check to avoid division by zero or positive denominator for short
                liquidation_price = margin_state.entry_price * (1 + 0.01)  # 1% above entry price
            else:
                liquidation_price = numerator / denominator
                # Ensure liquidation price is above current price for short position
                liquidation_price = max(liquidation_price, margin_state.current_price * 1.01)

        return max(liquidation_price, 0.01)  # Ensure liquidation price is positive

    def execute_liquidation(self, margin_state: MarginState, timestamp: str) -> LiquidationEvent:
        """
        Execute liquidation and return liquidation event details.

        Args:
            margin_state: Current margin state
            timestamp: Timestamp of liquidation event

        Returns:
            LiquidationEvent: Liquidation event details
        """
        is_liquidated, liquidation_price = self.check_liquidation(margin_state)

        if is_liquidated:
            reason = f"Margin ratio ({margin_state.margin_ratio:.4f}) below liquidation threshold ({self.liquidation_ratio:.2f})"
        else:
            reason = "Margin ratio above liquidation threshold"

        return LiquidationEvent(
            timestamp=timestamp,
            position_qty=margin_state.position_qty,
            position_side=margin_state.position_side,
            entry_price=margin_state.entry_price,
            liquidation_price=liquidation_price,
            equity=margin_state.equity,
            maintenance_margin=margin_state.maintenance_margin,
            margin_ratio=margin_state.margin_ratio,
            liquidation_reason=reason,
            is_liquidated=is_liquidated,
        )

    def calculate_risk_level(self, margin_state: MarginState) -> str:
        """
        Calculate risk level based on margin ratio.

        Args:
            margin_state: Current margin state

        Returns:
            str: Risk level ("safe", "warning", "danger", "liquidation")
        """
        if margin_state.margin_ratio < self.liquidation_ratio:
            return "liquidation"
        elif margin_state.margin_ratio < self.liquidation_ratio * 1.2:
            return "danger"
        elif margin_state.margin_ratio < self.liquidation_ratio * 1.5:
            return "warning"
        else:
            return "safe"
