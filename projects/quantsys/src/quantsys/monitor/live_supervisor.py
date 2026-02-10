#!/usr/bin/env python3
"""
Live Supervisor Module

This module implements the LiveSupervisor class which monitors:
- Heartbeats for market data, account, and orders
- Triggers SAFE_STOP when any heartbeat times out
- Implements reconnection with retry count and backoff strategy
- Manages SAFE_STOP behavior: no new positions, only closing positions and reconciliation
- Outputs live_supervisor_status.json
"""

import json
import logging
import os
import threading
import time
from datetime import UTC, datetime
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LiveSupervisor:
    """
    Live Supervisor class for monitoring live trading systems
    """

    # State machine definitions
    STATE_NORMAL = "NORMAL"
    STATE_SAFE_STOP = "SAFE_STOP"
    STATE_RECONNECTING = "RECONNECTING"

    def __init__(self, config: dict[str, Any] = None):
        """
        Initialize LiveSupervisor

        Args:
            config: Configuration dictionary
        """
        self.config = config or {}

        # Heartbeat configuration
        self.heartbeat_timeout = self.config.get("heartbeat_timeout", 30)  # seconds
        self.heartbeat_check_interval = self.config.get("heartbeat_check_interval", 5)  # seconds

        # Reconnection configuration
        self.max_retry_count = self.config.get("max_retry_count", 5)
        self.initial_backoff = self.config.get("initial_backoff", 1)  # seconds
        self.max_backoff = self.config.get("max_backoff", 30)  # seconds

        # Status file path
        self.status_file_path = self.config.get("status_file_path", "live_supervisor_status.json")

        # Blocking issues file path (shared with other components)
        self.blocking_issues_path = self.config.get(
            "blocking_issues_path", "data/blocking_issues.json"
        )

        # Heartbeat tracking
        self.heartbeats = {
            "market_data": {"last_heartbeat": time.time(), "timeout": False, "retry_count": 0},
            "account": {"last_heartbeat": time.time(), "timeout": False, "retry_count": 0},
            "orders": {"last_heartbeat": time.time(), "timeout": False, "retry_count": 0},
        }

        # State management
        self.state = self.STATE_NORMAL
        self.last_state_change = time.time()
        self.state_reason = "Initial state"

        # Monitoring thread
        self.monitor_thread = None
        self.running = False

        # Initialize status file
        self._write_status()

    def start(self):
        """
        Start the live supervisor monitoring
        """
        if self.running:
            logger.warning("LiveSupervisor is already running")
            return

        logger.info("Starting LiveSupervisor")
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop(self):
        """
        Stop the live supervisor monitoring
        """
        logger.info("Stopping LiveSupervisor")
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

    def update_heartbeat(self, component: str):
        """
        Update the heartbeat for a component

        Args:
            component: Component name (market_data, account, orders)
        """
        if component not in self.heartbeats:
            logger.warning(f"Unknown component: {component}")
            return

        self.heartbeats[component]["last_heartbeat"] = time.time()
        self.heartbeats[component]["timeout"] = False
        self.heartbeats[component]["retry_count"] = 0
        logger.debug(f"Updated heartbeat for {component}")

    def _monitor_loop(self):
        """
        Main monitoring loop
        """
        while self.running:
            current_time = time.time()

            # Check heartbeats
            self._check_heartbeats(current_time)

            # Update status file
            self._write_status()

            # Sleep for check interval
            time.sleep(self.heartbeat_check_interval)

    def _check_heartbeats(self, current_time: float):
        """
        Check all heartbeats for timeouts

        Args:
            current_time: Current time in seconds
        """
        timeout_detected = False
        timeout_components = []

        # Check each component's heartbeat
        for component, info in self.heartbeats.items():
            time_since_last_heartbeat = current_time - info["last_heartbeat"]

            if time_since_last_heartbeat > self.heartbeat_timeout:
                info["timeout"] = True
                info["retry_count"] += 1
                timeout_detected = True
                timeout_components.append(component)
                logger.warning(
                    f"Heartbeat timeout for {component}: {time_since_last_heartbeat:.1f}s, retry count: {info['retry_count']}"
                )
            else:
                info["timeout"] = False

        # Handle timeout conditions
        if timeout_detected:
            if self.state == self.STATE_NORMAL:
                # Transition to SAFE_STOP
                self._enter_safe_stop(
                    f"Heartbeat timeout for components: {', '.join(timeout_components)}"
                )
            elif self.state == self.STATE_SAFE_STOP:
                # Already in SAFE_STOP, continue monitoring
                pass
        else:
            # All heartbeats are healthy
            if self.state == self.STATE_RECONNECTING:
                # Transition back to NORMAL if reconnection succeeded
                self._enter_normal("All heartbeats restored")

    def _enter_safe_stop(self, reason: str):
        """
        Enter SAFE_STOP state

        Args:
            reason: Reason for entering SAFE_STOP
        """
        logger.error(f"Entering SAFE_STOP state: {reason}")
        self.state = self.STATE_SAFE_STOP
        self.last_state_change = time.time()
        self.state_reason = reason

        # Execute SAFE_STOP actions
        self._execute_safe_stop()

    def _enter_normal(self, reason: str):
        """
        Enter NORMAL state

        Args:
            reason: Reason for entering NORMAL
        """
        logger.info(f"Entering NORMAL state: {reason}")
        self.state = self.STATE_NORMAL
        self.last_state_change = time.time()
        self.state_reason = reason

        # Clear any previous blocking issues related to heartbeats
        self._clear_heartbeat_blocking_issues()

    def _enter_reconnecting(self, component: str, reason: str):
        """
        Enter RECONNECTING state for a specific component

        Args:
            component: Component that's reconnecting
            reason: Reason for reconnecting
        """
        logger.info(f"Entering RECONNECTING state for {component}: {reason}")
        # Note: We don't change the global state to RECONNECTING,
        # but track retry counts per component
        pass

    def _execute_safe_stop(self):
        """
        Execute SAFE_STOP actions:
        - Write to blocking_issues.json
        - Prevent new positions, allow only closing positions and reconciliation
        """
        # Create blocking issue
        blocking_issue = {
            "timestamp": datetime.now(UTC).isoformat(),
            "issues": [
                {
                    "issue_id": "heartbeat_timeout",
                    "issue_type": "supervisor",
                    "status": "blocked",
                    "message": f"LiveSupervisor SAFE_STOP triggered: {self.state_reason}",
                }
            ],
        }

        # Write to blocking_issues.json
        self._write_blocking_issues(blocking_issue)

    def _write_blocking_issues(self, new_issues: dict[str, Any]):
        """
        Write blocking issues to file, merging with existing issues

        Args:
            new_issues: New blocking issues to add
        """
        # Get directory name (empty string if no directory)
        dir_name = os.path.dirname(self.blocking_issues_path)

        # Ensure directory exists only if it's not empty
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # Read existing issues if file exists
        existing_issues = {"timestamp": datetime.now(UTC).isoformat(), "issues": []}

        if os.path.exists(self.blocking_issues_path):
            try:
                with open(self.blocking_issues_path, encoding="utf-8") as f:
                    existing_issues = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Error reading existing blocking issues: {e}")

        # Add new issues, avoiding duplicates by issue_id
        existing_issue_ids = {issue["issue_id"] for issue in existing_issues.get("issues", [])}
        for new_issue in new_issues.get("issues", []):
            if new_issue["issue_id"] not in existing_issue_ids:
                existing_issues["issues"].append(new_issue)
                existing_issue_ids.add(new_issue["issue_id"])

        # Update timestamp
        existing_issues["timestamp"] = datetime.now(UTC).isoformat()

        # Write back to file
        try:
            with open(self.blocking_issues_path, "w", encoding="utf-8") as f:
                json.dump(existing_issues, f, indent=2, ensure_ascii=False)
            logger.info(f"Written blocking issues to {self.blocking_issues_path}")
        except OSError as e:
            logger.error(f"Error writing blocking issues: {e}")

    def _clear_heartbeat_blocking_issues(self):
        """
        Clear heartbeat-related blocking issues
        """
        if not os.path.exists(self.blocking_issues_path):
            return

        try:
            with open(self.blocking_issues_path, encoding="utf-8") as f:
                issues = json.load(f)

            # Filter out heartbeat-related issues
            filtered_issues = [
                issue
                for issue in issues.get("issues", [])
                if issue.get("issue_id") != "heartbeat_timeout"
            ]

            issues["issues"] = filtered_issues
            issues["timestamp"] = datetime.now(UTC).isoformat()

            with open(self.blocking_issues_path, "w", encoding="utf-8") as f:
                json.dump(issues, f, indent=2, ensure_ascii=False)

            if len(filtered_issues) < len(issues.get("issues", [])):
                logger.info("Cleared heartbeat-related blocking issues")
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Error clearing heartbeat blocking issues: {e}")

    def _write_status(self):
        """
        Write current status to live_supervisor_status.json
        """
        # Create status dictionary
        status_dict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "state": self.state,
            "last_state_change": datetime.fromtimestamp(self.last_state_change, UTC).isoformat(),
            "state_reason": self.state_reason,
            "heartbeats": {},
        }

        # Add heartbeats
        for component, info in self.heartbeats.items():
            status_dict["heartbeats"][component] = {
                "last_heartbeat": datetime.fromtimestamp(info["last_heartbeat"], UTC).isoformat(),
                "time_since_last_heartbeat": time.time() - info["last_heartbeat"],
                "timeout": info["timeout"],
                "retry_count": info["retry_count"],
            }

        # Add config
        status_dict["config"] = {
            "heartbeat_timeout": self.heartbeat_timeout,
            "heartbeat_check_interval": self.heartbeat_check_interval,
            "max_retry_count": self.max_retry_count,
            "initial_backoff": self.initial_backoff,
            "max_backoff": self.max_backoff,
        }

        try:
            with open(self.status_file_path, "w", encoding="utf-8") as f:
                json.dump(status_dict, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Error writing status file: {e}")

    def get_status(self) -> dict[str, Any]:
        """
        Get current supervisor status

        Returns:
            Dict[str, Any]: Current status information
        """
        current_time = time.time()
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "state": self.state,
            "last_state_change": datetime.fromtimestamp(self.last_state_change, UTC).isoformat(),
            "state_reason": self.state_reason,
            "heartbeats": {
                component: {
                    "last_heartbeat": datetime.fromtimestamp(
                        info["last_heartbeat"], UTC
                    ).isoformat(),
                    "time_since_last_heartbeat": current_time - info["last_heartbeat"],
                    "timeout": info["timeout"],
                    "retry_count": info["retry_count"],
                }
                for component, info in self.heartbeats.items()
            },
        }

    def is_safe_stop(self) -> bool:
        """
        Check if system is in SAFE_STOP state

        Returns:
            bool: True if in SAFE_STOP state, False otherwise
        """
        return self.state == self.STATE_SAFE_STOP

    def reset(self):
        """
        Reset supervisor state and heartbeats
        """
        logger.info("Resetting LiveSupervisor")

        # Reset heartbeats
        current_time = time.time()
        for component in self.heartbeats:
            self.heartbeats[component] = {
                "last_heartbeat": current_time,
                "timeout": False,
                "retry_count": 0,
            }

        # Reset state
        self.state = self.STATE_NORMAL
        self.last_state_change = current_time
        self.state_reason = "Reset by user"

        # Clear blocking issues
        self._clear_heartbeat_blocking_issues()

        # Update status file
        self._write_status()

    def get_reconnection_delay(self, retry_count: int) -> float:
        """
        Calculate reconnection delay using exponential backoff

        Args:
            retry_count: Current retry count

        Returns:
            float: Delay in seconds
        """
        delay = self.initial_backoff * (
            2 ** min(retry_count, 10)
        )  # Cap at 10 to avoid excessive delays
        return min(delay, self.max_backoff)

    def __del__(self):
        """
        Cleanup when instance is deleted
        """
        self.stop()


# Example usage
if __name__ == "__main__":
    # Create a simple test script
    supervisor = LiveSupervisor()
    supervisor.start()

    try:
        # Run for 60 seconds, updating heartbeats every 10 seconds
        for i in range(6):
            supervisor.update_heartbeat("market_data")
            supervisor.update_heartbeat("account")
            supervisor.update_heartbeat("orders")
            logger.info(f"Heartbeats updated, current status: {supervisor.get_status()['state']}")
            time.sleep(10)

        # Simulate heartbeat timeout for market_data
        logger.info("Simulating market_data heartbeat timeout...")
        time.sleep(40)  # Wait for timeout

        # Check status
        status = supervisor.get_status()
        logger.info(f"Final status: {status['state']}, reason: {status['state_reason']}")

    finally:
        supervisor.stop()
        logger.info("LiveSupervisor stopped")
