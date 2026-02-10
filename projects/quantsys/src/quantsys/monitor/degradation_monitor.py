#!/usr/bin/env python3
"""
Strategy Degradation Monitor

Implements rolling window metrics (returns/drawdown/winrate/turnover),
triggers BLOCKED or paper downgrade on degradation,
and logs evidence.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            f"logs/degradation_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("degradation_monitor")


class StrategyStatus(Enum):
    """Strategy status enumeration."""

    ACTIVE = "active"
    BLOCKED = "blocked"
    PAPER = "paper"


@dataclass
class DegradationThresholds:
    """Degradation thresholds configuration."""

    min_return: float = -0.05
    max_drawdown: float = 0.15
    min_winrate: float = 0.45
    max_turnover: float = 0.5
    window_size: int = 20

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WindowMetrics:
    """Rolling window metrics."""

    window_start: str
    window_end: str
    window_size: int
    total_trades: int
    total_return: float
    max_drawdown: float
    win_rate: float
    turnover: float
    metrics_hash: str


@dataclass
class DegradationEvent:
    """Degradation event record."""

    timestamp: str
    strategy_code: str
    event_type: str  # "blocked" or "paper_downgrade"
    old_status: str
    new_status: str
    trigger_metric: str
    trigger_value: float
    threshold_value: float
    window_metrics: dict[str, Any]
    reason: str
    event_hash: str


class StrategyDegradationMonitor:
    """
    Strategy degradation monitor.

    Monitors rolling window metrics (returns/drawdown/winrate/turnover),
    triggers BLOCKED or paper downgrade on degradation,
    and logs evidence.
    """

    def __init__(self, strategy_code: str, thresholds: DegradationThresholds | None = None):
        """
        Initialize degradation monitor.

        Args:
            strategy_code: Strategy code
            thresholds: Degradation thresholds configuration
        """
        self.strategy_code = strategy_code
        self.thresholds = thresholds or DegradationThresholds()
        self.current_status = StrategyStatus.ACTIVE
        self.trade_history: list[dict[str, Any]] = []
        self.degradation_events: list[DegradationEvent] = []
        self.current_window_metrics: WindowMetrics | None = None

        logger.info(f"Degradation Monitor initialized for strategy: {strategy_code}")
        logger.info(f"Thresholds: {self.thresholds.to_dict()}")

    def _calculate_metrics_hash(self, metrics: WindowMetrics) -> str:
        """
        Calculate hash of window metrics.

        Args:
            metrics: Window metrics

        Returns:
            str: SHA256 hash (first 16 characters)
        """
        metrics_data = {
            "total_return": metrics.total_return,
            "max_drawdown": metrics.max_drawdown,
            "win_rate": metrics.win_rate,
            "turnover": metrics.turnover,
        }
        metrics_str = json.dumps(metrics_data, sort_keys=True, ensure_ascii=False)
        hash_obj = hashlib.sha256(metrics_str.encode("utf-8"))
        return hash_obj.hexdigest()[:16]

    def _calculate_event_hash(self, event: DegradationEvent) -> str:
        """
        Calculate hash of degradation event.

        Args:
            event: Degradation event

        Returns:
            str: SHA256 hash (first 16 characters)
        """
        event_data = {
            "timestamp": event.timestamp,
            "strategy_code": event.strategy_code,
            "event_type": event.event_type,
            "old_status": event.old_status,
            "new_status": event.new_status,
            "trigger_metric": event.trigger_metric,
            "trigger_value": event.trigger_value,
            "threshold_value": event.threshold_value,
        }
        event_str = json.dumps(event_data, sort_keys=True, ensure_ascii=False)
        hash_obj = hashlib.sha256(event_str.encode("utf-8"))
        return hash_obj.hexdigest()[:16]

    def add_trade(
        self,
        timestamp: datetime,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
        pnl: float,
        commission: float = 0.0,
    ):
        """
        Add trade to history.

        Args:
            timestamp: Trade timestamp
            symbol: Trading symbol
            side: Trade side (buy/sell)
            entry_price: Entry price
            exit_price: Exit price
            quantity: Trade quantity
            pnl: Trade PnL
            commission: Trade commission
        """
        trade = {
            "timestamp": timestamp.isoformat(),
            "symbol": symbol,
            "side": side,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "quantity": quantity,
            "pnl": pnl,
            "commission": commission,
            "net_pnl": pnl - commission,
        }

        self.trade_history.append(trade)
        logger.info(f"Trade added: {symbol} {side} PnL={pnl:.4f}")

        # Recalculate window metrics
        self._calculate_window_metrics()

    def _calculate_window_metrics(self) -> WindowMetrics | None:
        """
        Calculate rolling window metrics.

        Returns:
            WindowMetrics: Current window metrics
        """
        if len(self.trade_history) < self.thresholds.window_size:
            logger.warning(
                f"Not enough trades for window metrics: {len(self.trade_history)} < {self.thresholds.window_size}"
            )
            return None

        # Get last N trades for rolling window
        window_trades = self.trade_history[-self.thresholds.window_size :]

        # Calculate metrics
        total_trades = len(window_trades)
        total_pnl = sum(trade["net_pnl"] for trade in window_trades)
        winning_trades = sum(1 for trade in window_trades if trade["net_pnl"] > 0)

        # Calculate return (assuming initial capital of 100000)
        initial_capital = 100000.0
        total_return = total_pnl / initial_capital

        # Calculate win rate
        win_rate = winning_trades / total_trades if total_trades > 0 else 0.0

        # Calculate max drawdown
        cumulative_pnl = []
        running_pnl = 0.0
        for trade in window_trades:
            running_pnl += trade["net_pnl"]
            cumulative_pnl.append(running_pnl)

        if cumulative_pnl:
            max_pnl = max(cumulative_pnl)
            drawdown = [max_pnl - pnl for pnl in cumulative_pnl]
            max_drawdown = max(drawdown) / initial_capital if initial_capital > 0 else 0.0
        else:
            max_drawdown = 0.0

        # Calculate turnover (sum of absolute position changes / capital)
        turnover = (
            sum(trade["quantity"] * trade["entry_price"] for trade in window_trades)
            / initial_capital
        )

        window_start = window_trades[0]["timestamp"]
        window_end = window_trades[-1]["timestamp"]

        metrics = WindowMetrics(
            window_start=window_start,
            window_end=window_end,
            window_size=total_trades,
            total_trades=total_trades,
            total_return=total_return,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            turnover=turnover,
            metrics_hash="",
        )

        # Calculate metrics hash
        metrics.metrics_hash = self._calculate_metrics_hash(metrics)

        self.current_window_metrics = metrics
        return metrics

    def check_degradation(self) -> DegradationEvent | None:
        """
        Check for strategy degradation.

        Returns:
            DegradationEvent: Degradation event if triggered, None otherwise
        """
        if not self.current_window_metrics:
            return None

        metrics = self.current_window_metrics
        triggers = []

        # Check return threshold
        if metrics.total_return < self.thresholds.min_return:
            triggers.append(("return", metrics.total_return, self.thresholds.min_return))

        # Check drawdown threshold
        if metrics.max_drawdown > self.thresholds.max_drawdown:
            triggers.append(("drawdown", metrics.max_drawdown, self.thresholds.max_drawdown))

        # Check win rate threshold
        if metrics.win_rate < self.thresholds.min_winrate:
            triggers.append(("winrate", metrics.win_rate, self.thresholds.min_winrate))

        # Check turnover threshold
        if metrics.turnover > self.thresholds.max_turnover:
            triggers.append(("turnover", metrics.turnover, self.thresholds.max_turnover))

        if not triggers:
            return None

        # Determine action based on severity
        # If drawdown exceeds threshold significantly, block the strategy
        if metrics.max_drawdown > self.thresholds.max_drawdown * 1.5:
            event_type = "blocked"
            new_status = StrategyStatus.BLOCKED
            reason = f"Severe drawdown: {metrics.max_drawdown:.2%} exceeds threshold {self.thresholds.max_drawdown:.2%} by 50%"
        # If multiple thresholds triggered, downgrade to paper
        elif len(triggers) >= 2:
            event_type = "paper_downgrade"
            new_status = StrategyStatus.PAPER
            reason = f"Multiple degradation triggers: {', '.join([t[0] for t in triggers])}"
        # Otherwise, block the strategy
        else:
            event_type = "blocked"
            new_status = StrategyStatus.BLOCKED
            trigger_metric, trigger_value, threshold_value = triggers[0]
            reason = f"{trigger_metric} {trigger_value:.2%} exceeds threshold {threshold_value:.2%}"

        # Create degradation event
        event = DegradationEvent(
            timestamp=datetime.now().isoformat(),
            strategy_code=self.strategy_code,
            event_type=event_type,
            old_status=self.current_status.value,
            new_status=new_status.value,
            trigger_metric=triggers[0][0],
            trigger_value=triggers[0][1],
            threshold_value=triggers[0][2],
            window_metrics=asdict(metrics),
            reason=reason,
            event_hash="",
        )

        # Calculate event hash
        event.event_hash = self._calculate_event_hash(event)

        self.degradation_events.append(event)
        self.current_status = new_status

        logger.warning(f"Degradation triggered: {event_type} - {reason}")

        return event

    def apply_degradation_action(self, event: DegradationEvent):
        """
        Apply degradation action (BLOCKED or paper downgrade).

        Args:
            event: Degradation event
        """
        if event.event_type == "blocked":
            logger.error(f"Strategy {self.strategy_code} BLOCKED: {event.reason}")
            # In production, this would trigger blocking logic
            # e.g., stop trading, notify operators, etc.
        elif event.event_type == "paper_downgrade":
            logger.warning(f"Strategy {self.strategy_code} downgraded to PAPER: {event.reason}")
            # In production, this would trigger paper trading mode
            # e.g., switch to paper trading, reduce position sizes, etc.

    def save_evidence(self, output_dir: str = "reports/degradation"):
        """
        Save degradation evidence to disk.

        Args:
            output_dir: Output directory path
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Save degradation events
        events_file = output_path / f"{self.strategy_code}_degradation_events.json"
        with open(events_file, "w", encoding="utf-8") as f:
            events_data = [asdict(event) for event in self.degradation_events]
            json.dump(events_data, f, indent=2, ensure_ascii=False)

        # Save current window metrics
        metrics_file = output_path / f"{self.strategy_code}_window_metrics.json"
        with open(metrics_file, "w", encoding="utf-8") as f:
            if self.current_window_metrics:
                json.dump(asdict(self.current_window_metrics), f, indent=2, ensure_ascii=False)
            else:
                json.dump({}, f, indent=2)

        # Save trade history
        trades_file = output_path / f"{self.strategy_code}_trade_history.json"
        with open(trades_file, "w", encoding="utf-8") as f:
            json.dump(self.trade_history, f, indent=2, ensure_ascii=False)

        logger.info(f"Evidence saved to {output_dir}")

        return [str(events_file), str(metrics_file), str(trades_file)]

    def get_status(self) -> dict[str, Any]:
        """
        Get current monitor status.

        Returns:
            Dict[str, Any]: Monitor status
        """
        return {
            "strategy_code": self.strategy_code,
            "current_status": self.current_status.value,
            "total_trades": len(self.trade_history),
            "degradation_events": len(self.degradation_events),
            "current_window_metrics": asdict(self.current_window_metrics)
            if self.current_window_metrics
            else None,
            "thresholds": self.thresholds.to_dict(),
        }


