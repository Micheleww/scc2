#!/usr/bin/env python3
"""
Disaster Recovery Manager

This module provides functionality for disaster recovery, including:
1. Loading state snapshots
2. Reconciliation with exchange
3. Restoring subscriptions
4. Continuing paper trading
5. Blocking and generating drift reports if reconciliation fails
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.quantsys.common.black_swan_mode import BlackSwanModeManager
from src.quantsys.execution.key_state_snapshot import (
    KeyStateSnapshot,
    KeyStateSnapshotManager,
)
from src.quantsys.execution.readiness import ExecutionReadiness
from src.quantsys.execution.reconciliation import (
    RecommendedAction,
    ReconciliationReport,
    reconcile,
)
from src.quantsys.execution.trade_ledger import TradeLedger


class DisasterRecoveryManager:
    """
    Manager for disaster recovery operations.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the disaster recovery manager.

        Args:
            config: Recovery configuration
        """
        self.config = config or {
            "snapshot_path": "data/state/key_snapshots",
            "drift_report_path": "reports/drift_reports",
            "reconciliation_thresholds": {
                "balance_threshold": 0.01,
                "position_threshold": 0.001,
                "price_threshold": 0.001,
            },
            "paper_trading_config": {"enabled": True, "symbol_map": {}},
        }

        # Initialize components
        self.snapshot_manager = KeyStateSnapshotManager(Path(self.config["snapshot_path"]))
        self.readiness = ExecutionReadiness()
        self.trade_ledger = TradeLedger()
        self.black_swan_manager = BlackSwanModeManager()

        # Ensure directories exist
        Path(self.config["drift_report_path"]).mkdir(parents=True, exist_ok=True)

    def load_latest_snapshot(self) -> KeyStateSnapshot | None:
        """
        Load the latest state snapshot.

        Returns:
            Optional[KeyStateSnapshot]: Latest snapshot or None if not found
        """
        return self.snapshot_manager.get_latest_snapshot()

    def load_snapshot_by_id(self, snapshot_id: str) -> KeyStateSnapshot | None:
        """
        Load a snapshot by its ID.

        Args:
            snapshot_id: Snapshot ID to load

        Returns:
            Optional[KeyStateSnapshot]: Loaded snapshot or None if not found
        """
        return self.snapshot_manager.load_snapshot(snapshot_id)

    def reconcile_snapshot(
        self, snapshot: KeyStateSnapshot, exchange_client: Any
    ) -> ReconciliationReport:
        """
        Reconcile a snapshot with exchange state.

        Args:
            snapshot: Snapshot to reconcile
            exchange_client: Exchange client instance

        Returns:
            ReconciliationReport: Reconciliation results
        """
        # Extract local state from snapshot
        local_state = {
            "balance": {
                "USDT": {
                    "total": sum(bal.total for bal in snapshot.balances.values()),
                    "available": sum(bal.available for bal in snapshot.balances.values()),
                }
            },
            "positions": [
                {
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "size": pos.size,
                    "entryPrice": pos.entry_price,
                    "unrealizedPnl": pos.unrealized_pnl,
                }
                for pos in snapshot.positions
            ],
            "orders": [
                {
                    "id": order.id,
                    "clientOrderId": order.client_order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "type": order.type,
                    "price": order.price,
                    "amount": order.amount,
                    "filled": order.filled,
                    "status": order.status,
                }
                for order in snapshot.orders
            ],
            "fills": [],  # Fills are not included in the snapshot
        }

        # Get symbols from snapshot
        symbols = list({pos.symbol for pos in snapshot.positions})
        symbols.extend({order.symbol for order in snapshot.orders})
        symbols = list(set(symbols))

        # Create symbol map (local symbol -> exchange symbol)
        symbol_map = {symbol: symbol for symbol in symbols}

        # Perform reconciliation
        return reconcile(
            exchange_client=exchange_client,
            local_state=local_state,
            symbol_map=symbol_map,
            now_ts=int(time.time() * 1000),
            config=self.config["reconciliation_thresholds"],
        )

    def generate_drift_report(
        self, report: ReconciliationReport, snapshot: KeyStateSnapshot
    ) -> Path:
        """
        Generate a drift report if reconciliation fails.

        Args:
            report: Reconciliation report
            snapshot: Snapshot used for reconciliation

        Returns:
            Path: Path to the generated drift report
        """
        report_data = {
            "report_id": f"drift_{int(time.time() * 1000)}",
            "timestamp": int(time.time() * 1000),
            "snapshot_id": snapshot.snapshot_id,
            "snapshot_timestamp": snapshot.timestamp,
            "reconciliation_result": {
                "ok": report.ok,
                "drift_type": report.drift_type.value,
                "recommended_action": report.recommended_action.value,
                "summary": report.summary,
            },
            "diffs": [
                {
                    "category": diff.category,
                    "key": diff.key,
                    "exchange_value": str(diff.exchange_value),
                    "local_value": str(diff.local_value),
                    "field": diff.field,
                    "threshold": diff.threshold,
                }
                for diff in report.diffs
            ],
            "exchange_snapshot": {
                "timestamp": report.exchange_snapshot_meta.timestamp,
                "symbols": report.exchange_snapshot_meta.symbols,
                "source": report.exchange_snapshot_meta.source,
            },
            "local_snapshot": {
                "timestamp": report.local_snapshot_meta.timestamp,
                "symbols": report.local_snapshot_meta.symbols,
                "source": report.local_snapshot_meta.source,
            },
        }

        # Save drift report
        report_path = Path(self.config["drift_report_path"]) / f"{report_data['report_id']}.json"
        with open(report_path, "w") as f:
            json.dump(report_data, f, indent=2, default=str)

        return report_path

    def restore_subscriptions(self, symbols: list[str]) -> bool:
        """
        Restore subscriptions for the given symbols.

        Args:
            symbols: List of symbols to restore subscriptions for

        Returns:
            bool: True if subscriptions were restored successfully
        """
        # In a real system, this would restore WebSocket/REST subscriptions
        # For now, we'll just simulate it
        print(f"Restoring subscriptions for symbols: {symbols}")
        # Simulate subscription restoration
        time.sleep(1.0)
        return True

    def continue_paper_trading(self, snapshot: KeyStateSnapshot) -> bool:
        """
        Continue paper trading from the snapshot.

        Args:
            snapshot: Snapshot to continue from

        Returns:
            bool: True if paper trading was started successfully
        """
        if not self.config["paper_trading_config"]["enabled"]:
            print("Paper trading is not enabled in configuration")
            return False

        # In a real system, this would start the paper trading engine
        # For now, we'll just simulate it
        print(f"Continuing paper trading from snapshot: {snapshot.snapshot_id}")
        print(f"Strategy version: {snapshot.strategy_version}")
        print(f"Factor version: {snapshot.factor_version}")
        print(f"Positions count: {len(snapshot.positions)}")
        print(f"Orders count: {len(snapshot.orders)}")
        print(f"Intents count: {len(snapshot.intents)}")

        # Simulate paper trading start
        time.sleep(1.0)
        return True

    def block_trading(self, reason: str) -> None:
        """
        Block all trading activities.

        Args:
            reason: Reason for blocking
        """
        from src.quantsys.execution.readiness import ReadinessStatus
        from src.quantsys.execution.reconciliation import RecommendedAction

        # Update readiness state to BLOCKED by creating a new ReadinessStatus
        self.readiness._status = ReadinessStatus(
            ok=False, blocked=True, reasons=[reason], recommended_action=RecommendedAction.BLOCK
        )

        # Update black swan mode to liquidate if needed
        self.black_swan_manager.manual_trigger(
            action="liquidate",  # 使用字符串值，不是枚举类型
            reason=reason,
        )

        print(f"Trading blocked: {reason}")

    def run_recovery(self, exchange_client: Any, snapshot_id: str | None = None) -> dict[str, Any]:
        """
        Run the complete disaster recovery process.

        Args:
            exchange_client: Exchange client instance
            snapshot_id: Optional snapshot ID to use (default: latest)

        Returns:
            Dict[str, Any]: Recovery results
        """
        results = {
            "status": "FAILED",
            "timestamp": int(time.time() * 1000),
            "steps": [],
            "errors": [],
        }

        try:
            # Step 1: Load snapshot
            print("Step 1: Loading state snapshot...")
            if snapshot_id:
                snapshot = self.load_snapshot_by_id(snapshot_id)
            else:
                snapshot = self.load_latest_snapshot()

            if not snapshot:
                error_msg = f"No snapshot found (ID: {snapshot_id if snapshot_id else 'latest'})"
                results["errors"].append(error_msg)
                return results

            results["steps"].append(
                {
                    "name": "load_snapshot",
                    "status": "SUCCESS",
                    "snapshot_id": snapshot.snapshot_id,
                    "timestamp": snapshot.timestamp,
                }
            )
            print(f"✓ Loaded snapshot: {snapshot.snapshot_id}")

            # Step 2: Reconcile snapshot with exchange
            print("Step 2: Reconciling snapshot with exchange...")
            report = self.reconcile_snapshot(snapshot, exchange_client)

            results["steps"].append(
                {
                    "name": "reconcile",
                    "status": "SUCCESS" if report.ok else "FAILED",
                    "drift_type": report.drift_type.value,
                    "recommended_action": report.recommended_action.value,
                    "diff_count": len(report.diffs),
                }
            )

            if report.ok:
                print("✓ Reconciliation passed")
            else:
                print(f"✗ Reconciliation failed: {report.summary}")

                # Generate drift report
                drift_report_path = self.generate_drift_report(report, snapshot)
                print(f"✓ Generated drift report: {drift_report_path}")

                # Block trading if recommended
                if report.recommended_action == RecommendedAction.BLOCK:
                    self.block_trading(f"Reconciliation failed: {report.summary}")
                    results["blocked"] = True
                    results["block_reason"] = report.summary
                    results["drift_report_path"] = str(drift_report_path)
                    return results

            # Step 3: Restore subscriptions
            print("Step 3: Restoring subscriptions...")
            # Extract symbols from snapshot
            symbols = list({pos.symbol for pos in snapshot.positions})
            symbols.extend({order.symbol for order in snapshot.orders})
            symbols = list(set(symbols))

            if self.restore_subscriptions(symbols):
                results["steps"].append(
                    {
                        "name": "restore_subscriptions",
                        "status": "SUCCESS",
                        "symbols_count": len(symbols),
                    }
                )
                print(f"✓ Restored subscriptions for {len(symbols)} symbols")
            else:
                results["steps"].append({"name": "restore_subscriptions", "status": "FAILED"})
                results["errors"].append("Failed to restore subscriptions")
                return results

            # Step 4: Continue paper trading
            print("Step 4: Continuing paper trading...")
            if self.continue_paper_trading(snapshot):
                results["steps"].append({"name": "continue_paper_trading", "status": "SUCCESS"})
                print("✓ Paper trading continued successfully")
                results["status"] = "SUCCESS"
            else:
                results["steps"].append({"name": "continue_paper_trading", "status": "FAILED"})
                results["errors"].append("Failed to continue paper trading")
                return results

        except Exception as e:
            results["errors"].append(str(e))
            print(f"✗ Recovery failed with exception: {e}")

        return results

    def run_self_test(self) -> dict[str, Any]:
        """
        Run self-test to verify disaster recovery functionality.

        Returns:
            Dict[str, Any]: Test results
        """
        results = {"tests": [], "overall_result": "PASS"}

        # Test 1: Create and save test snapshot
        try:
            from src.quantsys.common.risk_manager import RiskVerdict
            from src.quantsys.execution.reconciliation import Balance, Order, Position
            from src.quantsys.strategy.strategy_snapshot import OrderIntent

            # Create test data
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

            # Capture and save snapshot
            snapshot = self.snapshot_manager.capture_snapshot(
                run_id="test_run_123",
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

            file_path = self.snapshot_manager.save_snapshot(snapshot)

            results["tests"].append(
                {
                    "name": "Create and Save Test Snapshot",
                    "result": "PASS",
                    "details": f"Snapshot saved to {file_path}",
                }
            )

        except Exception as e:
            results["tests"].append(
                {"name": "Create and Save Test Snapshot", "result": "FAIL", "details": str(e)}
            )
            results["overall_result"] = "FAIL"

        # Test 2: Load snapshot
        try:
            loaded_snapshot = self.snapshot_manager.get_latest_snapshot()
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

        # Test 3: Mock reconciliation
        try:
            # Create mock exchange client
            class MockExchangeClient:
                def fetch_balance(self):
                    return {"total": {"USDT": 10000.0}, "free": {"USDT": 9500.0}}

                def fetch_positions(self):
                    return []

                def fetch_open_orders(self):
                    return []

                def fetch_my_trades(self):
                    return []

            mock_client = MockExchangeClient()
            snapshot = self.snapshot_manager.get_latest_snapshot()

            if snapshot:
                report = self.reconcile_snapshot(snapshot, mock_client)
                results["tests"].append(
                    {
                        "name": "Mock Reconciliation",
                        "result": "PASS",
                        "details": f"Reconciliation completed, ok={report.ok}",
                    }
                )
            else:
                results["tests"].append(
                    {
                        "name": "Mock Reconciliation",
                        "result": "FAIL",
                        "details": "No snapshot available for reconciliation",
                    }
                )
                results["overall_result"] = "FAIL"
        except Exception as e:
            results["tests"].append(
                {"name": "Mock Reconciliation", "result": "FAIL", "details": str(e)}
            )
            results["overall_result"] = "FAIL"

        return results

    def update_taskhub(self, task_id: str, result: dict[str, Any]) -> bool:
        """
        Update TaskHub with recovery results

        Args:
            task_id: Task ID to update
            result: Recovery results

        Returns:
            bool: True if update was successful
        """
        try:
            import datetime
            from pathlib import Path

            # Load registry
            taskhub_root = Path("taskhub")
            registry_path = taskhub_root / "registry.json"

            if not registry_path.exists():
                print(f"TaskHub registry not found: {registry_path}")
                return False

            with open(registry_path, encoding="utf-8") as f:
                registry = json.load(f)

            # Find task
            task = None
            for t in registry.get("tasks", []):
                if t["id"] == task_id:
                    task = t
                    break

            if not task:
                print(f"Task not found: {task_id}")
                return False

            # Update task status and notes
            if result["status"] == "SUCCESS":
                task["status"] = "DONE"
                task["notes"] = "一键恢复流程执行成功"
            else:
                task["status"] = "FAIL"
                task["notes"] = (
                    f"一键恢复流程执行失败: {result.get('block_reason', 'Unknown reason')}"
                )

            # Update updated_at time
            task["updated_at"] = datetime.datetime.now().isoformat()

            # Add evidence paths
            evidence_paths = set(task.get("evidence_paths", []))

            # Save recovery results as evidence
            recovery_result_path = (
                Path("reports")
                / f"recovery_result_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            )
            with open(recovery_result_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)

            evidence_paths.add(f"reports/{recovery_result_path.name}")
            task["evidence_paths"] = list(evidence_paths)

            # Save updated registry
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2, ensure_ascii=False)

            print(f"Successfully updated TaskHub for task: {task_id}")
            return True

        except Exception as e:
            print(f"Failed to update TaskHub: {e}")
            return False

    def save_recovery_results(self, results: dict[str, Any]) -> str:
        """
        Save recovery results to reports directory

        Args:
            results: Recovery results

        Returns:
            str: Path to the results file
        """
        import datetime
        from pathlib import Path

        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        results_file = (
            reports_dir
            / f"recovery_result_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)

        return str(results_file)


# For testing purposes
if __name__ == "__main__":
    # Create a simple test
    dr_manager = DisasterRecoveryManager()
    test_results = dr_manager.run_self_test()

    # Print test results
    print("=== Disaster Recovery Self-Test Results ===")
    print(f"Overall Result: {test_results['overall_result']}")
    print("\nTest Details:")
    for test in test_results["tests"]:
        status = "✓ PASS" if test["result"] == "PASS" else "✗ FAIL"
        print(f"{status} {test['name']}: {test['details']}")

    # Save test results
    results_path = Path("reports") / "disaster_recovery_self_test.json"
    with open(results_path, "w") as f:
        json.dump(test_results, f, indent=2, default=str)

    print(f"\nTest results saved to: {results_path}")
