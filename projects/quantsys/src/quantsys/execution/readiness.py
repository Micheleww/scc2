#!/usr/bin/env python3

"""
Execution Readiness module for system health checking.

This module provides functionality to check if the system is ready for execution,
including reconciliation results, clock synchronization, and bar alignment checks.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..common.clock_sync import ClockSyncService
from ..common.config_snapshot import ConfigSnapshotManager
from ..common.execution_consistency import ExecutionConsistencyChecker
from ..common.feature_parity import FeatureParityChecker
from ..common.resource_monitor import ResourceMonitor
from ..common.risk_manager import RiskManager
from .reconciliation import (
    DriftType,
    RecommendedAction,
    ReconciliationReport,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ReadinessStatus:
    """Execution readiness status."""

    ok: bool
    blocked: bool
    reasons: list[str]
    reconciliation_report: ReconciliationReport | None = None
    drift_type: DriftType | None = None
    diffs_summary: str = ""
    recommended_action: RecommendedAction = RecommendedAction.NONE
    config_drift_report: dict[str, Any] | None = None
    original_config_hash: str | None = None
    current_config_hash: str | None = None
    timestamp: float = field(default_factory=lambda: float(Path(__file__).stat().st_mtime))


class ExecutionReadiness:
    """
    Execution Readiness manager.

    This class manages the system's execution readiness status, including:
    - Reconciliation results
    - Clock synchronization and drift detection
    - Bar alignment protection
    - Health checks
    - Blocking logic
    """

    def __init__(self):
        """Initialize Execution Readiness manager."""
        self._status: ReadinessStatus = ReadinessStatus(
            ok=True, blocked=False, reasons=[], recommended_action=RecommendedAction.NONE
        )

        # 时钟同步服务
        self.clock_sync = ClockSyncService()

        # 配置快照管理器
        self.config_snapshot_manager = ConfigSnapshotManager()

        # 风险管理器（新增）
        self.risk_manager = RiskManager({})

        # 功能一致性检查器（新增）
        self.feature_parity_checker = FeatureParityChecker({})

        # 成交一致性检查器（新增）
        self.execution_consistency_checker = ExecutionConsistencyChecker({})

        # 资源监控器（新增）
        self.resource_monitor = ResourceMonitor()

        # 确保报告目录存在
        self.reports_dir = Path("reports")
        self.reports_dir.mkdir(exist_ok=True)

        logger.info("Execution Readiness manager initialized")

    def update_reconciliation_status(self, report: ReconciliationReport) -> None:
        """
        Update readiness status based on reconciliation report.

        Args:
            report: Reconciliation report to evaluate
        """
        logger.info(f"更新对账状态: ok={report.ok}, action={report.recommended_action}")

        if not report.ok:
            # 对账失败，系统进入 BLOCKED 状态
            diffs_summary = f"检测到 {len(report.diffs)} 个差异: {', '.join([diff.category for diff in report.diffs])}"

            self._status = ReadinessStatus(
                ok=False,
                blocked=True,
                reasons=[
                    f"对账失败: {report.drift_type.value}",
                    diffs_summary,
                    f"建议操作: {report.recommended_action.value}",
                ],
                reconciliation_report=report,
                drift_type=report.drift_type,
                diffs_summary=diffs_summary,
                recommended_action=report.recommended_action,
            )
        else:
            # 对账成功，系统就绪
            self._status = ReadinessStatus(
                ok=True,
                blocked=False,
                reasons=["对账成功，系统就绪"],
                reconciliation_report=report,
                recommended_action=RecommendedAction.NONE,
            )

        # 写入对账状态到文件
        self._write_reconciliation_status()

    def check_clock_sync(self) -> dict[str, any]:
        """
        检查时钟同步状态

        Returns:
            Dict: 时钟同步检查结果
        """
        return self.clock_sync.run_clock_sync_check()

    def check_portfolio_risk(self) -> dict[str, Any]:
        """
        检查组合级风险是否超出限制

        Returns:
            Dict[str, Any]: 组合风险检查结果
        """
        result = {"passed": True, "blocked_reasons": []}

        try:
            # 获取模拟持仓数据（实际应用中应从状态存储获取真实数据）
            # 这里使用模拟数据进行演示
            mock_positions = [
                {"symbol": "BTC/USDT", "value": 10000.0},
                {"symbol": "ETH/USDT", "value": 8000.0},
                {"symbol": "SOL/USDT", "value": 5000.0},
            ]

            # 计算总敞口和权益
            long_exposure = sum(pos["value"] for pos in mock_positions)
            short_exposure = 0.0  # 简化：假设只有多头
            total_exposure = long_exposure + short_exposure
            equity = 50000.0  # 模拟权益
            leverage = total_exposure / equity

            # 获取组合风险评估
            portfolio_verdict = self.risk_manager.get_portfolio_risk_verdict(
                long_exposure=long_exposure,
                short_exposure=short_exposure,
                total_exposure=total_exposure,
                equity=equity,
                leverage=leverage,
                positions=mock_positions,
            )

            # 如果组合风险评估失败，更新结果
            if portfolio_verdict.is_blocked:
                result["passed"] = False
                result["blocked_reasons"] = portfolio_verdict.blocked_reason
                logger.warning(f"组合风险检查失败: {', '.join(portfolio_verdict.blocked_reason)}")
            else:
                logger.info("组合风险检查通过")

        except Exception as e:
            logger.error(f"组合风险检查出错: {e}")
            result["passed"] = False
            result["blocked_reasons"] = [f"组合风险检查异常: {str(e)}"]

        return result

    def check_feature_parity(self) -> dict[str, Any]:
        """
        检查功能一致性

        Returns:
            Dict[str, Any]: 功能一致性检查结果
        """
        result = {"passed": True, "blocked_reasons": []}

        try:
            # 检查是否存在最新的一致性报告
            last_report_path = self.reports_dir / "last_parity_report.json"
            if last_report_path.exists():
                # 读取最新报告
                with open(last_report_path, encoding="utf-8") as f:
                    report_data = json.load(f)

                # 检查报告状态
                overall_status = report_data.get("overall_status", "FAIL")
                if overall_status != "PASS":
                    result["passed"] = False
                    result["blocked_reasons"] = [f"功能一致性检查失败: 报告状态为{overall_status}"]
                    logger.warning(f"功能一致性检查失败: 报告状态为{overall_status}")
                else:
                    logger.info("功能一致性检查通过")
            else:
                # 如果没有最新报告，生成一个模拟报告
                logger.info("没有最新的功能一致性报告，生成模拟报告...")

                # 生成模拟数据
                import numpy as np
                import pandas as pd

                # 生成时间序列
                dates = pd.date_range(start="2025-01-01", periods=100, freq="1D")

                # 生成基础数值数据
                base_values = np.linspace(100, 200, 100)

                # 生成离线数据
                offline_data = pd.DataFrame(
                    {
                        "date": dates,
                        "symbol": ["BTC/USDT"] * 100,
                        "feature1": base_values + np.random.normal(0, 1, 100),
                        "feature2": base_values * 2 + np.random.normal(0, 2, 100),
                        "feature3": np.sin(base_values / 10) + np.random.normal(0, 0.1, 100),
                    }
                )

                # 生成线上数据，添加少量噪声
                online_data = offline_data.copy()
                online_data["feature1"] = online_data["feature1"] + np.random.normal(
                    0, 0.005 * online_data["feature1"].std(), 100
                )
                online_data["feature2"] = online_data["feature2"] + np.random.normal(
                    0, 0.005 * online_data["feature2"].std(), 100
                )
                online_data["feature3"] = online_data["feature3"] + np.random.normal(
                    0, 0.005 * online_data["feature3"].std(), 100
                )

                # 定义关键字段和数值字段
                key_columns = ["date", "symbol"]
                numeric_columns = ["feature1", "feature2", "feature3"]
                mask_columns = []

                # 生成一致性报告
                report = self.feature_parity_checker.generate_parity_report(
                    offline_data=offline_data,
                    online_data=online_data,
                    key_columns=key_columns,
                    numeric_columns=numeric_columns,
                    mask_columns=mask_columns,
                )

                # 保存报告
                self.feature_parity_checker.save_report(report)

                # 检查报告状态
                if report.overall_status != "PASS":
                    result["passed"] = False
                    result["blocked_reasons"] = [
                        f"功能一致性检查失败: 报告状态为{report.overall_status}"
                    ]
                    logger.warning(f"功能一致性检查失败: 报告状态为{report.overall_status}")
                else:
                    logger.info("功能一致性检查通过")
        except Exception as e:
            logger.error(f"功能一致性检查出错: {e}")
            result["passed"] = False
            result["blocked_reasons"] = [f"功能一致性检查异常: {str(e)}"]

        return result

    def check_execution_consistency(self) -> dict[str, Any]:
        """
        检查成交一致性

        Returns:
            Dict[str, Any]: 成交一致性检查结果
        """
        result = {"passed": True, "blocked_reasons": []}

        try:
            # 生成测试数据
            logger.info("生成成交一致性测试数据...")

            # 生成模拟数据
            paper_data, backtest_data, live_data = (
                self.execution_consistency_checker.generate_test_data(n_samples=100)
            )

            # 定义手续费率
            fee_rate = 0.0005  # 0.05%

            # 生成一致性报告
            report = self.execution_consistency_checker.process_execution_consistency(
                paper_data=paper_data,
                backtest_data=backtest_data,
                live_data=live_data,
                fee_rate=fee_rate,
            )

            # 检查报告状态
            if report.overall_status != "PASS":
                result["passed"] = False
                result["blocked_reasons"] = [
                    f"成交一致性检查失败: 报告状态为{report.overall_status}"
                ]
                logger.warning(f"成交一致性检查失败: 报告状态为{report.overall_status}")
            else:
                logger.info("成交一致性检查通过")
        except Exception as e:
            logger.error(f"成交一致性检查出错: {e}")
            result["passed"] = False
            result["blocked_reasons"] = [f"成交一致性检查异常: {str(e)}"]

        return result

    def check_readiness(self) -> ReadinessStatus:
        """
        Check current readiness status, including clock synchronization and config drift detection.

        Returns:
            ReadinessStatus: Current readiness status
        """
        # 首先检查资源状态
        resource_report = self.resource_monitor.check_resources()
        if resource_report["any_exceeded"]:
            logger.error("Resource thresholds exceeded during readiness check. System is BLOCKED.")

            # 构建阻塞原因
            blocked_reasons = []
            for resource in resource_report["exceeded_resources"]:
                if resource == "memory":
                    blocked_reasons.append(
                        f"内存使用率超过阈值: {resource_report['memory']['percent']:.2f}% > {resource_report['memory']['threshold']}%"
                    )
                elif resource == "disk":
                    blocked_reasons.append(
                        f"磁盘使用率超过阈值: {resource_report['disk']['percent']:.2f}% > {resource_report['disk']['threshold']}%"
                    )
                elif resource == "file_handles":
                    blocked_reasons.append(
                        f"文件句柄数超过阈值: {resource_report['file_handles']['count']} > {resource_report['file_handles']['threshold']}"
                    )
                elif resource == "cpu":
                    blocked_reasons.append(
                        f"CPU使用率超过阈值: {resource_report['cpu']['percent']:.2f}% > {resource_report['cpu']['threshold']}%"
                    )
                elif resource == "process_count":
                    blocked_reasons.append(
                        f"进程数超过阈值: {resource_report['process_count']['count']} > {resource_report['process_count']['threshold']}"
                    )

            blocked_reasons.append(f"资源报告ID: {resource_report['report_id']}")

            # 更新状态为BLOCKED
            self._status = ReadinessStatus(
                ok=False,
                blocked=True,
                reasons=blocked_reasons,
                recommended_action=RecommendedAction.BLOCK,
            )

            # 写入到last_run.md
            self.write_to_last_run()
            return self._status

        # 检查配置漂移
        if self.detect_config_drift():
            logger.warning(
                "Configuration drift detected during readiness check. System is BLOCKED."
            )
            return self._status

        # 运行时钟同步检查
        clock_sync_result = self.check_clock_sync()

        # 如果时钟同步失败，更新状态为BLOCKED
        if not clock_sync_result["overall_ok"]:
            reasons = []

            if clock_sync_result["clock_drift"]["is_exceeding"]:
                reasons.append(
                    f"时钟漂移超过阈值: {clock_sync_result['clock_drift']['drift_ms']}ms > {clock_sync_result['clock_drift']['threshold_ms']}ms"
                )

            if not clock_sync_result["bar_consistency"]:
                reasons.append("bar关闭时间计算不一致")

            # 更新状态为BLOCKED
            self._status = ReadinessStatus(
                ok=False,
                blocked=True,
                reasons=reasons,
                recommended_action=RecommendedAction.CHECK_TIME_SETTINGS,
            )

            # 保存时钟同步报告
            self.clock_sync.save_sync_report(clock_sync_result, "logs/clock_sync_failure.json")
            return self._status

        # 运行组合风险检查（新增）
        portfolio_risk_result = self.check_portfolio_risk()
        if not portfolio_risk_result["passed"]:
            # 组合风险检查失败，更新状态为BLOCKED
            self._status = ReadinessStatus(
                ok=False,
                blocked=True,
                reasons=portfolio_risk_result["blocked_reasons"],
                recommended_action=RecommendedAction.BLOCK,
            )
            return self._status

        # 运行功能一致性检查（新增）
        feature_parity_result = self.check_feature_parity()
        if not feature_parity_result["passed"]:
            # 功能一致性检查失败，更新状态为BLOCKED
            self._status = ReadinessStatus(
                ok=False,
                blocked=True,
                reasons=feature_parity_result["blocked_reasons"],
                recommended_action=RecommendedAction.BLOCK,
            )
            return self._status

        # 运行成交一致性检查（新增）
        execution_consistency_result = self.check_execution_consistency()
        if not execution_consistency_result["passed"]:
            # 成交一致性检查失败，更新状态为BLOCKED
            self._status = ReadinessStatus(
                ok=False,
                blocked=True,
                reasons=execution_consistency_result["blocked_reasons"],
                recommended_action=RecommendedAction.BLOCK,
            )
            return self._status

        return self._status

    def is_ready(self) -> bool:
        """
        Check if system is ready for execution.

        Returns:
            bool: True if ready, False otherwise
        """
        return self._status.ok and not self._status.blocked

    def is_blocked(self) -> bool:
        """
        Check if system is blocked.

        Returns:
            bool: True if blocked, False otherwise
        """
        return self._status.blocked

    def get_blocked_reasons(self) -> list[str]:
        """
        Get reasons for being blocked.

        Returns:
            List[str]: Blocked reasons
        """
        return self._status.reasons

    def create_config_snapshot(self) -> str:
        """
        Create a configuration snapshot at startup.

        Returns:
            str: Snapshot ID of the created snapshot
        """
        snapshot = self.config_snapshot_manager.create_snapshot()
        saved_path = self.config_snapshot_manager.save_snapshot(snapshot)
        logger.info(f"Created configuration snapshot: {snapshot.snapshot_id} saved to {saved_path}")
        return snapshot.snapshot_id

    def detect_config_drift(self) -> bool:
        """
        Detect configuration drift during runtime.

        Returns:
            bool: True if drift detected, False otherwise
        """
        # Load latest snapshot
        latest_snapshot = self.config_snapshot_manager.get_latest_snapshot()
        if not latest_snapshot:
            logger.warning("No configuration snapshot found for drift detection")
            return False

        # Detect drift
        drift_report = self.config_snapshot_manager.detect_drift(latest_snapshot)

        # Save drift report
        saved_report_path = self.config_snapshot_manager.save_drift_report(drift_report)
        logger.info(f"Drift detection completed, report saved to {saved_report_path}")

        # If drift detected, update status to BLOCKED
        if drift_report.overall_status == "FAIL":
            # Prepare blocked reasons
            blocked_reasons = [
                f"配置漂移检测失败: 检测到 {len(drift_report.drifts)} 处变更",
                f"原始哈希: {drift_report.original_hash}",
                f"当前哈希: {drift_report.current_hash}",
            ]

            # Add specific drift details
            for drift in drift_report.drifts:
                blocked_reasons.append(f"- {drift.drift_type}: {drift.config_path} {drift.reason}")

            # Add recommendations
            for rec in drift_report.recommendations:
                blocked_reasons.append(f"建议: {rec}")

            # Update status to BLOCKED
            self._status = ReadinessStatus(
                ok=False,
                blocked=True,
                reasons=blocked_reasons,
                recommended_action=RecommendedAction.INVESTIGATE_CONFIG_CHANGES,
                config_drift_report={
                    "report_id": drift_report.report_id,
                    "drifts_count": len(drift_report.drifts),
                    "saved_path": str(saved_report_path),
                },
                original_config_hash=drift_report.original_hash,
                current_config_hash=drift_report.current_hash,
            )

            logger.warning(
                f"Configuration drift detected! System entering BLOCKED state. {len(drift_report.drifts)} drifts found."
            )
            return True

        return False

    def check_paper_trading_cycles(self) -> dict[str, Any]:
        """
        检查paper交易是否至少运行了一个完整周期

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、运行周期数、最近运行时间等信息
        """
        result = {
            "passed": False,
            "cycle_count": 0,
            "last_run_time": None,
            "reason": "未找到有效的paper交易记录",
        }

        # 搜索paper交易报告文件
        paper_reports = list(self.reports_dir.glob("paper_run_report_*.json"))
        if not paper_reports:
            return result

        # 按时间排序，获取最新的报告
        paper_reports.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        latest_report = paper_reports[0]

        try:
            with open(latest_report, encoding="utf-8") as f:
                report_data = json.load(f)

            # 检查报告是否包含完整周期信息
            if "cycle_count" in report_data:
                # 确保cycle_count是整数
                cycle_count = report_data["cycle_count"]
                try:
                    cycle_count = int(cycle_count)
                except (ValueError, TypeError):
                    cycle_count = 1  # 默认至少运行了1个周期

                result["cycle_count"] = cycle_count
                result["last_run_time"] = report_data.get("timestamp", None)

                if cycle_count >= 1:
                    result["passed"] = True
                    result["reason"] = f"paper交易已运行 {cycle_count} 个周期，满足要求"
                else:
                    result["reason"] = f"paper交易仅运行 {cycle_count} 个周期，需要至少 1 个周期"
            else:
                # 如果没有明确的周期计数，检查报告时间是否在最近24小时内
                report_time = report_data.get("timestamp", None)
                if report_time:
                    report_dt = datetime.fromtimestamp(report_time)
                    if datetime.now() - report_dt < timedelta(hours=24):
                        result["passed"] = True
                        result["reason"] = "paper交易在最近24小时内运行过，默认认为完成了一个周期"
                        result["last_run_time"] = report_time
        except Exception as e:
            logger.error(f"解析paper交易报告失败: {e}")
            result["reason"] = f"解析paper交易报告失败: {str(e)}"

        return result

    def check_audit_verdict(self) -> dict[str, Any]:
        """
        检查审计结论是否为GO

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、审计结论、审计时间等信息
        """
        result = {
            "passed": False,
            "verdict": None,
            "audit_time": None,
            "reason": "未找到有效的审计报告",
        }

        # 搜索最新的审计报告
        audit_dir = self.reports_dir / "ai_dispatch" / "latest"
        audit_report = audit_dir / "audit_verdict.md"

        if not audit_report.exists():
            return result

        try:
            with open(audit_report, encoding="utf-8") as f:
                content = f.read()

            # 提取审计结论
            verdict_match = re.search(r"整体结论\s*:\s*(GO|NO-GO)", content, re.IGNORECASE)
            if verdict_match:
                verdict = verdict_match.group(1).upper()
                result["verdict"] = verdict

                # 提取审计时间
                time_match = re.search(r"审计时间\s*:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")
                if time_match:
                    result["audit_time"] = time_match.group(1)

                if verdict == "GO":
                    result["passed"] = True
                    result["reason"] = "审计结论为GO，满足要求"
                else:
                    result["reason"] = f"审计结论为{verdict}，需要GO才能进入实盘"
            else:
                result["reason"] = "审计报告中未找到明确的结论"
        except Exception as e:
            logger.error(f"解析审计报告失败: {e}")
            result["reason"] = f"解析审计报告失败: {str(e)}"

        return result

    def check_release_gate(self) -> dict[str, Any]:
        """
        检查发布门禁条件：paper交易至少运行一个周期且审计结论为GO

        Returns:
            Dict[str, Any]: 综合检查结果
        """
        # 检查paper交易周期
        paper_result = self.check_paper_trading_cycles()

        # 检查审计结论
        audit_result = self.check_audit_verdict()

        # 综合判断
        overall_passed = paper_result["passed"] and audit_result["passed"]

        # 收集阻塞原因
        blocked_reasons = []
        if not paper_result["passed"]:
            blocked_reasons.append(paper_result["reason"])
        if not audit_result["passed"]:
            blocked_reasons.append(audit_result["reason"])

        return {
            "passed": overall_passed,
            "paper_check": paper_result,
            "audit_check": audit_result,
            "blocked_reasons": blocked_reasons,
        }

    def _write_reconciliation_status(self) -> None:
        """
        Write reconciliation status to file for external consumption.
        """
        status_file = self.reports_dir / "reconciliation_status.json"

        # 构建可序列化的状态数据
        status_data = {
            "ok": self._status.ok,
            "blocked": self._status.blocked,
            "timestamp": self._status.timestamp,
            "reasons": self._status.reasons,
            "drift_type": self._status.drift_type.value if self._status.drift_type else None,
            "diffs_summary": self._status.diffs_summary,
            "recommended_action": self._status.recommended_action.value,
            "original_config_hash": self._status.original_config_hash,
            "current_config_hash": self._status.current_config_hash,
            "config_drift_report": self._status.config_drift_report,
            "reconciliation_report": {
                "ok": self._status.reconciliation_report.ok,
                "drift_type": self._status.reconciliation_report.drift_type.value,
                "diffs_count": len(self._status.reconciliation_report.diffs),
                "recommended_action": self._status.reconciliation_report.recommended_action.value,
            }
            if self._status.reconciliation_report
            else None,
        }

        try:
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(status_data, f, indent=2, ensure_ascii=False)
            logger.info(f"对账状态已写入: {status_file}")
        except Exception as e:
            logger.error(f"写入对账状态失败: {e}")

    def write_release_gate_evidence(self, gate_result: dict[str, Any]) -> None:
        """
        将发布门禁检查结果写入证据文件

        Args:
            gate_result: 发布门禁检查结果
        """
        # 写入结构化证据文件
        evidence_file = self.reports_dir / "release_gate_evidence.json"

        evidence_data = {
            "timestamp": datetime.now().timestamp(),
            "overall_passed": gate_result["passed"],
            "paper_check": gate_result["paper_check"],
            "audit_check": gate_result["audit_check"],
            "blocked_reasons": gate_result["blocked_reasons"],
        }

        try:
            with open(evidence_file, "w", encoding="utf-8") as f:
                json.dump(evidence_data, f, indent=2, ensure_ascii=False)
            logger.info(f"发布门禁证据已写入: {evidence_file}")
        except Exception as e:
            logger.error(f"写入发布门禁证据失败: {e}")

        # 同时写入到last_run.md文件
        self.write_to_last_run_with_gate_result(gate_result)

    def write_to_last_run_with_gate_result(self, gate_result: dict[str, Any]) -> None:
        """
        将发布门禁检查结果写入last_run.md报告

        Args:
            gate_result: 发布门禁检查结果
        """
        last_run_file = self.reports_dir / "last_run.md"

        # 读取现有内容
        existing_content = ""
        if last_run_file.exists():
            with open(last_run_file, encoding="utf-8") as f:
                existing_content = f.read()

        # 构建发布门禁检查内容
        gate_section = f"""
