#!/usr/bin/env python3
"""
Configuration Snapshot Management

This module provides functionality to create configuration snapshots, detect drift,
and generate drift reports.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ConfigDrift:
    """
    Configuration drift information.
    """

    drift_type: str  # file_change, env_change, hash_mismatch
    config_path: str
    old_value: Any
    new_value: Any
    timestamp: int
    reason: str


@dataclass
class ConfigSnapshot:
    """
    Configuration snapshot containing hash and key parameters.
    """

    snapshot_id: str
    timestamp: int
    config_hash: str
    config_files: dict[str, str]  # {file_path: hash}
    key_parameters: dict[str, Any]  # 关键参数
    env_vars: dict[str, str]  # 环境变量
    metadata: dict[str, Any]


@dataclass
class ConfigDriftReport:
    """
    Configuration drift report.
    """

    report_id: str
    timestamp: int
    snapshot_id: str
    original_hash: str
    current_hash: str
    drifts: list[ConfigDrift]
    overall_status: str  # PASS/FAIL
    recommendations: list[str]


class ConfigSnapshotManager:
    """
    Manager for configuration snapshots and drift detection.
    """

    def __init__(self, config_dir: Path | None = None, key_params: list[str] | None = None):
        """
        Initialize the configuration snapshot manager.

        Args:
            config_dir: Configuration directory path (default: configs/)
            key_params: List of key parameters to include in the snapshot
        """
        self.config_dir = config_dir or Path("configs")
        self.key_params = key_params or [
            "system.run_mode",
            "system.debug",
            "system.log_level",
            "database",
            "database.host",
            "database.port",
            "database.name",
            "data_collection.exchanges",
            "data_collection.frequency",
            "factor.calculate_factors",
            "factor.update_interval",
            "strategy.strategy_id",
            "strategy.risk_limit",
            "trading.enabled",
            "trading.max_position_size",
            "risk_management.enabled",
            "risk_management.max_drawdown",
            "api.base_url",
            "api.timeout",
            "api.retry_count",
            "scheduler.enabled",
            "scheduler.interval",
            "notifications.enabled"
        ]
        self.snapshot_dir = Path("data/state/config_snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        # 环境变量白名单，只跟踪相关的环境变量
        self.env_whitelist = ["QUANTSYS_", "FREQTRADE_", "OKX_", "BINANCE_"]

    def generate_snapshot_id(self) -> str:
        """Generate a unique snapshot ID."""
        timestamp = int(time.time() * 1000)
        return f"config_snapshot_{timestamp}"

    def calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate the SHA256 hash of a file.

        Args:
            file_path: Path to the file

        Returns:
            str: SHA256 hash of the file
        """
        if not file_path.exists():
            return ""

        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # 分块读取文件以处理大文件
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest()

    def calculate_config_hash(self, config_files: dict[str, str]) -> str:
        """
        Calculate the overall configuration hash from individual file hashes.

        Args:
            config_files: Dict of file paths to their hashes

        Returns:
            str: Overall configuration hash
        """
        # 排序文件路径以确保一致性
        sorted_files = sorted(config_files.items(), key=lambda x: x[0])

        # 合并所有文件哈希
        combined_hash = "".join([f"{path}:{hsh}" for path, hsh in sorted_files])

        # 计算整体哈希
        return hashlib.sha256(combined_hash.encode()).hexdigest()

    def get_config_files(self) -> list[Path]:
        """Get all configuration files in the config directory."""
        config_files = []
        
        # Include JSON, YAML, and ENV files
        for pattern in ["*.json", "*.yaml", "*.yml", "*.env"]:
            config_files.extend(list(self.config_dir.glob(pattern)))
        
        return config_files

    def extract_key_parameters(self, config_data: dict[str, Any]) -> dict[str, Any]:
        """
        Extract key parameters from configuration data.

        Args:
            config_data: Configuration data

        Returns:
            Dict[str, Any]: Key parameters
        """
        key_params = {}

        for param_path in self.key_params:
            parts = param_path.split(".")
            value = config_data
            found = True

            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    found = False
                    break

            if found:
                key_params[param_path] = copy.deepcopy(value)

        return key_params

    def get_relevant_env_vars(self) -> dict[str, str]:
        """
        Get relevant environment variables based on whitelist.

        Returns:
            Dict[str, str]: Relevant environment variables
        """
        env_vars = {}
        for key, value in os.environ.items():
            for prefix in self.env_whitelist:
                if key.startswith(prefix):
                    env_vars[key] = value
                    break
        return env_vars

    def create_snapshot(self) -> ConfigSnapshot:
        """
        Create a configuration snapshot.

        Returns:
            ConfigSnapshot: Created snapshot
        """
        snapshot_id = self.generate_snapshot_id()
        timestamp = int(time.time() * 1000)

        # 获取所有配置文件及其哈希
        config_files = {}
        all_config_data = {}
        file_metadata = {}

        for file_path in self.get_config_files():
            file_hash = self.calculate_file_hash(file_path)
            config_files[str(file_path)] = file_hash

            # 读取配置文件内容
            try:
                with open(file_path, encoding="utf-8") as f:
                    all_config_data[str(file_path)] = json.load(f)
                
                # Store file metadata
                stat = file_path.stat()
                file_metadata[str(file_path)] = {
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "created": stat.st_ctime
                }
            except Exception as e:
                logger.warning(f"Failed to read {file_path}: {e}")

        # 计算整体配置哈希
        config_hash = self.calculate_config_hash(config_files)

        # 提取关键参数（从所有配置文件， not just main config）
        key_parameters = {}
        for file_path_str, config_data in all_config_data.items():
            extracted = self.extract_key_parameters(config_data)
            if extracted:
                # Use relative path as a prefix to avoid conflicts
                file_path = Path(file_path_str)
                file_prefix = file_path.stem  # Use filename without extension as prefix
                for key, value in extracted.items():
                    prefixed_key = f"{file_prefix}.{key}" if file_prefix != "config" else key
                    key_parameters[prefixed_key] = value

        # 获取相关环境变量
        env_vars = self.get_relevant_env_vars()

        # 创建快照
        snapshot = ConfigSnapshot(
            snapshot_id=snapshot_id,
            timestamp=timestamp,
            config_hash=config_hash,
            config_files=config_files,
            key_parameters=key_parameters,
            env_vars=env_vars,
            metadata={
                "config_files_count": len(config_files),
                "key_params_count": len(key_parameters),
                "env_vars_count": len(env_vars),
                "file_metadata": file_metadata,
                "config_file_types": list(set(file.suffix for file in self.get_config_files())),
                "snapshot_timestamp": datetime.fromtimestamp(timestamp/1000).isoformat()
            },
        )

        return snapshot

    def save_snapshot(self, snapshot: ConfigSnapshot) -> Path:
        """
        Save a configuration snapshot to disk.

        Args:
            snapshot: Snapshot to save

        Returns:
            Path: Path to the saved snapshot file
        """
        # Convert to serializable dict
        snapshot_dict = asdict(snapshot)

        # Save to file
        file_path = self.snapshot_dir / f"{snapshot.snapshot_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_dict, f, indent=2, ensure_ascii=False)

        # Update latest snapshot link
        latest_path = self.snapshot_dir / "latest_snapshot.json"
        if latest_path.exists():
            latest_path.unlink()
        latest_path.write_text(
            json.dumps(snapshot_dict, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        logger.info(f"Saved configuration snapshot to {file_path}")
        return file_path

    def load_snapshot(self, snapshot_id_or_path: str) -> ConfigSnapshot | None:
        """
        Load a configuration snapshot from disk.

        Args:
            snapshot_id_or_path: Snapshot ID or path to snapshot file

        Returns:
            Optional[ConfigSnapshot]: Loaded snapshot, or None if not found
        """
        # Determine file path
        if snapshot_id_or_path.startswith("config_snapshot_"):
            file_path = self.snapshot_dir / f"{snapshot_id_or_path}.json"
        else:
            file_path = Path(snapshot_id_or_path)

        # Check if file exists
        if not file_path.exists():
            return None

        # Load from file
        with open(file_path, encoding="utf-8") as f:
            snapshot_dict = json.load(f)

        # Create and return snapshot
        return ConfigSnapshot(**snapshot_dict)

    def get_latest_snapshot(self) -> ConfigSnapshot | None:
        """
        Get the latest configuration snapshot.

        Returns:
            Optional[ConfigSnapshot]: Latest snapshot, or None if no snapshots exist
        """
        latest_path = self.snapshot_dir / "latest_snapshot.json"
        if not latest_path.exists():
            return None

        return self.load_snapshot(str(latest_path))

    def detect_drift(self, snapshot: ConfigSnapshot) -> ConfigDriftReport:
        """
        Detect configuration drift compared to a snapshot.

        Args:
            snapshot: Original configuration snapshot

        Returns:
            ConfigDriftReport: Drift report
        """
        report_id = f"drift_report_{int(time.time() * 1000)}"
        timestamp = int(time.time() * 1000)
        drifts = []
        recommendations = []

        # 1. 检查配置文件变更
        current_config_files = {}
        for file_path in self.get_config_files():
            current_config_files[str(file_path)] = self.calculate_file_hash(file_path)

        # 检查文件是否被添加
        for file_path, current_hash in current_config_files.items():
            if file_path not in snapshot.config_files:
                drift = ConfigDrift(
                    drift_type="file_change",
                    config_path=file_path,
                    old_value=None,
                    new_value=current_hash,
                    timestamp=timestamp,
                    reason="New configuration file added",
                )
                drifts.append(drift)
                recommendations.append(f"Review new file: {file_path}")

        # 检查文件是否被修改或删除
        for file_path, original_hash in snapshot.config_files.items():
            if file_path not in current_config_files:
                # 文件被删除
                drift = ConfigDrift(
                    drift_type="file_change",
                    config_path=file_path,
                    old_value=original_hash,
                    new_value=None,
                    timestamp=timestamp,
                    reason="Configuration file deleted",
                )
                drifts.append(drift)
                recommendations.append(f"Investigate deleted file: {file_path}")
            elif current_config_files[file_path] != original_hash:
                # 文件被修改
                # 获取文件内容变化
                old_content = ""
                new_content = ""

                # 尝试读取原始文件内容（如果文件存在）
                if Path(file_path).exists():
                    try:
                        with open(file_path, encoding="utf-8") as f:
                            new_content = f.read()
                    except Exception:
                        pass

                drift = ConfigDrift(
                    drift_type="file_change",
                    config_path=file_path,
                    old_value=original_hash,
                    new_value=current_config_files[file_path],
                    timestamp=timestamp,
                    reason="Configuration file modified",
                )
                drifts.append(drift)
                recommendations.append(f"Review changes to: {file_path}")

        # 2. 检查关键参数变更
        # Prefer manager's configured directory; fall back to repo default.
        main_config = (Path(self.config_dir) / "config.json") if self.config_dir else Path("configs/config.json")
        if main_config.exists():
            with open(main_config, encoding="utf-8") as f:
                current_config = json.load(f)

            current_key_params = self.extract_key_parameters(current_config)

            for param_path, original_value in snapshot.key_parameters.items():
                if param_path in current_key_params:
                    current_value = current_key_params[param_path]
                    if current_value != original_value:
                        drift = ConfigDrift(
                            drift_type="param_change",
                            config_path=param_path,
                            old_value=original_value,
                            new_value=current_value,
                            timestamp=timestamp,
                            reason="Key parameter changed",
                        )
                        drifts.append(drift)
                        recommendations.append(f"Review changed parameter: {param_path}")

        # 3. 检查环境变量变更
        current_env_vars = self.get_relevant_env_vars()

        # 检查环境变量是否被添加
        for key, current_value in current_env_vars.items():
            if key not in snapshot.env_vars:
                drift = ConfigDrift(
                    drift_type="env_change",
                    config_path=key,
                    old_value=None,
                    new_value=current_value,
                    timestamp=timestamp,
                    reason="New environment variable added",
                )
                drifts.append(drift)
                recommendations.append(f"Review new env var: {key}")

        # 检查环境变量是否被修改或删除
        for key, original_value in snapshot.env_vars.items():
            if key not in current_env_vars:
                # 环境变量被删除
                drift = ConfigDrift(
                    drift_type="env_change",
                    config_path=key,
                    old_value=original_value,
                    new_value=None,
                    timestamp=timestamp,
                    reason="Environment variable deleted",
                )
                drifts.append(drift)
                recommendations.append(f"Investigate deleted env var: {key}")
            elif current_env_vars[key] != original_value:
                # 环境变量被修改
                drift = ConfigDrift(
                    drift_type="env_change",
                    config_path=key,
                    old_value=original_value,
                    new_value=current_env_vars[key],
                    timestamp=timestamp,
                    reason="Environment variable modified",
                )
                drifts.append(drift)
                recommendations.append(f"Review changed env var: {key}")

        # 计算当前配置哈希
        current_config_hash = self.calculate_config_hash(current_config_files)

        # 确定总体状态
        overall_status = "PASS" if not drifts else "FAIL"

        # 创建报告
        report = ConfigDriftReport(
            report_id=report_id,
            timestamp=timestamp,
            snapshot_id=snapshot.snapshot_id,
            original_hash=snapshot.config_hash,
            current_hash=current_config_hash,
            drifts=drifts,
            overall_status=overall_status,
            recommendations=recommendations,
        )

        return report

    def save_drift_report(self, report: ConfigDriftReport) -> Path:
        """
        Save a drift report to disk.

        Args:
            report: Drift report to save

        Returns:
            Path: Path to the saved report file
        """
        # 确保报告目录存在
        reports_dir = Path("reports/config_drift")
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Convert to serializable dict
        report_dict = asdict(report)

        # Save to file
        file_path = reports_dir / f"{report.report_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)

        # Update latest report link
        latest_path = reports_dir / "latest_drift_report.json"
        if latest_path.exists():
            latest_path.unlink()
        latest_path.write_text(
            json.dumps(report_dict, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Save to unified status file
        status_path = Path("reports/config_drift_status.json")
        with open(status_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved drift report to {file_path}")
        return file_path

    def compare_snapshots(self, snapshot1: ConfigSnapshot, snapshot2: ConfigSnapshot) -> dict[str, Any]:
        """
        Compare two configuration snapshots and generate a detailed change summary.

        Args:
            snapshot1: First snapshot to compare
            snapshot2: Second snapshot to compare

        Returns:
            Dict[str, Any]: Detailed change summary
        """
        changes = {
            "config_files_added": [],
            "config_files_removed": [],
            "config_files_modified": [],
            "key_parameters_changed": {},
            "env_vars_changed": {},
            "config_hash_changed": snapshot1.config_hash != snapshot2.config_hash,
            "timestamp_diff": abs(snapshot2.timestamp - snapshot1.timestamp),
            "summary": {
                "total_files": len(snapshot2.config_files),
                "files_changed": 0,
                "key_params_changed": 0,
                "env_vars_changed": 0
            }
        }

        # Compare config files
        all_files = set(snapshot1.config_files.keys()) | set(snapshot2.config_files.keys())
        
        for file_path in all_files:
            if file_path not in snapshot1.config_files:
                changes["config_files_added"].append(file_path)
            elif file_path not in snapshot2.config_files:
                changes["config_files_removed"].append(file_path)
            elif snapshot1.config_files[file_path] != snapshot2.config_files[file_path]:
                changes["config_files_modified"].append({
                    "file_path": file_path,
                    "old_hash": snapshot1.config_files[file_path],
                    "new_hash": snapshot2.config_files[file_path]
                })

        # Compare key parameters
        all_params = set(snapshot1.key_parameters.keys()) | set(snapshot2.key_parameters.keys())
        
        for param in all_params:
            if param not in snapshot1.key_parameters:
                changes["key_parameters_changed"][param] = {
                    "action": "added",
                    "value": snapshot2.key_parameters.get(param)
                }
            elif param not in snapshot2.key_parameters:
                changes["key_parameters_changed"][param] = {
                    "action": "removed",
                    "value": snapshot1.key_parameters.get(param)
                }
            elif snapshot1.key_parameters[param] != snapshot2.key_parameters[param]:
                changes["key_parameters_changed"][param] = {
                    "action": "modified",
                    "old_value": snapshot1.key_parameters[param],
                    "new_value": snapshot2.key_parameters[param]
                }

        # Compare environment variables
        all_env_vars = set(snapshot1.env_vars.keys()) | set(snapshot2.env_vars.keys())
        
        for env_var in all_env_vars:
            if env_var not in snapshot1.env_vars:
                changes["env_vars_changed"][env_var] = {
                    "action": "added",
                    "value": snapshot2.env_vars.get(env_var)
                }
            elif env_var not in snapshot2.env_vars:
                changes["env_vars_changed"][env_var] = {
                    "action": "removed",
                    "value": snapshot1.env_vars.get(env_var)
                }
            elif snapshot1.env_vars[env_var] != snapshot2.env_vars[env_var]:
                changes["env_vars_changed"][env_var] = {
                    "action": "modified",
                    "old_value": snapshot1.env_vars[env_var],
                    "new_value": snapshot2.env_vars[env_var]
                }

        # Update summary
        changes["summary"]["files_changed"] = len(changes["config_files_added"]) + len(changes["config_files_removed"]) + len(changes["config_files_modified"])
        changes["summary"]["key_params_changed"] = len(changes["key_parameters_changed"])
        changes["summary"]["env_vars_changed"] = len(changes["env_vars_changed"])

        return changes

    def run_self_test(self) -> dict[str, Any]:
        """
        Run self-test to verify configuration snapshot functionality.

        Returns:
            Dict[str, Any]: Test results
        """
        results = {"tests": [], "overall_result": "PASS"}

        # Test 1: Create and save snapshot
        try:
            snapshot = self.create_snapshot()
            saved_path = self.save_snapshot(snapshot)

            results["tests"].append(
                {
                    "name": "Create and Save Snapshot",
                    "result": "PASS",
                    "details": f"Snapshot saved to {saved_path}",
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

        # Test 3: Detect drift (should pass initially)
        try:
            loaded_snapshot = self.get_latest_snapshot()
            if loaded_snapshot:
                drift_report = self.detect_drift(loaded_snapshot)
                results["tests"].append(
                    {
                        "name": "Detect Drift (Initial)",
                        "result": "PASS" if drift_report.overall_status == "PASS" else "FAIL",
                        "details": f"Initial drift detection: {drift_report.overall_status}, drifts: {len(drift_report.drifts)}",
                    }
                )
            else:
                results["tests"].append(
                    {
                        "name": "Detect Drift (Initial)",
                        "result": "FAIL",
                        "details": "Failed to load snapshot for drift detection",
                    }
                )
                results["overall_result"] = "FAIL"
        except Exception as e:
            results["tests"].append(
                {"name": "Detect Drift (Initial)", "result": "FAIL", "details": str(e)}
            )
            results["overall_result"] = "FAIL"

        # Test 4: Save drift report
        try:
            loaded_snapshot = self.get_latest_snapshot()
            if loaded_snapshot:
                drift_report = self.detect_drift(loaded_snapshot)
                saved_report = self.save_drift_report(drift_report)
                results["tests"].append(
                    {
                        "name": "Save Drift Report",
                        "result": "PASS",
                        "details": f"Drift report saved to {saved_report}",
                    }
                )
            else:
                results["tests"].append(
                    {
                        "name": "Save Drift Report",
                        "result": "FAIL",
                        "details": "Failed to load snapshot for drift report",
                    }
                )
                results["overall_result"] = "FAIL"
        except Exception as e:
            results["tests"].append(
                {"name": "Save Drift Report", "result": "FAIL", "details": str(e)}
            )
            results["overall_result"] = "FAIL"

        # Test 5: Verify snapshot integrity
        try:
            loaded_snapshot = self.get_latest_snapshot()
            if loaded_snapshot:
                # Verify snapshot contains expected fields
                expected_fields = [
                    "snapshot_id",
                    "timestamp",
                    "config_hash",
                    "config_files",
                    "key_parameters",
                ]
                for field in expected_fields:
                    if not hasattr(loaded_snapshot, field):
                        raise ValueError(f"Missing field: {field}")

                results["tests"].append(
                    {
                        "name": "Verify Snapshot Integrity",
                        "result": "PASS",
                        "details": "Snapshot contains all expected fields",
                    }
                )
            else:
                results["tests"].append(
                    {
                        "name": "Verify Snapshot Integrity",
                        "result": "FAIL",
                        "details": "Failed to load snapshot for integrity check",
                    }
                )
                results["overall_result"] = "FAIL"
        except Exception as e:
            results["tests"].append(
                {"name": "Verify Snapshot Integrity", "result": "FAIL", "details": str(e)}
            )
            results["overall_result"] = "FAIL"

        # Test 6: Test snapshot comparison
        try:
            # Create two snapshots
            snapshot1 = self.create_snapshot()
            
            # Wait a bit to ensure different timestamps
            import time
            time.sleep(0.01)
            
            snapshot2 = self.create_snapshot()
            
            # Compare snapshots (should be same since no changes)
            comparison = self.compare_snapshots(snapshot1, snapshot2)
            
            # Verify no changes detected between identical snapshots
            expected_changes = comparison["summary"]["files_changed"] == 0 and \
                              comparison["summary"]["key_params_changed"] == 0 and \
                              comparison["summary"]["env_vars_changed"] == 0
            
            results["tests"].append(
                {
                    "name": "Compare Snapshots (Identical)",
                    "result": "PASS" if expected_changes else "FAIL",
                    "details": f"Changes detected: {comparison['summary']}",
                }
            )
            
            if not expected_changes:
                results["overall_result"] = "FAIL"
        except Exception as e:
            results["tests"].append(
                {"name": "Compare Snapshots (Identical)", "result": "FAIL", "details": str(e)}
            )
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
        results_path = reports_dir / "config_snapshot_test_results.json"
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)

        # Also update last_run.md
        last_run_path = reports_dir / "last_run.md"
        test_summary = f"""
## Config Snapshot Self-Test Results

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


def main():
    """
    Main entry point for configuration snapshot functionality.
    Provides command-line interface for creating, loading, and managing configuration snapshots.
    """
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Configuration Snapshot Management Tool")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create snapshot command
    create_parser = subparsers.add_parser("create", help="Create a new configuration snapshot")
    create_parser.add_argument(
        "--config-dir", 
        default=None, 
        help="Configuration directory path (default: configs/)"
    )
    create_parser.add_argument(
        "--output", 
        default=None, 
        help="Output path for the snapshot"
    )

    # Load snapshot command
    load_parser = subparsers.add_parser("load", help="Load a configuration snapshot")
    load_parser.add_argument("snapshot_id", help="Snapshot ID or path to load")

    # Detect drift command
    drift_parser = subparsers.add_parser("drift", help="Detect configuration drift")
    drift_parser.add_argument(
        "--snapshot-id", 
        required=True, 
        help="Snapshot ID to compare against"
    )

    # Self-test command
    test_parser = subparsers.add_parser("test", help="Run self-test for config snapshot functionality")

    # List snapshots command
    list_parser = subparsers.add_parser("list", help="List all available snapshots")

    args = parser.parse_args()

    # Initialize the manager
    manager = ConfigSnapshotManager(config_dir=Path(args.config_dir) if args.config_dir else None)

    if args.command == "create":
        print("Creating configuration snapshot...")
        snapshot = manager.create_snapshot()
        saved_path = manager.save_snapshot(snapshot)
        print(f"Created snapshot: {snapshot.snapshot_id}")
        print(f"Saved to: {saved_path}")

    elif args.command == "load":
        print(f"Loading snapshot: {args.snapshot_id}")
        snapshot = manager.load_snapshot(args.snapshot_id)
        if snapshot:
            print(f"Snapshot ID: {snapshot.snapshot_id}")
            print(f"Timestamp: {snapshot.timestamp}")
            print(f"Config hash: {snapshot.config_hash}")
            print(f"Config files: {len(snapshot.config_files)}")
            print(f"Key parameters: {len(snapshot.key_parameters)}")
            print(f"Environment variables: {len(snapshot.env_vars)}")
        else:
            print(f"Error: Could not load snapshot: {args.snapshot_id}")
            sys.exit(1)

    elif args.command == "drift":
        print(f"Detecting drift against snapshot: {args.snapshot_id}")
        snapshot = manager.load_snapshot(args.snapshot_id)
        if not snapshot:
            print(f"Error: Could not load snapshot: {args.snapshot_id}")
            sys.exit(1)

        drift_report = manager.detect_drift(snapshot)
        saved_report_path = manager.save_drift_report(drift_report)
        
        print(f"Drift detection completed:")
        print(f"  Report ID: {drift_report.report_id}")
        print(f"  Original hash: {drift_report.original_hash}")
        print(f"  Current hash: {drift_report.current_hash}")
        print(f"  Status: {drift_report.overall_status}")
        print(f"  Drifts found: {len(drift_report.drifts)}")
        print(f"  Report saved to: {saved_report_path}")

        if drift_report.drifts:
            print("\nDrift details:")
            for drift in drift_report.drifts:
                print(f"  - {drift.drift_type}: {drift.config_path} - {drift.reason}")

    elif args.command == "test":
        print("Running self-test for configuration snapshot functionality...")
        results = manager.run_self_test()
        manager.save_test_results(results)
        
        print(f"Overall result: {results['overall_result']}")
        print("\nTest details:")
        for test in results['tests']:
            status = test['result']
            name = test['name']
            details = test['details']
            print(f"  {status}: {name} - {details}")

    elif args.command == "list":
        snapshot_dir = manager.snapshot_dir
        if snapshot_dir.exists():
            snapshots = list(snapshot_dir.glob("config_snapshot_*.json"))
            if snapshots:
                print("Available snapshots:")
                for snapshot_file in sorted(snapshots, key=lambda x: x.stat().st_mtime, reverse=True):
                    # Extract snapshot ID from filename
                    snapshot_id = snapshot_file.stem
                    print(f"  - {snapshot_id} (modified: {time.ctime(snapshot_file.stat().st_mtime)})")
            else:
                print("No snapshots found in directory.")
        else:
            print(f"Snapshot directory does not exist: {snapshot_dir}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
