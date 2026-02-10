"""
Strategy layer observation and status snapshot.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StrategySignal:
    """
    Strategy signal data class.
    """

    signal_type: str  # e.g., 'buy', 'sell', 'hold'
    confidence: float  # 0.0 to 1.0
    strength: float  # Signal strength
    reason: str  # Signal generation reason
    timestamp: int  # Signal generation timestamp (milliseconds)


@dataclass(frozen=True)
class TargetPosition:
    """
    Target position data class.
    """

    symbol: str
    position: float  # -1.0 to 1.0
    confidence: float  # 0.0 to 1.0
    leverage: float  # 1.0 to max leverage
    timestamp: int  # Timestamp (milliseconds)


@dataclass(frozen=True)
class OrderIntent:
    """
    Order intent data class.
    """

    symbol: str
    side: str  # 'buy' or 'sell'
    type: str  # 'market', 'limit', etc.
    amount: float  # Order amount
    price: float | None = None  # Limit price (None for market orders)
    confidence: float = 0.8  # 0.0 to 1.0
    timestamp: int = field(default_factory=lambda: int(datetime.now().timestamp() * 1000))


@dataclass(frozen=True)
class Exposure:
    """
    Portfolio exposure data class.
    """

    total_exposure: float  # Total portfolio exposure
    long_exposure: float  # Long positions exposure
    short_exposure: float  # Short positions exposure
    gross_exposure: float  # Gross exposure (long + short)
    net_exposure: float  # Net exposure (long - short)
    leverage: float  # Current leverage
    timestamp: int  # Timestamp (milliseconds)


@dataclass(frozen=True)
class PNLSummary:
    """
    PNL summary data class.
    """

    total_pnl: float  # Total PNL
    realized_pnl: float  # Realized PNL
    unrealized_pnl: float  # Unrealized PNL
    pnl_percentage: float  # PNL percentage
    attribution: dict[str, float]  # PNL attribution by strategy/factor
    timestamp: int  # Timestamp (milliseconds)


@dataclass(frozen=True)
class StrategySnapshot:
    """
    Strategy layer status snapshot.
    """

    # Version information
    strategy_version: str  # Strategy version
    feature_version: str  # Feature version
    data_version: str  # Data version

    # Core observation data
    timestamp: int  # Snapshot timestamp (milliseconds)
    strategy_code: str  # Strategy code

    # Market context
    current_price: float  # Current asset price
    volatility: float  # Current volatility

    # Strategy outputs
    signal: StrategySignal | None = None  # Generated signal
    target_position: TargetPosition | None = None  # Target position
    order_intent: OrderIntent | None = None  # Order intent

    # Portfolio metrics
    exposure: Exposure | None = None  # Exposure information
    pnl_summary: PNLSummary | None = None  # PNL summary

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)  # Additional metadata


class StrategySnapshotStore:
    """
    Strategy snapshot store for managing and persisting strategy layer observations.
    """

    def __init__(self, store_path: Path | None = None):
        """
        Initialize the strategy snapshot store.

        Args:
            store_path: Path to the snapshot store directory (default: data/state/strategy_snapshots)
        """
        self.store_path = store_path or Path("data/state/strategy_snapshots")
        self._ensure_store_exists()
        self.logger = logging.getLogger(__name__)

    def _ensure_store_exists(self):
        """Ensure the snapshot store directory exists."""
        self.store_path.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, snapshot: StrategySnapshot) -> Path:
        """
        Save a strategy snapshot to the store.

        Args:
            snapshot: Strategy snapshot to save

        Returns:
            Path: Path to the saved snapshot file
        """
        # Create snapshot directory for the strategy
        strategy_dir = self.store_path / snapshot.strategy_code
        strategy_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with timestamp
        filename = f"snapshot_{snapshot.timestamp}.json"
        file_path = strategy_dir / filename

        # Convert snapshot to dictionary and save
        snapshot_dict = asdict(snapshot)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_dict, f, indent=2, ensure_ascii=False)

        # Also update the latest snapshot link
        latest_link = strategy_dir / "latest_snapshot.json"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(file_path.name)  # Create relative symlink

        self.logger.info(f"Saved strategy snapshot to {file_path}")
        return file_path

    def get_latest_snapshot(self, strategy_code: str) -> StrategySnapshot | None:
        """
        Get the latest snapshot for a strategy.

        Args:
            strategy_code: Strategy code

        Returns:
            Optional[StrategySnapshot]: Latest snapshot if found, None otherwise
        """
        latest_link = self.store_path / strategy_code / "latest_snapshot.json"
        if not latest_link.exists():
            return None

        try:
            with open(latest_link, encoding="utf-8") as f:
                snapshot_dict = json.load(f)
            return StrategySnapshot(**snapshot_dict)
        except Exception as e:
            self.logger.error(f"Failed to load latest snapshot for {strategy_code}: {e}")
            return None

    def get_snapshot(self, strategy_code: str, timestamp: int) -> StrategySnapshot | None:
        """
        Get a specific snapshot by timestamp.

        Args:
            strategy_code: Strategy code
            timestamp: Snapshot timestamp (milliseconds)

        Returns:
            Optional[StrategySnapshot]: Snapshot if found, None otherwise
        """
        file_path = self.store_path / strategy_code / f"snapshot_{timestamp}.json"
        if not file_path.exists():
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                snapshot_dict = json.load(f)
            return StrategySnapshot(**snapshot_dict)
        except Exception as e:
            self.logger.error(f"Failed to load snapshot {timestamp} for {strategy_code}: {e}")
            return None

    def list_snapshots(self, strategy_code: str) -> list[int]:
        """
        List all snapshot timestamps for a strategy.

        Args:
            strategy_code: Strategy code

        Returns:
            List[int]: List of snapshot timestamps (milliseconds)
        """
        strategy_dir = self.store_path / strategy_code
        if not strategy_dir.exists():
            return []

        snapshots = []
        for file_path in strategy_dir.glob("snapshot_*.json"):
            if file_path.name == "latest_snapshot.json":
                continue
            try:
                timestamp = int(file_path.stem.split("_")[1])
                snapshots.append(timestamp)
            except (ValueError, IndexError):
                continue

        snapshots.sort()
        return snapshots

    def save_status_snapshot(self, snapshot: StrategySnapshot) -> Path:
        """
        Save a status snapshot to the unified status directory.

        Args:
            snapshot: Strategy snapshot to save

        Returns:
            Path: Path to the saved status snapshot file
        """
        # Ensure the reports directory exists
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        # Save to unified status file
        status_path = reports_dir / "status_snapshot.json"
        snapshot_dict = asdict(snapshot)

        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_dict, f, indent=2, ensure_ascii=False)

        self.logger.info(f"Saved unified status snapshot to {status_path}")
        return status_path