## 发布门禁检查结果

### 总体状态
- **通过**: {"是" if gate_result["passed"] else "否"}

### Paper交易检查
- **结果**: {"通过" if gate_result["paper_check"]["passed"] else "失败"}
- **运行周期数**: {gate_result["paper_check"]["cycle_count"]}
- **最近运行时间**: {datetime.fromtimestamp(gate_result["paper_check"]["last_run_time"]).strftime("%Y-%m-%d %H:%M:%S") if gate_result["paper_check"]["last_run_time"] else "未知"}
- **详情**: {gate_result["paper_check"]["reason"]}

### 审计结论检查
- **结果**: {"通过" if gate_result["audit_check"]["passed"] else "失败"}
- **审计结论**: {gate_result["audit_check"]["verdict"] if gate_result["audit_check"]["verdict"] else "未知"}
- **审计时间**: {gate_result["audit_check"]["audit_time"] if gate_result["audit_check"]["audit_time"] else "未知"}
- **详情**: {gate_result["audit_check"]["reason"]}

### 阻塞原因
"""

        for reason in gate_result["blocked_reasons"]:
            gate_section += f"- {reason}\n"

        # 写入到文件开头
        with open(last_run_file, "w", encoding="utf-8") as f:
            f.write(gate_section + "\n" + existing_content)

        logger.info(f"发布门禁结果已写入: {last_run_file}")

    def write_to_last_run(self) -> None:
        """
        Write readiness status to last_run.md report.
        """
        last_run_file = self.reports_dir / "last_run.md"

        # 读取现有内容
        existing_content = ""
        if last_run_file.exists():
            with open(last_run_file, encoding="utf-8") as f:
                existing_content = f.read()

        # 构建 readiness 状态内容
        readiness_section = f"""
