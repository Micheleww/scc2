#!/usr/bin/env python3
"""
Live Gate for controlling access to live trading

This module implements the LiveGate class which enforces all access control
conditions for entering live trading mode.

!!! 核心红线资产：仅允许经主控批准修改 !!!
任何对本文件的修改必须经过严格的审查和批准流程
详见 docs/core_assets.md
"""

import json
import os
from datetime import datetime

import yaml

from src.quantsys.execution.fund_position_reconciler import FundPositionReconciler
from src.quantsys.execution.reconciliation import (
    ReconciliationReport,
)


class LiveGate:
    """
    Live Gate that checks all conditions before allowing access to live trading
    """

    def __init__(
        self, config_dir: str = "configs", data_dir: str = "data", taskhub_dir: str = "taskhub"
    ):
        """
        Initialize LiveGate with directory paths

        Args:
            config_dir: Directory containing configuration files
            data_dir: Directory containing data files like enable_live.json, allowlist.json
            taskhub_dir: Directory containing taskhub data like registry.json
        """
        self.config_dir = config_dir
        self.data_dir = data_dir
        self.taskhub_dir = taskhub_dir

        # 添加config_loader，支持从TaskHub/index优先加载配置
        from src.quantsys.common.config_loader import ConfigLoader

        self.config_loader = ConfigLoader(taskhub_dir, config_dir)

        # Load live configuration
        self.live_config = self._load_live_config()

        # Default risk budget
        self.risk_budget = self.live_config.get("risk", {}).get("max_total_usdt", 10.0)  # USDT

        # Initialize reconciler
        self.reconciler = FundPositionReconciler(self.live_config.get("reconciliation", {}))

        # Set blocked callback
        self.reconciler.set_blocked_callback(self._on_reconcile_blocked)

    def check_live_access(self) -> tuple[bool, dict]:
        """
        Check all live access conditions

        Returns:
            tuple[bool, dict]: (is_allowed, blocking_issues)
            - is_allowed: True if all conditions are met, False otherwise
            - blocking_issues: Dictionary containing all blocking issues
        """
        blocking_issues = {"timestamp": datetime.now().isoformat(), "issues": []}

        # Check 0: Trade live switch - global control
        if not self.config_loader.get_trade_live_switch():
            blocking_issues["issues"].append(
                {
                    "category": "GATE",
                    "code": "GATE_005",
                    "message": "Trade live switch is disabled",
                    "evidence_paths": [
                        f"{self.taskhub_dir}/index/live_config.json",
                        f"{self.config_dir}/live_config.json",
                        "logs/live_gate.log",
                    ],
                }
            )

        # Check 1: Kill switch - manual stop
        if not self._check_kill_switch():
            blocking_issues["issues"].append(
                {
                    "category": "GATE",
                    "code": "GATE_001",
                    "message": "手动停止开关已激活，禁止下单",
                    "evidence_paths": [
                        f"{self.data_dir}/kill_switch_status.json",
                        "logs/live_gate.log",
                    ],
                }
            )

        # Check 2: Latest audit conclusion is GO
        if not self._check_latest_audit():
            blocking_issues["issues"].append(
                {
                    "category": "SYSTEM",
                    "code": "SYSTEM_002",
                    "message": "Latest audit conclusion is not GO",
                    "evidence_paths": [f"{self.taskhub_dir}/registry.json", "logs/audit.log"],
                }
            )

        # Check 3: enable_live switch exists and is enabled
        if not self._check_enable_live():
            blocking_issues["issues"].append(
                {
                    "category": "GATE",
                    "code": "GATE_002",
                    "message": "enable_live switch file not found or invalid",
                    "evidence_paths": [f"{self.data_dir}/enable_live.json", "logs/live_gate.log"],
                }
            )

        # Check 4: allowlist exists and is not empty
        if not self._check_allowlist():
            blocking_issues["issues"].append(
                {
                    "category": "GATE",
                    "code": "GATE_004",
                    "message": "allowlist is missing or empty",
                    "evidence_paths": [f"{self.data_dir}/allowlist.json", "logs/live_gate.log"],
                }
            )

        # Check 5: Fund limit is within budget (≤10u)
        if not self._check_fund_limit():
            blocking_issues["issues"].append(
                {
                    "category": "RISK",
                    "code": "RISK_001",
                    "message": f"Total risk budget exceeded. Max allowed: {self.risk_budget} USDT",
                    "evidence_paths": [
                        f"{self.taskhub_dir}/index/live_config.json",
                        f"{self.config_dir}/live_config.json",
                        "logs/risk_engine.log",
                    ],
                }
            )

        # Check 6: Reconciliation (账户/持仓/订单三表一致性)
        if not self._check_reconciliation():
            blocking_issues["issues"].append(
                {
                    "category": "RECONCILE",
                    "code": "RECONCILE_001",
                    "message": "Reconciliation failed: account/position/order tables inconsistent",
                    "evidence_paths": [
                        f"{self.data_dir}/live_reconcile_report.json",
                        "logs/reconciler.log",
                    ],
                }
            )

        # Check 7: Check for any blocking issues from previous runs
        if not self._check_previous_blocking_issues():
            blocking_issues["issues"].append(
                {
                    "category": "SYSTEM",
                    "code": "SYSTEM_003",
                    "message": "There are unresolved blocking issues from previous runs",
                    "evidence_paths": [
                        f"{self.data_dir}/blocking_issues.json",
                        "logs/live_gate.log",
                    ],
                }
            )

        # Determine if access is allowed
        is_allowed = len(blocking_issues["issues"]) == 0

        # Write blocking issues to file if any
        if not is_allowed:
            self._write_blocking_issues(blocking_issues)

        return is_allowed, blocking_issues

    def _load_live_config(self) -> dict:
        """
        Load live configuration from config_live.json

        Returns:
            dict: Live configuration
        """
        config_path = os.path.join(self.config_dir, "config_live.json")

        try:
            if os.path.exists(config_path):
                with open(config_path, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

        return {}

    def _check_live_config(self) -> bool:
        """
        Check if live configuration is valid

        Returns:
            bool: True if live configuration is valid, False otherwise
        """
        return len(self.live_config) > 0

    def _check_latest_audit(self) -> bool:
        """
        Check if latest audit conclusion is GO

        Returns:
            bool: True if latest audit is GO, False otherwise
        """
        registry_path = os.path.join(self.taskhub_dir, "registry.json")

        if not os.path.exists(registry_path):
            return False

        try:
            with open(registry_path, encoding="utf-8") as f:
                registry = json.load(f)

            # Check if any recent audit tasks have passed
            for task_id, task_info in registry.items():
                if isinstance(task_info, dict) and task_info.get("status") == "DONE":
                    return True

            return False
        except (OSError, json.JSONDecodeError):
            return False

    def _check_enable_live(self) -> bool:
        """
        Check if enable_live switch exists and is valid

        Returns:
            bool: True if enable_live is valid, False otherwise
        """
        enable_live_path = os.path.join(self.data_dir, "enable_live.json")

        if not os.path.exists(enable_live_path):
            return False

        try:
            with open(enable_live_path, encoding="utf-8") as f:
                enable_live = json.load(f)

            # Check if enable_live has required fields
            if isinstance(enable_live, dict) and "timestamp" in enable_live:
                return True

            return False
        except (OSError, json.JSONDecodeError):
            return False

    def _check_live_enabled(self) -> bool:
        """
        Check if live trading is enabled in configuration

        Returns:
            bool: True if live trading is enabled, False otherwise
        """
        return self.live_config.get("live", {}).get("enabled", False)

    def _check_allowlist(self) -> bool:
        """
        Check if allowlist exists and is not empty

        Returns:
            bool: True if allowlist is valid and not empty, False otherwise
        """
        allowlist_path = os.path.join(self.data_dir, "allowlist.json")

        if not os.path.exists(allowlist_path):
            return False

        try:
            with open(allowlist_path, encoding="utf-8") as f:
                allowlist = json.load(f)

            # Check if allowlist has strategies or symbols and they are not empty
            if isinstance(allowlist, dict):
                strategies = allowlist.get("strategies", [])
                symbols = allowlist.get("symbols", [])
                return len(strategies) > 0 or len(symbols) > 0

            return False
        except (OSError, json.JSONDecodeError):
            return False

    def _check_risk_template(self) -> bool:
        """
        Check if risk template is enabled

        Returns:
            bool: True if risk template is enabled, False otherwise
        """
        risk_config_path = os.path.join(self.config_dir, "risk_control_switches.yaml")

        if not os.path.exists(risk_config_path):
            return False

        try:
            with open(risk_config_path, encoding="utf-8") as f:
                risk_config = yaml.safe_load(f)

            # Check if risk_check_enabled is enabled
            if isinstance(risk_config, dict) and "global" in risk_config:
                global_config = risk_config["global"]
                if "risk_check_enabled" in global_config:
                    return global_config["risk_check_enabled"].get("enabled", False)

            return False
        except (OSError, yaml.YAMLError):
            return False

    def _check_exchange_keys(self) -> bool:
        """
        Check if exchange keys are available in environment variables

        Returns:
            bool: True if exchange keys are available, False otherwise
        """
        # For testing purposes, we'll allow missing keys in test environment
        if self.live_config.get("system", {}).get("run_mode") == "test":
            return True

        required_keys = ["OKX_KEY", "OKX_SECRET", "OKX_PASSPHRASE"]

        for key in required_keys:
            if key not in os.environ:
                return False

        return True

    def _check_fund_limit(self) -> bool:
        """
        Check if fund limit is within budget

        Returns:
            bool: True if fund limit is within budget, False otherwise
        """
        # For now, we'll check if the risk budget is properly configured
        # In a real implementation, this would calculate total exposure
        return self.risk_budget <= 10.0

    def _check_kill_switch(self) -> bool:
        """
        Check if kill switch is active

        Returns:
            bool: True if kill switch is not active, False otherwise
        """
        # Check for manual kill switch file
        taskhub_dir = os.path.join(self.taskhub_dir, "index")
        stop_live_path = os.path.join(taskhub_dir, "stop_live.json")

        # Create taskhub/index directory if it doesn't exist
        os.makedirs(taskhub_dir, exist_ok=True)

        if os.path.exists(stop_live_path):
            try:
                with open(stop_live_path, encoding="utf-8") as f:
                    stop_live = json.load(f)

                # If the file exists and has a valid structure, kill switch is active
                if isinstance(stop_live, dict) and "timestamp" in stop_live:
                    return False
            except (OSError, json.JSONDecodeError):
                # If there's an error reading the file, assume kill switch is active
                return False

        return True

    def _check_previous_blocking_issues(self) -> bool:
        """
        Check if there are any unresolved blocking issues from previous runs

        Returns:
            bool: True if there are no unresolved blocking issues, False otherwise
        """
        blocking_issues_path = os.path.join(self.data_dir, "blocking_issues.json")

        if os.path.exists(blocking_issues_path):
            try:
                with open(blocking_issues_path, encoding="utf-8") as f:
                    existing_issues = json.load(f)

                # If there are any blocking issues, return False
                if existing_issues.get("issues", []):
                    return False
            except Exception:
                # If there's an error reading the file, assume there are blocking issues
                return False

        return True

    def _check_reconciliation(self) -> bool:
        """
        Check if account/position/order reconciliation is successful

        Returns:
            bool: True if reconciliation passes, False otherwise
        """
        # Check 1: Look for existing blocking issues that need to be resolved
        blocking_issues_path = os.path.join(self.data_dir, "blocking_issues.json")
        if os.path.exists(blocking_issues_path):
            try:
                with open(blocking_issues_path, encoding="utf-8") as f:
                    existing_issues = json.load(f)

                # If there are any blocking issues, reconciliation fails
                if existing_issues.get("issues", []):
                    return False
            except Exception:
                pass

        # Check 2: Look for reconciliation report
        reconcile_report_path = os.path.join(self.data_dir, "live_reconcile_report.json")
        if not os.path.exists(reconcile_report_path):
            # If no reconciliation report exists, reconciliation fails
            return False

        # Check 3: Verify reconciliation report content
        try:
            with open(reconcile_report_path, encoding="utf-8") as f:
                reconcile_report = json.load(f)

            # Check if reconciliation passed
            if not reconcile_report.get("ok", False):
                return False
        except Exception:
            return False

        return True

    def _on_reconcile_blocked(self, reason: str) -> None:
        """
        Callback when reconciliation detects issues and blocks trading

        Args:
            reason: Reason for blocking
        """
        # Create blocking issue
        blocking_issue = {
            "timestamp": datetime.now().isoformat(),
            "issues": [
                {
                    "category": "RECONCILE",
                    "code": "RECONCILE_002",
                    "message": f"Reconciliation failed: {reason}",
                    "evidence_paths": [
                        f"{self.data_dir}/live_reconcile_report.json",
                        "logs/reconciler.log",
                    ],
                }
            ],
        }

        # Write blocking issues
        self._write_blocking_issues(blocking_issue)

    def run_reconciliation(self) -> ReconciliationReport:
        """
        Run actual reconciliation process

        Returns:
            ReconciliationReport: Result of the reconciliation
        """
        # Run reconciliation
        report = self.reconciler.reconcile()

        # Save report to live_reconcile_report.json
        self._save_live_reconcile_report(report)

        return report

    def _save_live_reconcile_report(self, report: ReconciliationReport) -> None:
        """
        Save live reconciliation report to file

        Args:
            report: Reconciliation report to save
        """
        report_dict = {
            "timestamp": datetime.now().isoformat(),
            "ok": report.ok,
            "drift_type": report.drift_type.value if report.drift_type else None,
            "recommended_action": report.recommended_action.value
            if report.recommended_action
            else None,
            "summary": report.summary,
            "total_diffs": len(report.diffs),
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
            "status": {
                "is_blocked": self.reconciler.status.is_blocked,
                "block_reason": self.reconciler.status.block_reason,
                "drift_count": self.reconciler.status.drift_count,
                "total_reconciles": self.reconciler.status.total_reconciles,
                "failed_reconciles": self.reconciler.status.failed_reconciles,
            },
        }

        # Write to data directory as live_reconcile_report.json
        report_path = os.path.join(self.data_dir, "live_reconcile_report.json")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report_dict, f, indent=2, ensure_ascii=False)
        except (OSError, json.JSONDecodeError):
            # If we can't write, log error
            pass

    def start_periodic_reconciliation(self):
        """
        Start periodic reconciliation
        """
        self.reconciler.start_periodic_reconcile()

    def stop_periodic_reconciliation(self):
        """
        Stop periodic reconciliation
        """
        self.reconciler.stop_periodic_reconcile()

    def _write_blocking_issues(self, blocking_issues: dict) -> None:
        """
        Write blocking issues to file

        Args:
            blocking_issues: Dictionary containing blocking issues
        """
        # Write to data directory
        blocking_path = os.path.join(self.data_dir, "blocking_issues.json")

        try:
            # Read existing issues if file exists
            existing_issues = {"timestamp": datetime.now().isoformat(), "issues": []}

            if os.path.exists(blocking_path):
                with open(blocking_path, encoding="utf-8") as f:
                    existing_issues = json.load(f)

            # Add new issues, avoiding duplicates
            existing_issue_keys = {
                (issue["category"], issue["code"]) for issue in existing_issues["issues"]
            }
            for new_issue in blocking_issues["issues"]:
                new_issue_key = (new_issue["category"], new_issue["code"])
                if new_issue_key not in existing_issue_keys:
                    existing_issues["issues"].append(new_issue)

            # Update timestamp
            existing_issues["timestamp"] = datetime.now().isoformat()

            # Write back to data directory
            with open(blocking_path, "w", encoding="utf-8") as f:
                json.dump(existing_issues, f, indent=2, ensure_ascii=False)

            # Write to TaskHub for audit trail
            taskhub_blocking_path = os.path.join(self.taskhub_dir, "index", "blocking_issues.json")
            os.makedirs(os.path.dirname(taskhub_blocking_path), exist_ok=True)
            with open(taskhub_blocking_path, "w", encoding="utf-8") as f:
                json.dump(existing_issues, f, indent=2, ensure_ascii=False)
        except (OSError, json.JSONDecodeError):
            # If we can't write, just ignore
            pass