def main():
    """Main entry point for testing."""
    monitor = StrategyDegradationMonitor(
        strategy_code="test_strategy",
        thresholds=DegradationThresholds(
            min_return=-0.05, max_drawdown=0.15, min_winrate=0.45, max_turnover=0.5, window_size=20
        ),
    )

    # Add some test trades
    from datetime import datetime

    base_time = datetime.now() - timedelta(days=30)

    # Add profitable trades
    for i in range(15):
        monitor.add_trade(
            timestamp=base_time + timedelta(days=i),
            symbol="BTC/USDT",
            side="buy",
            entry_price=50000.0,
            exit_price=50500.0,
            quantity=0.1,
            pnl=50.0,
            commission=1.0,
        )

    # Add losing trades to trigger degradation
    for i in range(10):
        monitor.add_trade(
            timestamp=base_time + timedelta(days=15 + i),
            symbol="BTC/USDT",
            side="sell",
            entry_price=50500.0,
            exit_price=49500.0,
            quantity=0.1,
            pnl=-100.0,
            commission=1.0,
        )

    # Check for degradation
    event = monitor.check_degradation()

    if event:
        monitor.apply_degradation_action(event)

    # Save evidence
    evidence_files = monitor.save_evidence()

    # Print status
    status = monitor.get_status()
    print(f"Strategy Code: {status['strategy_code']}")
    print(f"Current Status: {status['current_status']}")
    print(f"Total Trades: {status['total_trades']}")
    print(f"Degradation Events: {status['degradation_events']}")

    if status["current_window_metrics"]:
        metrics = status["current_window_metrics"]
        print(f"Window Return: {metrics['total_return']:.2%}")
        print(f"Window Max Drawdown: {metrics['max_drawdown']:.2%}")
        print(f"Window Win Rate: {metrics['win_rate']:.2%}")
        print(f"Window Turnover: {metrics['turnover']:.2%}")

    print(f"Evidence files: {', '.join(evidence_files)}")


if __name__ == "__main__":
    main()
