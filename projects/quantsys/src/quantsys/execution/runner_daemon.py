
#!/usr/bin/env python3
"""
Live Trading Runner Daemon

This daemon manages the live trading strategy with:
- Automatic restart on abnormal exit
- State recovery on startup (orders/positions/mode)
- Graceful shutdown support
- Compliance with System Invariants
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.quantsys.execution.local_state import LocalStateStore, get_local_snapshot
from src.quantsys.execution.readiness import ExecutionReadiness

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"logs/runner_daemon_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("runner_daemon")


@dataclass
class RunnerConfig:
    """Runner configuration."""

    strategy_script: str
    config_path: str
    max_restarts: int = 3
    restart_delay: int = 30
    health_check_interval: int = 60
    enable_auto_restart: bool = True
    enable_graceful_shutdown: bool = True


@dataclass
class RunnerState:
    """Runner state for persistence."""

    pid: int = 0
    restart_count: int = 0
    last_restart_time: float = 0.0
    last_health_check: float = 0.0
    trading_mode: str = "OFFLINE"
    shutdown_requested: bool = False


class LiveRunnerDaemon:
    """
    Live trading runner daemon.

    This daemon manages the live trading strategy with:
    - Automatic restart on abnormal exit
    - State recovery on startup
    - Graceful shutdown support
    - Compliance with System Invariants
    """

    def __init__(self, config: RunnerConfig):
        """
        Initialize the daemon.

        Args:
            config: Runner configuration
        """
        self.config = config
        self.state = RunnerState()
        self.process: subprocess.Popen | None = None
        self.readiness = ExecutionReadiness()
        self.state_store = LocalStateStore()
        self._shutdown_event = threading.Event()
        self._health_check_thread: threading.Thread | None = None

        # Ensure required directories exist
        Path("data/state").mkdir(parents=True, exist_ok=True)
        Path("logs").mkdir(parents=True, exist_ok=True)
        Path("reports").mkdir(parents=True, exist_ok=True)

        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()

        # Register atexit handler for cleanup
        atexit.register(self._cleanup)

        logger.info("Live Runner Daemon initialized")
        logger.info(f"Strategy script: {config.strategy_script}")
        logger.info(f"Config path: {config.config_path}")
        logger.info(f"Max restarts: {config.max_restarts}")
        logger.info(f"Auto restart enabled: {config.enable_auto_restart}")

    def _register_signal_handlers(self):
        """Register signal handlers for graceful shutdown."""
        if self.config.enable_graceful_shutdown:
            signal.signal(signal.SIGTERM, self._handle_shutdown_signal)
            signal.signal(signal.SIGINT, self._handle_shutdown_signal)
            logger.info("Signal handlers registered for graceful shutdown")

    def _handle_shutdown_signal(self, signum, frame):
        """Handle shutdown signal (SIGTERM/SIGINT)."""
        logger.info(f"Received shutdown signal: {signum}")
        self.state.shutdown_requested = True
        self._shutdown_event.set()
        self._stop_strategy_process()

    def _load_state(self) -> RunnerState:
        """
        Load runner state from file.

        Returns:
            RunnerState: Loaded state
        """
        state_file = Path("data/state/runner_state.json")

        if state_file.exists():
            try:
                with open(state_file) as f:
                    state_data = json.load(f)
                    return RunnerState(**state_data)
            except Exception as e:
                logger.error(f"Failed to load runner state: {e}")

        return RunnerState()

    def _save_state(self):
        """Save runner state to file."""
        state_file = Path("data/state/runner_state.json")

        state_data = {
            "pid": self.state.pid,
            "restart_count": self.state.restart_count,
            "last_restart_time": self.state.last_restart_time,
            "last_health_check": self.state.last_health_check,
            "trading_mode": self.state.trading_mode,
            "shutdown_requested": self.state.shutdown_requested,
        }

        try:
            with open(state_file, "w") as f:
                json.dump(state_data, f, indent=2)
            logger.debug(f"Runner state saved: {state_file}")
        except Exception as e:
            logger.error(f"Failed to save runner state: {e}")

    def _recover_state(self):
        """
        Recover state on startup.

        This includes:
        - Loading previous orders
        - Loading previous positions
        - Loading trading mode
        """
        logger.info("Recovering state on startup...")

        # Get local snapshot
        snapshot = get_local_snapshot(self.state_store)

        # Log recovered state
        logger.info(f"Recovered balances: {len(snapshot.balances)}")
        logger.info(f"Recovered positions: {len(snapshot.positions)}")
        logger.info(f"Recovered open orders: {len(snapshot.open_orders)}")
        logger.info(f"Recovered recent fills: {len(snapshot.recent_fills)}")

        # Log positions details
        for position in snapshot.positions:
            logger.info(
                f"Position: {position.symbol} {position.side} size={position.size} entry={position.entry_price}"
            )

        # Log open orders details
        for order in snapshot.open_orders:
            logger.info(
                f"Open Order: {order.symbol} {order.side} type={order.type} price={order.price} amount={order.amount}"
            )

        # Update runner state with trading mode
        self.state.trading_mode = self._determine_trading_mode(snapshot)
        logger.info(f"Trading mode determined: {self.state.trading_mode}")

        # Write recovery evidence
        self._write_recovery_evidence(snapshot)

    def _determine_trading_mode(self, snapshot) -> str:
        """
        Determine trading mode from snapshot.

        Args:
            snapshot: Local state snapshot

        Returns:
            str: Trading mode (OFFLINE/DRY_RUN/LIVE)
        """
        # Check if there are any positions or orders
        has_positions = len(snapshot.positions) > 0
        has_orders = len(snapshot.open_orders) > 0

        if has_positions or has_orders:
            # Determine if LIVE or DRY_RUN based on state
            # For now, assume DRY_RUN if there are positions/orders
            return "DRY_RUN"

        return "OFFLINE"

    def _write_recovery_evidence(self, snapshot):
        """
        Write recovery evidence to file.

        Args:
            snapshot: Local state snapshot
        """
        evidence_file = Path("reports/state_recovery.json")

        evidence = {
            "timestamp": datetime.now().isoformat(),
            "recovered": True,
            "balances_count": len(snapshot.balances),
            "positions_count": len(snapshot.positions),
            "open_orders_count": len(snapshot.open_orders),
            "fills_count": len(snapshot.recent_fills),
            "trading_mode": self.state.trading_mode,
            "positions": [
                {
                    "symbol": pos.symbol,
                    "side": pos.side,
                    "size": pos.size,
                    "entry_price": pos.entry_price,
                    "unrealized_pnl": pos.unrealized_pnl,
                }
                for pos in snapshot.positions
            ],
            "open_orders": [
                {
                    "id": order.id,
                    "client_order_id": order.client_order_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "type": order.type,
                    "price": order.price,
                    "amount": order.amount,
                    "filled": order.filled,
                    "status": order.status,
                }
                for order in snapshot.open_orders
            ],
        }

        try:
            with open(evidence_file, "w") as f:
                json.dump(evidence, f, indent=2, ensure_ascii=False)
            logger.info(f"Recovery evidence written: {evidence_file}")
        except Exception as e:
            logger.error(f"Failed to write recovery evidence: {e}")

    def _check_readiness_before_start(self) -> bool:
        """
        Check execution readiness before starting strategy.

        This enforces System Invariants:
        - Execution Readiness is the single source of truth
        - BLOCKED state prohibits all writes and side effects

        Returns:
            bool: True if ready to start, False otherwise
        """
        logger.info("Checking execution readiness before starting strategy...")

        # Run reconciliation to check drift
        try:
            # Get local snapshot
            local_snapshot = get_local_snapshot(self.state_store)

            # Run reconciliation using module-level reconcile function
            # Import reconcile function from reconciliation module
            from src.quantsys.execution.reconciliation import reconcile

            # Run reconciliation (mock exchange snapshot for now)
            # In production, this would fetch actual exchange state
            report = reconcile(
                exchange_client=None,  # Mock: no exchange client
                local_state={
                    "balances": {
                        k: {"total": v.total, "available": v.available}
                        for k, v in local_snapshot.balances.items()
                    },
                    "positions": [
                        {
                            "symbol": p.symbol,
                            "side": p.side,
                            "size": p.size,
                            "entry_price": p.entry_price,
                            "unrealized_pnl": p.unrealized_pnl,
                        }
                        for p in local_snapshot.positions
                    ],
                    "orders": [
                        {
                            "id": o.id,
                            "clientOrderId": o.client_order_id,
                            "symbol": o.symbol,
                            "side": o.side.lower(),
                            "type": o.type.lower(),
                            "price": o.price,
                            "amount": o.amount,
                            "filled": o.filled,
                            "status": o.status.lower(),
                        }
                        for o in local_snapshot.open_orders
                    ],
                    "fills": [
                        {
                            "id": f.id,
                            "order_id": f.order_id,
                            "symbol": f.symbol,
                            "side": f.side.lower(),
                            "price": f.price,
                            "amount": f.amount,
                            "timestamp": f.timestamp,
                        }
                        for f in local_snapshot.recent_fills
                    ],
                },
                symbol_map={},
                now_ts=int(time.time() * 1000),
                config={},
            )

            # Update readiness status
            self.readiness.update_reconciliation_status(report)

            # Check if ready
            if self.readiness.is_blocked():
                blocked_reasons = self.readiness.get_blocked_reasons()
                logger.error("System is BLOCKED, cannot start strategy")
                for reason in blocked_reasons:
                    logger.error(f"  - {reason}")
                return False

            logger.info("System is READY, can start strategy")
            return True

        except Exception as e:
            logger.error(f"Failed to check readiness: {e}")
            return False

    def _start_strategy_process(self) -> bool:
        """
        Start the strategy process.

        Returns:
            bool: True if started successfully, False otherwise
        """
        if not self._check_readiness_before_start():
            logger.error("Cannot start strategy: system not ready")
            return False

        logger.info(f"Starting strategy process: {self.config.strategy_script}")

        try:
            # Start the strategy as a subprocess
            self.process = subprocess.Popen(
                [sys.executable, self.config.strategy_script],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            self.state.pid = self.process.pid
            self._save_state()

            logger.info(f"Strategy process started with PID: {self.state.pid}")
            return True

        except Exception as e:
            logger.error(f"Failed to start strategy process: {e}")
            return False

    def _stop_strategy_process(self):
        """Stop the strategy process gracefully."""
        if self.process and self.process.poll() is None:
            logger.info(f"Stopping strategy process (PID: {self.state.pid})...")

            try:
                # Send SIGTERM for graceful shutdown
                self.process.terminate()

                # Wait for process to terminate (up to 30 seconds)
                try:
                    self.process.wait(timeout=30)
                    logger.info("Strategy process terminated gracefully")
                except subprocess.TimeoutExpired:
                    logger.warning("Strategy process did not terminate gracefully, forcing kill")
                    self.process.kill()
                    self.process.wait()
                    logger.info("Strategy process killed")

            except Exception as e:
                logger.error(f"Error stopping strategy process: {e}")

        self.process = None
        self.state.pid = 0
        self._save_state()

    def _monitor_process(self):
        """Monitor the strategy process and handle abnormal exits."""
        if not self.process:
            return

        # Check if process has exited
        return_code = self.process.poll()

        if return_code is not None:
            logger.info(f"Strategy process exited with code: {return_code}")

            # Check if exit was abnormal
            if return_code != 0 and self.config.enable_auto_restart:
                self._handle_abnormal_exit(return_code)
            else:
                logger.info("Strategy process exited normally")
                self.state.shutdown_requested = True
                self._shutdown_event.set()

    def _handle_abnormal_exit(self, exit_code: int):
        """
        Handle abnormal strategy exit.

        Args:
            exit_code: Exit code from the process
        """
        logger.warning(f"Abnormal exit detected (code: {exit_code})")

        # Check restart limit
        if self.state.restart_count >= self.config.max_restarts:
            logger.error(f"Max restarts ({self.config.max_restarts}) reached, not restarting")
            self.state.shutdown_requested = True
            self._shutdown_event.set()
            return

        # Increment restart count
        self.state.restart_count += 1
        self.state.last_restart_time = time.time()
        self._save_state()

        logger.info(f"Restart count: {self.state.restart_count}/{self.config.max_restarts}")

        # Wait before restart
        logger.info(f"Waiting {self.config.restart_delay} seconds before restart...")
        self._shutdown_event.wait(self.config.restart_delay)

        if self.state.shutdown_requested:
            logger.info("Shutdown requested, cancelling restart")
            return

        # Restart the strategy
        logger.info("Restarting strategy process...")
        self._start_strategy_process()

    def _health_check(self):
        """Perform health check on the strategy process."""
        if not self.process:
            return

        # Check if process is still running
        if self.process.poll() is not None:
            logger.warning("Health check: Process not running")
            self._monitor_process()
            return

        # Update last health check time
        self.state.last_health_check = time.time()
        self._save_state()

        # Check execution readiness
        if self.readiness.is_blocked():
            logger.warning("Health check: System is BLOCKED, stopping strategy")
            self._stop_strategy_process()
            self.state.shutdown_requested = True
            self._shutdown_event.set()

    def _start_health_check_thread(self):
        """Start the health check thread."""

        def health_check_loop():
            while not self._shutdown_event.is_set():
                try:
                    self._health_check()
                except Exception as e:
                    logger.error(f"Health check error: {e}")

                # Wait for next check
                self._shutdown_event.wait(self.config.health_check_interval)

        self._health_check_thread = threading.Thread(target=health_check_loop, daemon=True)
        self._health_check_thread.start()
        logger.info("Health check thread started")

    def _write_runner_status(self):
        """Write runner status to file for monitoring."""
        status_file = Path("reports/runner_status.json")

        status = {
            "timestamp": datetime.now().isoformat(),
            "pid": self.state.pid,
            "running": self.process is not None and self.process.poll() is None,
            "restart_count": self.state.restart_count,
            "max_restarts": self.config.max_restarts,
            "trading_mode": self.state.trading_mode,
            "shutdown_requested": self.state.shutdown_requested,
            "readiness": {"ok": self.readiness.is_ready(), "blocked": self.readiness.is_blocked()},
        }

        try:
            with open(status_file, "w") as f:
                json.dump(status, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to write runner status: {e}")

    def _cleanup(self):
        """Cleanup on exit."""
        logger.info("Cleaning up daemon...")

        # Stop strategy process if running
        self._stop_strategy_process()

        # Write final status
        self._write_runner_status()

        # Save final state
        self._save_state()

        logger.info("Daemon cleanup complete")

    def run(self):
        """
        Run the daemon.

        This is the main entry point for the daemon.
        """
        logger.info("=== Starting Live Runner Daemon ===")

        # Load previous state
        self.state = self._load_state()
        logger.info(f"Loaded runner state: restart_count={self.state.restart_count}")

        # Recover state on startup
        self._recover_state()

        # Start health check thread
        self._start_health_check_thread()

        # Main loop
        while not self.state.shutdown_requested:
            try:
                # Start strategy process if not running
                if self.process is None or self.process.poll() is not None:
                    if not self._start_strategy_process():
                        logger.error("Failed to start strategy process, exiting")
                        break

                # Monitor process
                self._monitor_process()

                # Write status
                self._write_runner_status()

                # Wait for shutdown event or health check interval
                self._shutdown_event.wait(min(self.config.health_check_interval, 10))

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                # Continue running despite errors

        logger.info("=== Live Runner Daemon Stopped ===")


def load_config(config_path: str) -> RunnerConfig:
    """
    Load runner configuration from file.

    Args:
        config_path: Path to configuration file

    Returns:
        RunnerConfig: Loaded configuration
    """
    with open(config_path) as f:
        config_data = json.load(f)

    return RunnerConfig(**config_data)


def main():
    """Main entry point."""
    # Load configuration
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/runner_config.json"

    try:
        config = load_config(config_path)
        logger.info(f"Configuration loaded from: {config_path}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        logger.info("Using default configuration")
        config = RunnerConfig(
            strategy_script="src/quantsys/execution/run_live_strategy.py",
            config_path="live_strategy_config.json",
        )

    # Create and run daemon
    daemon = LiveRunnerDaemon(config)

    try:
        daemon.run()
    except KeyboardInterrupt:
        logger.info("Daemon interrupted by user")
    except Exception as e:
        logger.error(f"Daemon error: {e}")
    finally:
        daemon._cleanup()


if __name__ == "__main__":
    main()