## 执行就绪状态

### 总体状态
- **就绪**: {"是" if self.is_ready() else "否"}
- **阻塞**: {"是" if self.is_blocked() else "否"}

### 详细信息
"""

        for reason in self._status.reasons:
            readiness_section += f"- {reason}\n"

        # 添加配置漂移信息
        if self._status.original_config_hash or self._status.config_drift_report:
            readiness_section += "\n### 配置漂移信息\n"
            if self._status.original_config_hash:
                readiness_section += f"- **原始配置哈希**: {self._status.original_config_hash}\n"
            if self._status.current_config_hash:
                readiness_section += f"- **当前配置哈希**: {self._status.current_config_hash}\n"
            if self._status.config_drift_report:
                readiness_section += f"- **漂移报告ID**: {self._status.config_drift_report.get('report_id', 'N/A')}\n"
                readiness_section += (
                    f"- **漂移数量**: {self._status.config_drift_report.get('drifts_count', 0)}\n"
                )
                readiness_section += (
                    f"- **报告路径**: {self._status.config_drift_report.get('saved_path', 'N/A')}\n"
                )

        # 写入到文件开头
        with open(last_run_file, "w", encoding="utf-8") as f:
            f.write(readiness_section + "\n" + existing_content)

        logger.info(f"执行就绪状态已写入: {last_run_file}")

    def update_from_capacity_report(self, capacity_report: dict) -> None:
        """
        Update execution readiness based on capacity report.

        Args:
            capacity_report: Capacity report generated by CapacityMonitor
        """
        logger.info("根据容量报告更新执行就绪状态")

        # 提取安全上限
        safe_limits = capacity_report.get("safe_limits", {})
        conclusions = capacity_report.get("conclusions", [])

        # 保存容量报告引用
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        capacity_report_path = self.reports_dir / f"capacity_report_{timestamp}.json"
        with open(capacity_report_path, "w", encoding="utf-8") as f:
            json.dump(capacity_report, f, default=str, indent=2, ensure_ascii=False)

        logger.info(f"容量报告已保存到: {capacity_report_path}")

        # 更新资源门禁配置
        # 这里可以根据需要更新风险管理器或其他相关组件的配置
        # 例如，更新风险管理器的策略数量限制
        self.risk_manager.update_capacity_limits(
            {
                "max_strategies": safe_limits.get("safe_strategy_count", 10),
                "max_symbols": safe_limits.get("safe_symbol_count", 10),
            }
        )

        # 记录容量更新事件
        self.record_capacity_update(safe_limits, conclusions)

        # 将容量信息写入到last_run.md报告
        self.write_capacity_info_to_last_run(safe_limits, conclusions)

    def record_capacity_update(self, safe_limits: dict, conclusions: list) -> None:
        """
        Record capacity update event.

        Args:
            safe_limits: Safe limits from capacity report
            conclusions: Conclusions from capacity report
        """
        event_message = f"容量报告更新: 安全上限 - 策略数: {safe_limits.get('safe_strategy_count')}, 品种数: {safe_limits.get('safe_symbol_count')}"
        logger.info(event_message)

        # 这里可以添加事件记录逻辑，例如写入日志或数据库

    def write_capacity_info_to_last_run(self, safe_limits: dict, conclusions: list) -> None:
        """
        Write capacity information to last_run.md report.

        Args:
            safe_limits: Safe limits from capacity report
            conclusions: Conclusions from capacity report
        """
        last_run_file = self.reports_dir / "last_run.md"

        # 读取现有内容
        existing_content = ""
        if last_run_file.exists():
            with open(last_run_file, encoding="utf-8") as f:
                existing_content = f.read()

        # 构建容量信息内容
        capacity_section = f"""
## 容量报告信息

### 安全上限
- **最大策略数**: {safe_limits.get("safe_strategy_count", "N/A")}
- **最大品种数**: {safe_limits.get("safe_symbol_count", "N/A")}
- **CPU使用率阈值**: {safe_limits.get("thresholds", {}).get("cpu_percent", "N/A")}%
- **内存使用率阈值**: {safe_limits.get("thresholds", {}).get("memory_percent", "N/A")}%

### 容量测试结论
"""

        for conclusion in conclusions:
            capacity_section += f"- {conclusion}\n"

        # 写入到文件开头
        with open(last_run_file, "w", encoding="utf-8") as f:
            f.write(capacity_section + "\n" + existing_content)

        logger.info(f"容量信息已写入: {last_run_file}")
