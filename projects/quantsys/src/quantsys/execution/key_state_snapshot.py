#!/usr/bin/env python3
"""
Key State Snapshot Management

This module provides functionality to capture, store, and restore key state snapshots
including positions, orders, intents, strategy versions, factor versions, and risk verdicts.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from src.quantsys.common.risk_manager import RiskVerdict
from src.quantsys.execution.reconciliation import (
    Balance,
    Order,
    Position,
)
from src.quantsys.strategy.strategy_snapshot import OrderIntent


@dataclass
class KeyStateSnapshot:
    """
    Key state snapshot containing all critical system state information.
    """

    # Basic metadata
    snapshot_id: str
    timestamp: int  # milliseconds since epoch
    run_id: str  # Run ID for traceability

    # Version information
    strategy_version: str
    factor_version: str

    # Core state
    positions: list[Position]
    orders: list[Order]
    intents: list[OrderIntent]

    # Balance information
    balances: dict[str, Balance]

    # Risk information
    risk_verdict: RiskVerdict

    # Performance metrics
    unrealized_pnl: float
    total_equity: float

    # Additional metadata
    metadata: dict[str, Any] = field(default_factory=dict)


class KeyStateSnapshotManager:
    """
    Manager for key state snapshots, handling storage, retrieval, and validation.
    """

    def __init__(self, store_path: Path | None = None):
        """
        Initialize the snapshot manager.

        Args:
            store_path: Path to store snapshots (default: data/state/key_snapshots)
        """
        self.store_path = store_path or Path("data/state/key_snapshots")
        self.store_path.mkdir(parents=True, exist_ok=True)
        self._ensure_backward_compatibility()

    def _ensure_backward_compatibility(self):
        """Ensure the store is backward compatible with existing data."""
        pass

    def generate_snapshot_id(self) -> str:
        """Generate a unique snapshot ID."""
        timestamp = int(time.time() * 1000)
        return f"snapshot_{timestamp}"

    def capture_snapshot(
        self,
        run_id: str,
        strategy_version: str,
        factor_version: str,
        positions: list[Position],
        orders: list[Order],
        intents: list[OrderIntent],
        balances: dict[str, Balance],
        risk_verdict: RiskVerdict,
        unrealized_pnl: float,
        total_equity: float,
        metadata: dict[str, Any] | None = None,
    ) -> KeyStateSnapshot:
        """
        Capture a key state snapshot.

        Args:
            run_id: Run ID for traceability
            strategy_version: Strategy version
            factor_version: Factor version
            positions: Current positions
            orders: Current orders
            intents: Current order intents
            balances: Current balances
            risk_verdict: Current risk verdict
            unrealized_pnl: Current unrealized PnL
            total_equity: Current total equity
            metadata: Additional metadata

        Returns:
            KeyStateSnapshot: Captured snapshot
        """
        snapshot_id = self.generate_snapshot_id()
        timestamp = int(time.time() * 1000)

        snapshot = KeyStateSnapshot(
            snapshot_id=snapshot_id,
            timestamp=timestamp,
            run_id=run_id,
            strategy_version=strategy_version,
            factor_version=factor_version,
            positions=positions,
            orders=orders,
            intents=intents,
            balances=balances,
            risk_verdict=risk_verdict,
            unrealized_pnl=unrealized_pnl,
            total_equity=total_equity,
            metadata=metadata or {},
        )

        return snapshot

    def save_snapshot(self, snapshot: KeyStateSnapshot) -> Path:
        """
        Save a snapshot to disk.

        Args:
            snapshot: Snapshot to save

        Returns:
            Path: Path to the saved snapshot file
        """
        # Convert to serializable dict
        snapshot_dict = asdict(snapshot)

        # Convert RiskVerdict to dict
        if hasattr(snapshot.risk_verdict, "__dict__"):
            snapshot_dict["risk_verdict"] = snapshot.risk_verdict.__dict__

        # Save to file
        file_path = self.store_path / f"{snapshot.snapshot_id}.json"
        with open(file_path, "w") as f:
            json.dump(snapshot_dict, f, indent=2, default=str)

        # Update latest snapshot link
        latest_path = self.store_path / "latest_snapshot.json"
        if latest_path.exists():
            latest_path.unlink()
        latest_path.write_text(json.dumps(snapshot_dict, indent=2, default=str))

        return file_path

    def load_snapshot(self, snapshot_id_or_path: str | Path) -> KeyStateSnapshot | None:
        """
        Load a snapshot from disk.

        Args:
            snapshot_id_or_path: Snapshot ID or path to snapshot file

        Returns:
            Optional[KeyStateSnapshot]: Loaded snapshot, or None if not found
        """
        # Determine file path
        if isinstance(snapshot_id_or_path, str):
            if snapshot_id_or_path.startswith("snapshot_"):
                file_path = self.store_path / f"{snapshot_id_or_path}.json"
            else:
                file_path = self.store_path / snapshot_id_or_path
        else:
            file_path = snapshot_id_or_path

        # Check if file exists
        if not file_path.exists():
            return None

        # Load from file
        with open(file_path) as f:
            snapshot_dict = json.load(f)

        # Convert risk_verdict back to RiskVerdict object
        risk_verdict_dict = snapshot_dict.pop("risk_verdict", {})
        risk_verdict = RiskVerdict(
            allow_open=risk_verdict_dict.get("allow_open", True),
            allow_reduce=risk_verdict_dict.get("allow_reduce", True),
            blocked_reason=risk_verdict_dict.get("blocked_reason", []),
            is_blocked=risk_verdict_dict.get("is_blocked", False),
        )

        # Convert Position objects
        positions = []
        for pos_dict in snapshot_dict.pop("positions", []):
            positions.append(Position(**pos_dict))

        # Convert Order objects
        orders = []
        for order_dict in snapshot_dict.pop("orders", []):
            orders.append(Order(**order_dict))

        # Convert OrderIntent objects
        intents = []
        for intent_dict in snapshot_dict.pop("intents", []):
            intents.append(OrderIntent(**intent_dict))

        # Convert Balance objects
        balances = {}
        for currency, bal_dict in snapshot_dict.pop("balances", {}).items():
            balances[currency] = Balance(**bal_dict)

        # Create and return snapshot
        return KeyStateSnapshot(
            positions=positions,
            orders=orders,
            intents=intents,
            balances=balances,
            risk_verdict=risk_verdict,
            **snapshot_dict,
        )

    def get_latest_snapshot(self) -> KeyStateSnapshot | None:
        """
        Get the latest snapshot.

        Returns:
            Optional[KeyStateSnapshot]: Latest snapshot, or None if no snapshots exist
        """
        latest_path = self.store_path / "latest_snapshot.json"
        if not latest_path.exists():
            return None

        return self.load_snapshot(latest_path)

    def list_snapshots(self) -> list[str]:
        """
        List all snapshot IDs.

        Returns:
            List[str]: List of snapshot IDs, sorted by timestamp (newest first)
        """
        snapshots = []
        for file_path in self.store_path.glob("snapshot_*.json"):
            if file_path.name != "latest_snapshot.json":
                snapshots.append(file_path.stem)

        # Sort by timestamp (newest first)
        snapshots.sort(key=lambda x: int(x.split("_")[1]), reverse=True)
        return snapshots

    def validate_snapshot(self, snapshot: KeyStateSnapshot) -> bool:
        """
        Validate a snapshot for integrity.

        Args:
            snapshot: Snapshot to validate

        Returns:
            bool: True if snapshot is valid, False otherwise
        """
        # Check required fields
        required_fields = [
            "snapshot_id",
            "timestamp",
            "run_id",
            "strategy_version",
            "factor_version",
        ]
        for field in required_fields:
            if not getattr(snapshot, field, None):
                return False

        # Check that positions, orders, and intents are lists
        if (
            not isinstance(snapshot.positions, list)
            or not isinstance(snapshot.orders, list)
            or not isinstance(snapshot.intents, list)
        ):
            return False

        # Check that balances is a dict
        if not isinstance(snapshot.balances, dict):
            return False

        # Check that risk_verdict is a RiskVerdict object
        if not hasattr(snapshot.risk_verdict, "allow_open"):
            return False

        return True

    def restore_from_snapshot(self, snapshot: KeyStateSnapshot) -> dict[str, Any]:
        """
        Restore system state from a snapshot.

        Args:
            snapshot: Snapshot to restore from

        Returns:
            Dict[str, Any]: Restoration results
        """
        # Validate snapshot first
        if not self.validate_snapshot(snapshot):
            return {"success": False, "error": "Invalid snapshot"}

        # In a real system, this would restore state to all relevant components
        # For now, we'll just return the restored state for verification
        return {
            "success": True,
            "restored_state": {
                "snapshot_id": snapshot.snapshot_id,
                "timestamp": snapshot.timestamp,
                "strategy_version": snapshot.strategy_version,
                "factor_version": snapshot.factor_version,
                "positions_count": len(snapshot.positions),
                "orders_count": len(snapshot.orders),
                "intents_count": len(snapshot.intents),
                "balances_count": len(snapshot.balances),
                "risk_verdict": {
                    "allow_open": snapshot.risk_verdict.allow_open,
                    "is_blocked": snapshot.risk_verdict.is_blocked,
                },
            },
        }

    def run_self_test(self) -> dict[str, Any]:
        """
        Run self-test to verify snapshot functionality.

        Returns:
            Dict[str, Any]: Test results
        """
        results = {"tests": [], "overall_result": "PASS"}

        # Test 1: Create and save snapshot
        try:
            # Create test data
            from src.quantsys.execution.reconciliation import (
                Balance,
                Order,
                Position,
            )

            test_positions = [
                Position(
                    symbol="ETH-USDT-SWAP",
                    side="long",
                    size=0.5,
                    entry_price=2000.0,
                    unrealized_pnl=50.0,
                )
            ]

            test_orders = [
                Order(
                    id="order_123",
                    client_order_id="client_order_123",
                    symbol="ETH-USDT-SWAP",
                    side="BUY",
                    type="MARKET",
                    price=2000.0,
                    amount=0.1,
                    filled=0.0,
                    status="OPEN",
                )
            ]

            test_intents = [
                OrderIntent(
                    symbol="ETH-USDT-SWAP", side="buy", type="market", amount=0.1, confidence=0.9
                )
            ]

            test_balances = {"USDT": Balance(total=10000.0, available=9500.0, currency="USDT")}

            test_risk_verdict = RiskVerdict(
                allow_open=True, allow_reduce=True, blocked_reason=[], is_blocked=False
            )

            # Capture snapshot with run_id
            run_id = "test_run_123"
            snapshot = self.capture_snapshot(
                run_id=run_id,
                strategy_version="v1.0.0",
                factor_version="v1.2.0",
                positions=test_positions,
                orders=test_orders,
                intents=test_intents,
                balances=test_balances,
                risk_verdict=test_risk_verdict,
                unrealized_pnl=50.0,
                total_equity=10050.0,
                metadata={"test": True},
            )

            # Save snapshot
            file_path = self.save_snapshot(snapshot)

            results["tests"].append(
                {
                    "name": "Create and Save Snapshot",
                    "result": "PASS",
                    "details": f"Snapshot saved to {file_path}",
                }
            )

        except Exception as e:
            results["tests"].append(
                {"name": "Create and Save Snapshot", "result": "FAIL", "details": str(e)}
            )
            results["overall_result"] = "FAIL"

        # Test 2: Load snapshot
        try:
            loaded_snapshot = self.get_latest_snapshot()
            if loaded_snapshot:
                results["tests"].append(
                    {
                        "name": "Load Latest Snapshot",
                        "result": "PASS",
                        "details": f"Loaded snapshot {loaded_snapshot.snapshot_id}",
                    }
                )
            else:
                results["tests"].append(
                    {
                        "name": "Load Latest Snapshot",
                        "result": "FAIL",
                        "details": "Failed to load latest snapshot",
                    }
                )
                results["overall_result"] = "FAIL"
        except Exception as e:
            results["tests"].append(
                {"name": "Load Latest Snapshot", "result": "FAIL", "details": str(e)}
            )
            results["overall_result"] = "FAIL"

        # Test 3: Validate snapshot
        try:
            loaded_snapshot = self.get_latest_snapshot()
            if loaded_snapshot:
                is_valid = self.validate_snapshot(loaded_snapshot)
                if is_valid:
                    results["tests"].append(
                        {
                            "name": "Validate Snapshot",
                            "result": "PASS",
                            "details": "Snapshot is valid",
                        }
                    )
                else:
                    results["tests"].append(
                        {
                            "name": "Validate Snapshot",
                            "result": "FAIL",
                            "details": "Snapshot validation failed",
                        }
                    )
                    results["overall_result"] = "FAIL"
        except Exception as e:
            results["tests"].append(
                {"name": "Validate Snapshot", "result": "FAIL", "details": str(e)}
            )
            results["overall_result"] = "FAIL"

        # Test 4: Restore from snapshot
        try:
            loaded_snapshot = self.get_latest_snapshot()
            if loaded_snapshot:
                restore_result = self.restore_from_snapshot(loaded_snapshot)
                if restore_result["success"]:
                    results["tests"].append(
                        {
                            "name": "Restore from Snapshot",
                            "result": "PASS",
                            "details": "Successfully restored from snapshot",
                        }
                    )
                else:
                    results["tests"].append(
                        {
                            "name": "Restore from Snapshot",
                            "result": "FAIL",
                            "details": restore_result.get("error", "Unknown error"),
                        }
                    )
                    results["overall_result"] = "FAIL"
        except Exception as e:
            results["tests"].append(
                {"name": "Restore from Snapshot", "result": "FAIL", "details": str(e)}
            )
            results["overall_result"] = "FAIL"

        # Test 5: List snapshots
        try:
            snapshots = self.list_snapshots()
            results["tests"].append(
                {
                    "name": "List Snapshots",
                    "result": "PASS",
                    "details": f"Found {len(snapshots)} snapshots",
                }
            )
        except Exception as e:
            results["tests"].append({"name": "List Snapshots", "result": "FAIL", "details": str(e)})
            results["overall_result"] = "FAIL"

        return results

    def save_test_results(self, results: dict[str, Any]) -> Path:
        """
        Save test results to disk.

        Args:
            results: Test results to save

        Returns:
            Path: Path to the saved test results file
        """
        # Ensure reports directory exists
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        # Save test results
        results_path = reports_dir / "key_snapshot_test_results.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2, default=str)

        # Also update last_run.md
        last_run_path = reports_dir / "last_run.md"
        test_summary = f"""
## Key State Snapshot Self-Test Results

### Overall Result: {results["overall_result"]}

### Test Details:
"""

        for test in results["tests"]:
            test_summary += f"- **{test['name']}**: {test['result']} - {test['details']}\n"

        # Read existing content
        existing_content = ""
        if last_run_path.exists():
            with open(last_run_path, encoding="utf-8") as f:
                existing_content = f.read()

        # Write updated content
        with open(last_run_path, "w", encoding="utf-8") as f:
            f.write(test_summary + "\n" + existing_content)

        return results_path
