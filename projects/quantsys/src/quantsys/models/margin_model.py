"""
Margin and leverage model for perpetual contracts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MarginState:
    """
    Margin state at a specific point in time.
    """

    initial_capital: float
    balance: float
    position_qty: float
    position_side: int
    entry_price: float
    current_price: float
    margin_used: float
    available_balance: float
    equity: float
    notional_value: float
    leverage: float
    maintenance_margin: float
    margin_ratio: float
    liquidation_ratio: float = 0.8


class MarginModel:
    """
    Margin and leverage calculation model for perpetual contracts.
    """

    def __init__(
        self,
        initial_margin_rate: float = 0.05,  # 5% initial margin requirement
        maintenance_margin_rate: float = 0.02,  # 2% maintenance margin requirement
        liquidation_ratio: float = 0.8,  # Equity / maintenance_margin < 0.8 triggers liquidation
        max_leverage: float = 10.0,
    ) -> None:
        """
        Initialize margin model parameters.

        Args:
            initial_margin_rate: Initial margin requirement ratio
            maintenance_margin_rate: Maintenance margin requirement ratio
            liquidation_ratio: Equity / maintenance_margin ratio that triggers liquidation
            max_leverage: Maximum allowed leverage
        """
        self.initial_margin_rate = initial_margin_rate
        self.maintenance_margin_rate = maintenance_margin_rate
        self.liquidation_ratio = liquidation_ratio
        self.max_leverage = max_leverage

    def calculate_margin_state(
        self,
        initial_capital: float,
        balance: float,
        position_qty: float,
        position_side: int,
        entry_price: float,
        current_price: float,
    ) -> MarginState:
        """
        Calculate current margin state based on position and price.

        Args:
            initial_capital: Initial capital amount
            balance: Current available balance
            position_qty: Position quantity
            position_side: Position side (1 for long, -1 for short)
            entry_price: Entry price of the position
            current_price: Current market price

        Returns:
            MarginState: Current margin state
        """
        # Calculate notional value of the position
        notional_value = position_qty * current_price

        # Calculate PnL
        if position_qty == 0:
            pnl = 0.0
        else:
            pnl = position_side * position_qty * (current_price - entry_price)

        # Calculate equity
        equity = balance + pnl

        if position_qty == 0:
            # No position
            margin_used = 0.0
            available_balance = balance
            leverage = 0.0
            maintenance_margin = 0.0
            margin_ratio = 0.0
        else:
            # With position
            # Calculate margin used (initial margin)
            margin_used = notional_value * self.initial_margin_rate

            # Calculate available balance
            available_balance = balance - margin_used + pnl

            # Calculate leverage
            leverage = notional_value / margin_used if margin_used > 0 else 0.0
            leverage = min(leverage, self.max_leverage)  # Apply max leverage limit

            # Calculate maintenance margin
            maintenance_margin = notional_value * self.maintenance_margin_rate

            # Calculate margin ratio (equity / maintenance_margin)
            margin_ratio = equity / maintenance_margin if maintenance_margin > 0 else 0.0

        return MarginState(
            initial_capital=initial_capital,
            balance=balance,
            position_qty=position_qty,
            position_side=position_side,
            entry_price=entry_price,
            current_price=current_price,
            margin_used=margin_used,
            available_balance=available_balance,
            equity=equity,
            notional_value=notional_value,
            leverage=leverage,
            maintenance_margin=maintenance_margin,
            margin_ratio=margin_ratio,
            liquidation_ratio=self.liquidation_ratio,
        )

    def calculate_initial_margin(self, notional_value: float) -> float:
        """
        Calculate initial margin required for a position.

        Args:
            notional_value: Notional value of the position

        Returns:
            float: Initial margin required
        """
        return notional_value * self.initial_margin_rate

    def calculate_maintenance_margin(self, notional_value: float) -> float:
        """
        Calculate maintenance margin for a position.

        Args:
            notional_value: Notional value of the position

        Returns:
            float: Maintenance margin required
        """
        return notional_value * self.maintenance_margin_rate

    def is_margin_sufficient(self, available_balance: float, required_margin: float) -> bool:
        """
        Check if available balance is sufficient for required margin.

        Args:
            available_balance: Current available balance
            required_margin: Required margin for the trade

        Returns:
            bool: True if margin is sufficient, False otherwise
        """
        return available_balance >= required_margin

    def calculate_max_position_size(self, balance: float, price: float, leverage: float) -> float:
        """
        Calculate maximum position size based on balance, price, and leverage.

        Args:
            balance: Current balance
            price: Current market price
            leverage: Desired leverage

        Returns:
            float: Maximum position size
        """
        # Limit leverage to maximum allowed
        leverage = min(leverage, self.max_leverage)

        if leverage <= 0 or price <= 0:
            return 0.0

        # Calculate max notional value based on balance and leverage
        max_notional = balance * leverage

        # Calculate max position size
        max_position_size = max_notional / price

        return max_position_size
