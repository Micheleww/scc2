#!/usr/bin/env python3
"""
Live Execution Manager for handling order execution, status tracking, and risk management

This module implements the LiveExecutionManager class which handles:
- Order execution with risk checks
- Status tracking and write-back
- Audit logging
- Drill functionality
"""

import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .order_execution import OrderExecution
from .state_storage import StateStorageFactory

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LiveExecutionManager:
    """
    Live Execution Manager for handling order execution and status tracking
    """

    def __init__(
        self,
        config_dir: str = "configs",
        data_dir: str = "data",
        order_executor: OrderExecution | None = None,
    ):
        """
        Initialize Live Execution Manager

        Args:
            config_dir: Directory containing configuration files
            data_dir: Directory for state and evidence files
            order_executor: OrderExecution instance (optional, will be created if not provided)
        """
        self.config_dir = config_dir

        # Load live configuration
        self.live_config = self._load_live_config()

        # Initialize OrderExecutor (use provided or create new)
        if order_executor is not None:
            self.order_executor = order_executor
        else:
            # Create OrderExecution instance from config
            execution_config = {
                "exchange": self.live_config.get("exchange", "okx"),
                "trading_mode": self.live_config.get("trading_mode", "drill"),
                "risk_params": self.live_config.get("risk", {}),
                "order_splitter": self.live_config.get("order_splitter", {}),
                "black_swan": self.live_config.get("black_swan", {}),
                "risk_guard": self.live_config.get("risk_guard", {}),
                "real_order": self.live_config.get("real_order", {}),
            }
            self.order_executor = OrderExecution(execution_config)

        # Data directory for state and evidence
        self.data_dir = Path(data_dir)
        self.evidence_dir = self.data_dir / "evidence" / "live_execution"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        # State file paths
        self.order_state_path = self.data_dir / "order_state.json"
        self.position_state_path = self.data_dir / "position_state.json"
        self.risk_state_path = self.data_dir / "risk_state.json"

        # Initialize state storage (统一状态存储)
        storage_type = self.live_config.get("state_storage", {}).get("type", "file")
        storage_dir = self.live_config.get("state_storage", {}).get(
            "dir", str(self.data_dir / "state")
        )
        self.state_storage = StateStorageFactory.create(
            storage_type=storage_type, storage_dir=storage_dir
        )

        # Initialize states (从统一状态存储加载)
        self.order_state = self._load_order_state()
        self.position_state = self._load_position_state()
        self.risk_state = self._load_risk_state()

        logger.info("Live Execution Manager initialized")

    def _load_live_config(self) -> dict[str, Any]:
        """
        Load live configuration from config_live.json

        Returns:
            Dict[str, Any]: Live configuration
        """
        config_path = os.path.join(self.config_dir, "config_live.json")

        try:
            if os.path.exists(config_path):
                with open(config_path, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load live config: {e}")

        return {}

    def _load_order_state(self) -> dict[str, Any]:
        """
        Load order state from unified state storage

        Returns:
            Dict[str, Any]: Order state
        """
        # 从统一状态存储加载订单状态
        portfolio = self.state_storage.get_portfolio()
        if portfolio and "orders" in portfolio:
            return portfolio["orders"]

        # 向后兼容：如果统一存储中没有，尝试从文件加载
        try:
            if self.order_state_path.exists():
                with open(self.order_state_path, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load order state: {e}")

        # Default order state
        return {"orders": [], "last_updated": time.time()}

    def _load_position_state(self) -> dict[str, Any]:
        """
        Load position state from unified state storage

        Returns:
            Dict[str, Any]: Position state
        """
        # 从统一状态存储加载持仓状态
        positions = self.state_storage.get_all_positions()
        if positions:
            total_exposure = sum(abs(pos.get("notional", 0.0)) for pos in positions.values())
            return {
                "positions": positions,
                "total_exposure": total_exposure,
                "last_updated": time.time(),
            }

        # 向后兼容：如果统一存储中没有，尝试从文件加载
        try:
            if self.position_state_path.exists():
                with open(self.position_state_path, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load position state: {e}")

        # Default position state
        return {"positions": {}, "total_exposure": 0.0, "last_updated": time.time()}

    def _load_risk_state(self) -> dict[str, Any]:
        """
        Load risk state from file

        Returns:
            Dict[str, Any]: Risk state
        """
        try:
            if self.risk_state_path.exists():
                with open(self.risk_state_path, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load risk state: {e}")

        # Default risk state
        return {"total_usdt_exposure": 0.0, "last_risk_check": time.time(), "risk_status": "SAFE"}

    def _write_order_state(self) -> None:
        """
        Write order state to unified state storage
        """
        try:
            self.order_state["last_updated"] = time.time()

            # 保存到统一状态存储
            portfolio = self.state_storage.get_portfolio() or {}
            portfolio["orders"] = self.order_state
            self.state_storage.save_portfolio(portfolio)

            # 向后兼容：同时保存到文件
            with open(self.order_state_path, "w", encoding="utf-8") as f:
                json.dump(self.order_state, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Failed to write order state: {e}")

    def _write_position_state(self) -> None:
        """
        Write position state to unified state storage
        """
        try:
            self.position_state["last_updated"] = time.time()

            # 保存到统一状态存储
            for symbol, position_data in self.position_state.get("positions", {}).items():
                self.state_storage.save_position(
                    symbol,
                    {
                        "symbol": symbol,
                        "amount": position_data
                        if isinstance(position_data, (int, float))
                        else position_data.get("amount", 0.0),
                        "notional": abs(position_data)
                        if isinstance(position_data, (int, float))
                        else abs(position_data.get("amount", 0.0)),
                        "updated_at": datetime.now().isoformat(),
                    },
                )

            # 向后兼容：同时保存到文件
            with open(self.position_state_path, "w", encoding="utf-8") as f:
                json.dump(self.position_state, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Failed to write position state: {e}")

    def _write_risk_state(self) -> None:
        """
        Write risk state to file
        """
        try:
            self.risk_state["last_risk_check"] = time.time()
            with open(self.risk_state_path, "w", encoding="utf-8") as f:
                json.dump(self.risk_state, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Failed to write risk state: {e}")

    def _save_evidence(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Save evidence to file

        Args:
            event_type: Type of event
            data: Event data
        """
        evidence = {
            "event_type": event_type,
            "data": data,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
        }

        evidence_file = self.evidence_dir / f"{event_type}_{int(time.time())}.json"

        try:
            with open(evidence_file, "w", encoding="utf-8") as f:
                json.dump(evidence, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Failed to save evidence: {e}")

    def check_risk_limits(self, order_amount: float) -> bool:
        """
        Check if order amount is within risk limits

        Args:
            order_amount: Order amount in USDT

        Returns:
            bool: True if within limits, False otherwise
        """
        # Get risk configuration
        risk_config = self.live_config.get("risk", {})
        max_total_usdt = risk_config.get("max_total_usdt", 10.0)
        per_trade_usdt = risk_config.get("per_trade_usdt", 5.0)

        # Check per trade limit
        if order_amount > per_trade_usdt:
            logger.warning(
                f"Order amount {order_amount}u exceeds per trade limit {per_trade_usdt}u"
            )
            return False

        # Check total exposure limit
        total_exposure = self.risk_state.get("total_usdt_exposure", 0.0)
        new_exposure = total_exposure + order_amount

        if new_exposure > max_total_usdt:
            logger.warning(
                f"New total exposure {new_exposure}u exceeds max limit {max_total_usdt}u"
            )
            return False

        return True

    def execute_order(
        self, symbol: str, side: str, amount: float, price: float | None = None
    ) -> dict[str, Any]:
        """
        Execute an order with risk checks

        Args:
            symbol: Trading symbol
            side: Order side (buy/sell)
            amount: Order amount in USDT
            price: Order price (optional)

        Returns:
            Dict[str, Any]: Order execution result
        """
        # Check risk limits first
        if not self.check_risk_limits(amount):
            result = {
                "success": False,
                "status": "BLOCKED",
                "reason": "Risk limit exceeded",
                "order_id": None,
                "timestamp": time.time(),
            }
            self._save_evidence("order_blocked", result)
            return result

        # Get execution configuration
        execution_config = self.live_config.get("execution", {})
        order_type = execution_config.get("order_type", "market" if price is None else "limit")

        # Use real OrderExecutor to execute order
        logger.info(f"Executing {order_type} order: {side} {amount}u {symbol} at {price}")

        try:
            # Call OrderExecution.place_order
            execution_result = self.order_executor.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                amount=amount,
                price=price,
                params={"strategy_id": self.live_config.get("strategy_id", "default")},
            )

            # Convert OrderExecution result to LiveExecutionManager format
            if execution_result.get("code") == "0" and execution_result.get("data"):
                order_data = execution_result["data"][0]
                order_id = order_data.get("ordId") or order_data.get(
                    "clOrdId", f"order_{int(time.time())}_{symbol}_{side}"
                )

                # Update order state
                order = {
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    "type": order_type,
                    "status": order_data.get("state", "filled").upper(),
                    "timestamp": time.time(),
                    "filled_at": time.time() if order_data.get("state") == "filled" else None,
                    "filled_price": price,
                }

                self.order_state["orders"].append(order)
                self._write_order_state()

                # Update position state (simplified, should use actual position data from exchange)
                if symbol not in self.position_state["positions"]:
                    self.position_state["positions"][symbol] = 0.0

                if side == "buy" and order_data.get("state") == "filled":
                    self.position_state["positions"][symbol] += amount
                elif side == "sell" and order_data.get("state") == "filled":
                    self.position_state["positions"][symbol] -= amount

                # Calculate total exposure
                total_exposure = sum(abs(pos) for pos in self.position_state["positions"].values())
                self.position_state["total_exposure"] = total_exposure
                self._write_position_state()

                # Update risk state
                self.risk_state["total_usdt_exposure"] = total_exposure
                self.risk_state["risk_status"] = (
                    "SAFE"
                    if total_exposure
                    <= self.live_config.get("risk", {}).get("max_total_usdt", 10.0)
                    else "BLOCKED"
                )
                self._write_risk_state()

                # Generate result
                result = {
                    "success": True,
                    "status": order_data.get("state", "filled").upper(),
                    "order_id": order_id,
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    "filled_price": price if order_data.get("state") == "filled" else None,
                    "timestamp": time.time(),
                }

                # Save evidence
                self._save_evidence("order_executed", result)

                logger.info(f"Order executed successfully: {order_id}")
                return result
            else:
                # Order execution failed
                error_msg = execution_result.get("msg", "Unknown error")
                result = {
                    "success": False,
                    "status": "FAILED",
                    "reason": error_msg,
                    "order_id": None,
                    "timestamp": time.time(),
                }
                self._save_evidence("order_execution_failed", result)
                logger.error(f"Order execution failed: {error_msg}")
                return result

        except Exception as e:
            # Handle execution errors
            error_msg = str(e)
            result = {
                "success": False,
                "status": "ERROR",
                "reason": error_msg,
                "order_id": None,
                "timestamp": time.time(),
            }
            self._save_evidence("order_execution_error", result)
            logger.error(f"Order execution error: {error_msg}", exc_info=True)
            return result

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """
        Cancel an order

        Args:
            order_id: Order ID to cancel

        Returns:
            Dict[str, Any]: Cancel result
        """
        # Find the order
        order_index = -1
        for i, order in enumerate(self.order_state["orders"]):
            if order["order_id"] == order_id:
                order_index = i
                break

        if order_index == -1:
            result = {
                "success": False,
                "reason": f"Order {order_id} not found",
                "timestamp": time.time(),
            }
            self._save_evidence("order_cancel_failed", result)
            return result

        # Update order status
        order = self.order_state["orders"][order_index]
        order["status"] = "CANCELLED"
        order["cancelled_at"] = time.time()
        self.order_state["orders"][order_index] = order
        self._write_order_state()

        result = {
            "success": True,
            "order_id": order_id,
            "status": "CANCELLED",
            "timestamp": time.time(),
        }

        self._save_evidence("order_cancelled", result)
        logger.info(f"Order cancelled: {order_id}")
        return result

    def get_current_state(self) -> dict[str, Any]:
        """
        Get current state

        Returns:
            Dict[str, Any]: Current state including orders, positions, and risk
        """
        return {
            "order_state": self.order_state,
            "position_state": self.position_state,
            "risk_state": self.risk_state,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
        }

    def run_drill(self) -> dict[str, Any]:
        """
        Run a drill (simulated live execution)

        Returns:
            Dict[str, Any]: Drill results
        """
        logger.info("Starting live execution drill...")

        drill_result = {
            "drill_id": f"drill_{int(time.time())}",
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "steps": [],
            "overall_status": "PASS",
        }

        # Step 1: Check initial state
        initial_state = self.get_current_state()
        drill_result["steps"].append(
            {
                "step": 1,
                "description": "Initial state check",
                "status": "PASS",
                "details": {
                    "total_exposure": initial_state["risk_state"].get("total_usdt_exposure", 0.0),
                    "order_count": len(initial_state["order_state"].get("orders", [])),
                },
            }
        )

        # Step 2: Try to execute a valid order (within limits)
        logger.info("Step 2: Executing valid order within limits...")
        valid_order = self.execute_order("ETH-USDT", "buy", 3.0, 2000.0)
        drill_result["steps"].append(
            {
                "step": 2,
                "description": "Execute valid order within limits",
                "status": "PASS" if valid_order["success"] else "FAIL",
                "details": valid_order,
            }
        )

        if not valid_order["success"]:
            drill_result["overall_status"] = "FAIL"

        # Step 3: Try to execute an order exceeding per trade limit
        logger.info("Step 3: Trying to execute order exceeding per trade limit...")
        invalid_order = self.execute_order("BTC-USDT", "buy", 10.0, 40000.0)
        drill_result["steps"].append(
            {
                "step": 3,
                "description": "Execute order exceeding per trade limit",
                "status": "PASS" if not invalid_order["success"] else "FAIL",
                "details": invalid_order,
            }
        )

        if invalid_order["success"]:
            drill_result["overall_status"] = "FAIL"

        # Step 4: Check final state
        final_state = self.get_current_state()
        drill_result["steps"].append(
            {
                "step": 4,
                "description": "Final state check",
                "status": "PASS",
                "details": {
                    "total_exposure": final_state["risk_state"].get("total_usdt_exposure", 0.0),
                    "order_count": len(final_state["order_state"].get("orders", [])),
                },
            }
        )

        # Save drill results as evidence
        self._save_evidence("drill_executed", drill_result)

        logger.info(f"Drill completed with status: {drill_result['overall_status']}")
        return drill_result

    def reset_state(self) -> None:
        """
        Reset all states to initial values
        """
        # Reset order state
        self.order_state = {"orders": [], "last_updated": time.time()}
        self._write_order_state()

        # Reset position state
        self.position_state = {"positions": {}, "total_exposure": 0.0, "last_updated": time.time()}
        self._write_position_state()

        # Reset risk state
        self.risk_state = {
            "total_usdt_exposure": 0.0,
            "last_risk_check": time.time(),
            "risk_status": "SAFE",
        }
        self._write_risk_state()

        logger.info("All states reset to initial values")
        self._save_evidence("state_reset", {"message": "All states reset"})


if __name__ == "__main__":
    # Run a drill as example
    manager = LiveExecutionManager()
    drill_result = manager.run_drill()
    print(json.dumps(drill_result, indent=2, ensure_ascii=False))
    manager.reset_state()
