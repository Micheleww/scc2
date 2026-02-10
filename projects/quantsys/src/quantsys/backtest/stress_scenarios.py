"""
Stress test scenario generator for backtesting.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd


class StressScenarioGenerator:
    """
    Generator for creating stress test scenarios.
    """

    def __init__(self, base_price: float = 1000.0, initial_volatility: float = 0.02):
        """
        Initialize scenario generator with base parameters.

        Args:
            base_price: Base price for the asset
            initial_volatility: Initial daily volatility (as a fraction)
        """
        self.base_price = base_price
        self.initial_volatility = initial_volatility

    def generate_ohlcv(
        self, days: int = 30, timeframe: str = "1h", scenario: str = "normal"
    ) -> pd.DataFrame:
        """
        Generate OHLCV data for stress testing.

        Args:
            days: Number of days to generate data for
            timeframe: Timeframe of the data (e.g., '1h', '4h', '1d')
            scenario: Stress scenario type

        Returns:
            pd.DataFrame: Generated OHLCV data
        """
        # Calculate number of periods
        periods_per_day = {"1h": 24, "4h": 6, "1d": 1}[timeframe]

        total_periods = days * periods_per_day

        # Generate timestamps
        now = datetime.now()
        timestamps = [now - timedelta(days=days) + timedelta(hours=i) for i in range(total_periods)]

        # Generate base prices based on scenario
        if scenario == "normal":
            prices = self._generate_normal_prices(total_periods)
        elif scenario == "extreme_gap":
            prices = self._generate_extreme_gap_prices(total_periods)
        elif scenario == "continuous_trend":
            prices = self._generate_continuous_trend_prices(total_periods)
        elif scenario == "high_volatility":
            prices = self._generate_high_volatility_prices(total_periods)
        elif scenario == "low_liquidity":
            prices = self._generate_low_liquidity_prices(total_periods)
        else:
            raise ValueError(f"Unknown scenario: {scenario}")

        # Generate OHLCV from prices
        ohlcv = self._generate_ohlcv_from_prices(prices, timestamps)

        return ohlcv

    def _generate_normal_prices(self, periods: int) -> np.ndarray:
        """
        Generate normal price series with moderate volatility.
        """
        returns = np.random.normal(0, self.initial_volatility / np.sqrt(24), periods)
        prices = self.base_price * np.exp(np.cumsum(returns))
        return prices

    def _generate_extreme_gap_prices(self, periods: int) -> np.ndarray:
        """
        Generate price series with extreme gaps.
        """
        # Start with normal prices
        returns = np.random.normal(0, self.initial_volatility / np.sqrt(24), periods)
        prices = self.base_price * np.exp(np.cumsum(returns))

        # Add extreme gaps at random points
        gap_days = [int(periods * 0.2), int(periods * 0.5), int(periods * 0.8)]
        for day in gap_days:
            # 20-50% gap
            gap = np.random.uniform(-0.5, 0.5)  # -50% to +50% gap
            prices[day:] *= 1 + gap

        return prices

    def _generate_continuous_trend_prices(self, periods: int) -> np.ndarray:
        """
        Generate price series with continuous one-sided trend.
        """
        # Moderate trend component to avoid extreme values
        trend = np.linspace(0, self.initial_volatility * 0.5 * periods, periods)
        # Add some noise
        noise = np.random.normal(0, self.initial_volatility / np.sqrt(24), periods)
        # Combine trend and noise
        returns = trend + noise
        # Randomly decide trend direction
        direction = np.random.choice([-1, 1])

        # Calculate cumulative returns with reasonable limits
        cum_returns = np.cumsum(direction * returns)
        # Limit cumulative returns to prevent extreme values
        cum_returns = np.clip(cum_returns, -2, 2)  # Limit to -200% to +200% total return

        prices = self.base_price * np.exp(cum_returns)
        # Ensure prices stay within reasonable range
        prices = np.clip(
            prices, self.base_price * 0.1, self.base_price * 5
        )  # 10% to 500% of base price

        return prices

    def _generate_high_volatility_prices(self, periods: int) -> np.ndarray:
        """
        Generate price series with sudden increase in volatility.
        """
        # Start with normal volatility
        volatility = np.full(periods, self.initial_volatility / np.sqrt(24))
        # Increase volatility dramatically after halfway point
        volatility[int(periods * 0.5) :] *= 5  # 5x volatility increase
        # Generate returns with time-varying volatility
        returns = np.random.normal(0, volatility, periods)
        prices = self.base_price * np.exp(np.cumsum(returns))

        return prices

    def _generate_low_liquidity_prices(self, periods: int) -> np.ndarray:
        """
        Generate price series with low liquidity characteristics.
        """
        # Start with normal prices
        returns = np.random.normal(0, self.initial_volatility / np.sqrt(24), periods)
        prices = self.base_price * np.exp(np.cumsum(returns))

        # Add sudden large moves (simulating low liquidity)
        for i in range(10, periods, 20):
            # Large price movement
            move = np.random.normal(0, self.initial_volatility * 2)
            prices[i] *= 1 + move
            # Subsequent small movement (price gets stuck)
            prices[i + 1 : i + 5] = prices[i] * np.exp(
                np.random.normal(0, self.initial_volatility / 10, 4)
            )

        return prices

    def _generate_ohlcv_from_prices(self, prices: np.ndarray, timestamps: list) -> pd.DataFrame:
        """
        Generate OHLCV data from a price series.

        Args:
            prices: Price series (close prices)
            timestamps: List of timestamps

        Returns:
            pd.DataFrame: OHLCV data
        """
        ohlcv = []

        for i, (timestamp, close) in enumerate(zip(timestamps, prices)):
            if i == 0:
                open = close * np.random.uniform(0.999, 1.001)
            else:
                open = prices[i - 1] * np.random.uniform(0.999, 1.001)

            # Generate high and low with some volatility
            volatility = self.initial_volatility / np.sqrt(24)
            high = max(open, close) * np.random.uniform(1.0, 1.0 + volatility)
            low = min(open, close) * np.random.uniform(1.0 - volatility, 1.0)

            # Generate volume (random but correlated with volatility)
            volume = np.random.uniform(1000, 10000) * (1 + abs(close - open) / open)

            ohlcv.append(
                {
                    "timestamp": timestamp,
                    "open": open,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )

        df = pd.DataFrame(ohlcv)
        df.set_index("timestamp", inplace=True)
        return df

    def get_scenarios(self) -> list[str]:
        """
        Get list of available stress scenarios.

        Returns:
            list[str]: Available scenario names
        """
        return ["normal", "extreme_gap", "continuous_trend", "high_volatility", "low_liquidity"]

    def generate_stress_test_config(self, scenario: str) -> dict:
        """
        Generate backtest config for stress testing a specific scenario.

        Args:
            scenario: Stress scenario name

        Returns:
            dict: Backtest config with scenario-specific settings
        """
        base_config = {
            "backtest": {
                "initial_capital": 10000,
                "commission": 0.001,
                "maker_fee": 0.0002,
                "taker_fee": 0.0005,
                "risk_free_rate": 0.0,
                "max_trades": 10000,
                "max_drawdown_limit": 0.5,  # Allow larger drawdowns for stress testing
                "risk_per_trade": 0.02,
                "max_leverage": 10,
                "use_local_data_only": True,
            }
        }

        # Add scenario-specific settings
        if scenario == "low_liquidity":
            # Increase slippage and funding rates for low liquidity
            base_config["backtest"]["slippage"] = 0.05  # 5% slippage
            base_config["backtest"]["funding_rate"] = 0.001  # Higher funding rate
        elif scenario == "high_volatility":
            # Increase slippage for high volatility
            base_config["backtest"]["slippage"] = 0.02  # 2% slippage

        return base_config
