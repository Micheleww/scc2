#!/usr/bin/env python3
"""
线上线下一致性校验模块
实现同窗离线计算与线上输出对比，确保功能一致性
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ParityCheckResult:
    """
    一致性校验结果
    """

    check_name: str  # 检查名称
    passed: bool  # 是否通过
    message: str  # 检查结果描述
    details: dict[str, Any]  # 详细信息
    confidence: float  # 置信度 (0-1)
    severity: str  # 严重程度: LOW, MEDIUM, HIGH


@dataclass
class ParityReport:
    """
    一致性校验报告
    """

    report_id: str  # 报告ID
    timestamp: str  # 报告生成时间
    overall_status: str  # 总体状态: PASS, FAIL, PARTIAL
    total_checks: int  # 总检查次数
    passed_checks: int  # 通过检查次数
    failed_checks: int  # 失败检查次数
    check_results: list[ParityCheckResult]  # 检查结果列表
    metadata: dict[str, Any]  # 元数据


class FeatureParityChecker:
    """
    功能一致性检查器
    """

    def __init__(self, config: dict[str, Any] = None):
        """
        初始化功能一致性检查器

        Args:
            config: 配置参数
        """
        self.config = config or {}

        # 默认配置
        self.default_config = {
            "tolerance": 0.01,  # 数值容差 (1%)
            "max_missing_ratio": 0.05,  # 最大缺失率 (5%)
            "max_outlier_ratio": 0.02,  # 最大异常值率 (2%)
            "mask_coverage_threshold": 0.9,  # mask覆盖阈值 (90%)
            "alignment_threshold": 0.95,  # 对齐阈值 (95%)
        }

        # 合并配置
        self.actual_config = {**self.default_config, **self.config}

        logger.info("功能一致性检查器初始化完成")

    def check_numeric_consistency(
        self,
        offline_data: pd.DataFrame,
        online_data: pd.DataFrame,
        key_columns: list[str],
        numeric_columns: list[str],
    ) -> ParityCheckResult:
        """
        检查数值一致性

        Args:
            offline_data: 离线数据
            online_data: 线上数据
            key_columns: 用于对齐的关键字段
            numeric_columns: 数值字段列表

        Returns:
            ParityCheckResult: 检查结果
        """
        try:
            # 对齐数据
            merged_data = pd.merge(
                offline_data,
                online_data,
                on=key_columns,
                suffixes=("_offline", "_online"),
                how="inner",
            )

            if merged_data.empty:
                return ParityCheckResult(
                    check_name="numeric_consistency",
                    passed=False,
                    message="数据对齐失败，没有匹配的记录",
                    details={
                        "offline_records": len(offline_data),
                        "online_records": len(online_data),
                        "merged_records": len(merged_data),
                        "key_columns": key_columns,
                    },
                    confidence=0.0,
                    severity="HIGH",
                )

            # 计算对齐率
            alignment_ratio = len(merged_data) / max(len(offline_data), len(online_data))

            # 检查数值差异
            tolerance = self.actual_config["tolerance"]
            inconsistent_fields = []
            field_stats = {}

            for col in numeric_columns:
                if (
                    f"{col}_offline" in merged_data.columns
                    and f"{col}_online" in merged_data.columns
                ):
                    offline_vals = merged_data[f"{col}_offline"].astype(float)
                    online_vals = merged_data[f"{col}_online"].astype(float)

                    # 计算相对差异
                    diff = np.abs(offline_vals - online_vals) / (
                        np.abs(online_vals) + 1e-8
                    )  # 避免除以零

                    # 检查是否在容差范围内
                    within_tolerance = diff <= tolerance
                    inconsistent_count = len(diff) - within_tolerance.sum()
                    inconsistent_ratio = inconsistent_count / len(diff)

                    field_stats[col] = {
                        "inconsistent_count": int(inconsistent_count),
                        "inconsistent_ratio": float(inconsistent_ratio),
                        "max_diff": float(diff.max()),
                        "mean_diff": float(diff.mean()),
                        "median_diff": float(diff.median()),
                    }

                    if inconsistent_ratio > 0:
                        inconsistent_fields.append(col)

            # 判断总体结果
            passed = (
                len(inconsistent_fields) == 0
                and alignment_ratio >= self.actual_config["alignment_threshold"]
            )
            message = (
                "数值一致性检查通过"
                if passed
                else f"数值一致性检查失败，{len(inconsistent_fields)}个字段不一致"
            )

            return ParityCheckResult(
                check_name="numeric_consistency",
                passed=passed,
                message=message,
                details={
                    "alignment_ratio": float(alignment_ratio),
                    "alignment_threshold": self.actual_config["alignment_threshold"],
                    "tolerance": tolerance,
                    "inconsistent_fields": inconsistent_fields,
                    "field_stats": field_stats,
                    "offline_records": len(offline_data),
                    "online_records": len(online_data),
                    "merged_records": len(merged_data),
                },
                confidence=alignment_ratio,
                severity="HIGH" if not passed else "LOW",
            )

        except Exception as e:
            logger.error(f"数值一致性检查出错: {e}")
            return ParityCheckResult(
                check_name="numeric_consistency",
                passed=False,
                message=f"数值一致性检查出错: {str(e)}",
                details={"error": str(e)},
                confidence=0.0,
                severity="HIGH",
            )

    def check_mask_consistency(
        self,
        offline_data: pd.DataFrame,
        online_data: pd.DataFrame,
        key_columns: list[str],
        mask_columns: list[str],
    ) -> ParityCheckResult:
        """
        检查mask一致性

        Args:
            offline_data: 离线数据
            online_data: 线上数据
            key_columns: 用于对齐的关键字段
            mask_columns: mask字段列表

        Returns:
            ParityCheckResult: 检查结果
        """
        try:
            # 对齐数据
            merged_data = pd.merge(
                offline_data,
                online_data,
                on=key_columns,
                suffixes=("_offline", "_online"),
                how="inner",
            )

            if merged_data.empty:
                return ParityCheckResult(
                    check_name="mask_consistency",
                    passed=False,
                    message="数据对齐失败，没有匹配的记录",
                    details={
                        "offline_records": len(offline_data),
                        "online_records": len(online_data),
                        "merged_records": len(merged_data),
                        "key_columns": key_columns,
                    },
                    confidence=0.0,
                    severity="MEDIUM",
                )

            # 检查mask一致性
            inconsistent_masks = []
            mask_stats = {}

            for col in mask_columns:
                if (
                    f"{col}_offline" in merged_data.columns
                    and f"{col}_online" in merged_data.columns
                ):
                    offline_masks = merged_data[f"{col}_offline"].fillna(False).astype(bool)
                    online_masks = merged_data[f"{col}_online"].fillna(False).astype(bool)

                    # 计算mask覆盖率
                    offline_coverage = offline_masks.sum() / len(offline_masks)
                    online_coverage = online_masks.sum() / len(online_masks)

                    # 计算mask一致性
                    consistency = (offline_masks == online_masks).sum() / len(offline_masks)

                    mask_stats[col] = {
                        "offline_coverage": float(offline_coverage),
                        "online_coverage": float(online_coverage),
                        "consistency": float(consistency),
                        "mismatch_count": int(
                            len(offline_masks) - (offline_masks == online_masks).sum()
                        ),
                    }

                    if consistency < 1.0:
                        inconsistent_masks.append(col)

            # 判断总体结果
            passed = len(inconsistent_masks) == 0
            message = (
                "mask一致性检查通过"
                if passed
                else f"mask一致性检查失败，{len(inconsistent_masks)}个mask不一致"
            )

            return ParityCheckResult(
                check_name="mask_consistency",
                passed=passed,
                message=message,
                details={
                    "inconsistent_masks": inconsistent_masks,
                    "mask_stats": mask_stats,
                    "offline_records": len(offline_data),
                    "online_records": len(online_data),
                    "merged_records": len(merged_data),
                },
                confidence=1.0 if passed else 0.5,
                severity="MEDIUM" if not passed else "LOW",
            )

        except Exception as e:
            logger.error(f"mask一致性检查出错: {e}")
            return ParityCheckResult(
                check_name="mask_consistency",
                passed=False,
                message=f"mask一致性检查出错: {str(e)}",
                details={"error": str(e)},
                confidence=0.0,
                severity="MEDIUM",
            )

    def check_data_coverage(
        self, offline_data: pd.DataFrame, online_data: pd.DataFrame, key_columns: list[str]
    ) -> ParityCheckResult:
        """
        检查数据覆盖一致性

        Args:
            offline_data: 离线数据
            online_data: 线上数据
            key_columns: 用于对齐的关键字段

        Returns:
            ParityCheckResult: 检查结果
        """
        try:
            # 计算缺失率
            offline_missing = offline_data.isnull().sum().to_dict()
            online_missing = online_data.isnull().sum().to_dict()

            # 计算缺失率
            offline_missing_ratios = {
                col: (count / len(offline_data)) for col, count in offline_missing.items()
            }
            online_missing_ratios = {
                col: (count / len(online_data)) for col, count in online_missing.items()
            }

            # 检查缺失率是否超过阈值
            max_missing_ratio = self.actual_config["max_missing_ratio"]
            offline_excessive_missing = [
                col for col, ratio in offline_missing_ratios.items() if ratio > max_missing_ratio
            ]
            online_excessive_missing = [
                col for col, ratio in online_missing_ratios.items() if ratio > max_missing_ratio
            ]

            # 检查缺失模式是否一致
            missing_pattern_diff = set(offline_excessive_missing) ^ set(online_excessive_missing)

            # 判断总体结果
            passed = (
                len(offline_excessive_missing) == 0
                and len(online_excessive_missing) == 0
                and len(missing_pattern_diff) == 0
            )
            message = (
                "数据覆盖一致性检查通过"
                if passed
                else f"数据覆盖一致性检查失败，离线数据有{len(offline_excessive_missing)}个字段缺失率过高，线上数据有{len(online_excessive_missing)}个字段缺失率过高"
            )

            return ParityCheckResult(
                check_name="data_coverage",
                passed=passed,
                message=message,
                details={
                    "max_missing_ratio": max_missing_ratio,
                    "offline_excessive_missing": offline_excessive_missing,
                    "online_excessive_missing": online_excessive_missing,
                    "missing_pattern_diff": list(missing_pattern_diff),
                    "offline_missing_ratios": offline_missing_ratios,
                    "online_missing_ratios": online_missing_ratios,
                    "offline_records": len(offline_data),
                    "online_records": len(online_data),
                },
                confidence=1.0 if passed else 0.5,
                severity="MEDIUM" if not passed else "LOW",
            )

        except Exception as e:
            logger.error(f"数据覆盖一致性检查出错: {e}")
            return ParityCheckResult(
                check_name="data_coverage",
                passed=False,
                message=f"数据覆盖一致性检查出错: {str(e)}",
                details={"error": str(e)},
                confidence=0.0,
                severity="MEDIUM",
            )

    def generate_parity_report(
        self,
        offline_data: pd.DataFrame,
        online_data: pd.DataFrame,
        key_columns: list[str],
        numeric_columns: list[str],
        mask_columns: list[str],
    ) -> ParityReport:
        """
        生成完整的一致性报告

        Args:
            offline_data: 离线数据
            online_data: 线上数据
            key_columns: 用于对齐的关键字段
            numeric_columns: 数值字段列表
            mask_columns: mask字段列表

        Returns:
            ParityReport: 完整的一致性报告
        """
        # 生成报告ID
        report_id = f"parity_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}"
        timestamp = datetime.now().isoformat()

        # 执行各项检查
        check_results = []

        # 1. 数值一致性检查
        numeric_result = self.check_numeric_consistency(
            offline_data, online_data, key_columns, numeric_columns
        )
        check_results.append(numeric_result)

        # 2. mask一致性检查
        if mask_columns:
            mask_result = self.check_mask_consistency(
                offline_data, online_data, key_columns, mask_columns
            )
            check_results.append(mask_result)

        # 3. 数据覆盖一致性检查
        coverage_result = self.check_data_coverage(offline_data, online_data, key_columns)
        check_results.append(coverage_result)

        # 计算总体统计
        total_checks = len(check_results)
        passed_checks = sum(1 for result in check_results if result.passed)
        failed_checks = total_checks - passed_checks

        # 确定总体状态
        if failed_checks == 0:
            overall_status = "PASS"
        elif passed_checks == 0:
            overall_status = "FAIL"
        else:
            # 检查是否有高严重性失败
            has_high_severity_failure = any(
                result.severity == "HIGH" and not result.passed for result in check_results
            )
            # 检查失败率是否超过50%
            high_failure_rate = failed_checks / total_checks > 0.5

            if has_high_severity_failure or high_failure_rate:
                overall_status = "FAIL"
            else:
                overall_status = "PARTIAL"

        # 生成元数据
        metadata = {
            "config": self.actual_config,
            "offline_data_shape": offline_data.shape,
            "online_data_shape": online_data.shape,
            "key_columns": key_columns,
            "numeric_columns": numeric_columns,
            "mask_columns": mask_columns,
            "report_id": report_id,
            "timestamp": timestamp,
        }

        # 创建报告
        report = ParityReport(
            report_id=report_id,
            timestamp=timestamp,
            overall_status=overall_status,
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            check_results=check_results,
            metadata=metadata,
        )

        logger.info(
            f"生成一致性报告: {report_id}, 状态: {overall_status}, 通过: {passed_checks}/{total_checks}"
        )
        return report

    def save_report(
        self, report: ParityReport, output_dir: Path = Path("reports")
    ) -> dict[str, str]:
        """
        保存报告到文件

        Args:
            report: 一致性报告
            output_dir: 输出目录

        Returns:
            Dict[str, str]: 保存的文件路径
        """
        # 确保输出目录存在
        output_dir.mkdir(parents=True, exist_ok=True)

        # 保存JSON格式报告
        json_path = output_dir / f"{report.report_id}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self._report_to_dict(report), f, indent=2, ensure_ascii=False, default=str)

        # 保存Markdown格式报告
        md_path = output_dir / f"{report.report_id}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(self._generate_md_report(report))

        # 更新last_parity_report.json链接
        last_report_path = output_dir / "last_parity_report.json"
        with open(last_report_path, "w", encoding="utf-8") as f:
            json.dump(self._report_to_dict(report), f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"报告已保存: {json_path}, {md_path}")
        return {
            "json_path": str(json_path),
            "md_path": str(md_path),
            "last_report_path": str(last_report_path),
        }

    def _report_to_dict(self, report: ParityReport) -> dict[str, Any]:
        """
        将报告转换为字典格式

        Args:
            report: 一致性报告

        Returns:
            Dict[str, Any]: 报告的字典表示
        """
        return {
            "report_id": report.report_id,
            "timestamp": report.timestamp,
            "overall_status": report.overall_status,
            "total_checks": report.total_checks,
            "passed_checks": report.passed_checks,
            "failed_checks": report.failed_checks,
            "check_results": [
                {
                    "check_name": result.check_name,
                    "passed": result.passed,
                    "message": result.message,
                    "details": result.details,
                    "confidence": result.confidence,
                    "severity": result.severity,
                }
                for result in report.check_results
            ],
            "metadata": report.metadata,
        }

    def _generate_md_report(self, report: ParityReport) -> str:
        """
        生成Markdown格式报告

        Args:
            report: 一致性报告

        Returns:
            str: Markdown格式的报告
        """
        lines = [
            "# 功能一致性报告\n",
            f"\n**报告ID**: {report.report_id}",
            f"**生成时间**: {report.timestamp}",
            f"**总体状态**: {report.overall_status}",
            f"**检查项**: {report.total_checks}",
            f"**通过项**: {report.passed_checks}",
            f"**失败项**: {report.failed_checks}",
            "\n## 配置信息",
            "\n| 配置项 | 值 |",
            "|--------|-----|",
        ]

        # 添加配置信息
        for key, value in report.metadata["config"].items():
            lines.append(f"| {key} | {value} |")

        # 添加数据信息
        lines.extend(
            [
                "\n## 数据信息",
                "\n| 数据类型 | 行数 | 列数 |",
                "|----------|------|------|",
                f"| 离线数据 | {report.metadata['offline_data_shape'][0]} | {report.metadata['offline_data_shape'][1]} |",
                f"| 线上数据 | {report.metadata['online_data_shape'][0]} | {report.metadata['online_data_shape'][1]} |",
                "\n## 关键字段",
                f"{', '.join(report.metadata['key_columns'])}",
                "\n## 数值字段",
                f"{', '.join(report.metadata['numeric_columns'])}",
            ]
        )

        # 添加mask字段
        if report.metadata["mask_columns"]:
            lines.extend(
                [
                    "\n## Mask字段",
                    f"{', '.join(report.metadata['mask_columns'])}",
                ]
            )

        # 添加检查结果
        lines.append("\n## 检查结果")

        for result in report.check_results:
            status_icon = "✅" if result.passed else "❌"
            lines.extend(
                [
                    f"\n### {status_icon} {result.check_name}",
                    f"**状态**: {'通过' if result.passed else '失败'}",
                    f"**消息**: {result.message}",
                    f"**置信度**: {result.confidence:.2f}",
                    f"**严重程度**: {result.severity}",
                    "\n**详细信息**:",
                ]
            )

            # 添加详细信息
            for key, value in result.details.items():
                if isinstance(value, dict):
                    lines.append(f"\n#### {key}")
                    for sub_key, sub_value in value.items():
                        if isinstance(sub_value, float):
                            lines.append(f"- {sub_key}: {sub_value:.4f}")
                        else:
                            lines.append(f"- {sub_key}: {sub_value}")
                elif isinstance(value, list):
                    lines.append(f"\n#### {key}")
                    for item in value:
                        lines.append(f"- {item}")
                else:
                    lines.append(f"- {key}: {value}")

        return "\n".join(lines)

    def is_blocked(self, report: ParityReport) -> bool:
        """
        判断是否需要阻断

        Args:
            report: 一致性报告

        Returns:
            bool: 如果报告状态为FAIL，返回True，表示需要阻断
        """
        return report.overall_status == "FAIL"
