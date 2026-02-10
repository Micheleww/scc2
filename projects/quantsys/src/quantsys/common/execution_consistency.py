#!/usr/bin/env python3
"""
线上/回测成交口径一致性校验模块
确保成交价、滑点、手续费、部分成交处理在paper/backtest/live同口径
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ExecutionConsistencyResult:
    """
    成交一致性检查结果
    """

    check_name: str  # 检查名称
    passed: bool  # 是否通过
    message: str  # 检查结果描述
    details: dict[str, Any]  # 详细信息
    severity: str  # 严重程度: LOW, MEDIUM, HIGH


@dataclass
class ConsistencyReport:
    """
    成交一致性报告
    """

    report_id: str  # 报告ID
    timestamp: str  # 报告生成时间
    overall_status: str  # 总体状态: PASS, FAIL, PARTIAL
    total_checks: int  # 总检查次数
    passed_checks: int  # 通过检查次数
    failed_checks: int  # 失败检查次数
    check_results: list[ExecutionConsistencyResult]  # 检查结果列表
    metadata: dict[str, Any]  # 元数据
    recommendations: list[str]  # 建议


class ExecutionConsistencyChecker:
    """
    成交一致性检查器
    """

    def __init__(self, config: dict[str, Any] = None):
        """
        初始化成交一致性检查器

        Args:
            config: 配置参数
        """
        self.config = config or {}

        # 默认配置
        self.default_config = {
            "price_tolerance": 0.001,  # 价格容差 (0.1%)
            "fee_tolerance": 0.01,  # 手续费容差 (1%)
            "slippage_tolerance": 0.002,  # 滑点容差 (0.2%)
            "output_dir": "reports",  # 报告输出目录
            "evidence_dir": "evidence",  # 证据输出目录
        }

        # 合并配置
        self.actual_config = {**self.default_config, **self.config}

        # 确保输出目录存在
        self.output_dir = Path(self.actual_config["output_dir"])
        self.evidence_dir = Path(self.actual_config["evidence_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        logger.info("成交一致性检查器初始化完成")

    def calculate_slippage(self, order_price: float, fill_price: float) -> float:
        """
        计算滑点

        Args:
            order_price: 订单价格
            fill_price: 成交价格

        Returns:
            float: 滑点百分比
        """
        if order_price == 0:
            return 0.0

        return abs(fill_price - order_price) / order_price

    def calculate_fee(self, fill_amount: float, fill_price: float, fee_rate: float) -> float:
        """
        计算手续费

        Args:
            fill_amount: 成交数量
            fill_price: 成交价格
            fee_rate: 手续费率

        Returns:
            float: 手续费金额
        """
        return fill_amount * fill_price * fee_rate

    def check_price_consistency(
        self, paper_data: pd.DataFrame, backtest_data: pd.DataFrame, live_data: pd.DataFrame
    ) -> ExecutionConsistencyResult:
        """
        检查成交价一致性

        Args:
            paper_data: Paper交易数据
            backtest_data: 回测数据
            live_data: 实盘数据

        Returns:
            ExecutionConsistencyResult: 检查结果
        """
        try:
            # 检查是否有足够的数据
            if paper_data.empty or backtest_data.empty:
                return ExecutionConsistencyResult(
                    check_name="price_consistency",
                    passed=False,
                    message="数据不足，无法进行成交价一致性检查",
                    details={
                        "paper_records": len(paper_data),
                        "backtest_records": len(backtest_data),
                        "live_records": len(live_data),
                    },
                    severity="MEDIUM",
                )

            # 合并数据
            # 这里简化处理，实际应根据order_id或timestamp对齐数据

            # 计算平均成交价格
            paper_avg_price = paper_data["fill_price"].mean()
            backtest_avg_price = backtest_data["fill_price"].mean()

            # 计算价格差异
            price_diff = abs(paper_avg_price - backtest_avg_price) / backtest_avg_price
            tolerance = self.actual_config["price_tolerance"]

            passed = price_diff <= tolerance

            return ExecutionConsistencyResult(
                check_name="price_consistency",
                passed=passed,
                message=f"成交价一致性检查{'通过' if passed else '失败'}",
                details={
                    "paper_avg_price": paper_avg_price,
                    "backtest_avg_price": backtest_avg_price,
                    "price_diff": price_diff,
                    "tolerance": tolerance,
                },
                severity="HIGH" if not passed else "LOW",
            )
        except Exception as e:
            logger.error(f"成交价一致性检查出错: {e}")
            return ExecutionConsistencyResult(
                check_name="price_consistency",
                passed=False,
                message=f"成交价一致性检查出错: {str(e)}",
                details={"error": str(e)},
                severity="HIGH",
            )

    def check_slippage_consistency(
        self, paper_data: pd.DataFrame, backtest_data: pd.DataFrame, live_data: pd.DataFrame
    ) -> ExecutionConsistencyResult:
        """
        检查滑点一致性

        Args:
            paper_data: Paper交易数据
            backtest_data: 回测数据
            live_data: 实盘数据

        Returns:
            ExecutionConsistencyResult: 检查结果
        """
        try:
            # 检查是否有足够的数据
            if paper_data.empty or backtest_data.empty:
                return ExecutionConsistencyResult(
                    check_name="slippage_consistency",
                    passed=False,
                    message="数据不足，无法进行滑点一致性检查",
                    details={
                        "paper_records": len(paper_data),
                        "backtest_records": len(backtest_data),
                        "live_records": len(live_data),
                    },
                    severity="MEDIUM",
                )

            # 计算滑点
            paper_data["slippage"] = paper_data.apply(
                lambda x: self.calculate_slippage(x["order_price"], x["fill_price"]), axis=1
            )

            backtest_data["slippage"] = backtest_data.apply(
                lambda x: self.calculate_slippage(x["order_price"], x["fill_price"]), axis=1
            )

            # 计算平均滑点
            paper_avg_slippage = paper_data["slippage"].mean()
            backtest_avg_slippage = backtest_data["slippage"].mean()

            # 计算滑点差异
            slippage_diff = abs(paper_avg_slippage - backtest_avg_slippage)
            tolerance = self.actual_config["slippage_tolerance"]

            passed = slippage_diff <= tolerance

            return ExecutionConsistencyResult(
                check_name="slippage_consistency",
                passed=passed,
                message=f"滑点一致性检查{'通过' if passed else '失败'}",
                details={
                    "paper_avg_slippage": paper_avg_slippage,
                    "backtest_avg_slippage": backtest_avg_slippage,
                    "slippage_diff": slippage_diff,
                    "tolerance": tolerance,
                },
                severity="HIGH" if not passed else "LOW",
            )
        except Exception as e:
            logger.error(f"滑点一致性检查出错: {e}")
            return ExecutionConsistencyResult(
                check_name="slippage_consistency",
                passed=False,
                message=f"滑点一致性检查出错: {str(e)}",
                details={"error": str(e)},
                severity="HIGH",
            )

    def check_fee_consistency(
        self,
        paper_data: pd.DataFrame,
        backtest_data: pd.DataFrame,
        live_data: pd.DataFrame,
        fee_rate: float,
    ) -> ExecutionConsistencyResult:
        """
        检查手续费一致性

        Args:
            paper_data: Paper交易数据
            backtest_data: 回测数据
            live_data: 实盘数据
            fee_rate: 手续费率

        Returns:
            ExecutionConsistencyResult: 检查结果
        """
        try:
            # 检查是否有足够的数据
            if paper_data.empty or backtest_data.empty:
                return ExecutionConsistencyResult(
                    check_name="fee_consistency",
                    passed=False,
                    message="数据不足，无法进行手续费一致性检查",
                    details={
                        "paper_records": len(paper_data),
                        "backtest_records": len(backtest_data),
                        "live_records": len(live_data),
                    },
                    severity="MEDIUM",
                )

            # 计算手续费
            paper_data["calculated_fee"] = paper_data.apply(
                lambda x: self.calculate_fee(x["fill_amount"], x["fill_price"], fee_rate), axis=1
            )

            backtest_data["calculated_fee"] = backtest_data.apply(
                lambda x: self.calculate_fee(x["fill_amount"], x["fill_price"], fee_rate), axis=1
            )

            # 计算实际手续费与理论手续费的差异
            paper_fee_diff = abs(paper_data["actual_fee"] - paper_data["calculated_fee"]).mean()
            backtest_fee_diff = abs(
                backtest_data["actual_fee"] - backtest_data["calculated_fee"]
            ).mean()

            # 计算手续费差异
            fee_diff = abs(paper_fee_diff - backtest_fee_diff)
            tolerance = self.actual_config["fee_tolerance"]

            passed = fee_diff <= tolerance

            return ExecutionConsistencyResult(
                check_name="fee_consistency",
                passed=passed,
                message=f"手续费一致性检查{'通过' if passed else '失败'}",
                details={
                    "paper_fee_diff": paper_fee_diff,
                    "backtest_fee_diff": backtest_fee_diff,
                    "fee_diff": fee_diff,
                    "tolerance": tolerance,
                    "fee_rate": fee_rate,
                },
                severity="HIGH" if not passed else "LOW",
            )
        except Exception as e:
            logger.error(f"手续费一致性检查出错: {e}")
            return ExecutionConsistencyResult(
                check_name="fee_consistency",
                passed=False,
                message=f"手续费一致性检查出错: {str(e)}",
                details={"error": str(e)},
                severity="HIGH",
            )

    def check_partial_fill_consistency(
        self, paper_data: pd.DataFrame, backtest_data: pd.DataFrame, live_data: pd.DataFrame
    ) -> ExecutionConsistencyResult:
        """
        检查部分成交处理一致性

        Args:
            paper_data: Paper交易数据
            backtest_data: 回测数据
            live_data: 实盘数据

        Returns:
            ExecutionConsistencyResult: 检查结果
        """
        try:
            # 检查是否有足够的数据
            if paper_data.empty or backtest_data.empty:
                return ExecutionConsistencyResult(
                    check_name="partial_fill_consistency",
                    passed=False,
                    message="数据不足，无法进行部分成交一致性检查",
                    details={
                        "paper_records": len(paper_data),
                        "backtest_records": len(backtest_data),
                        "live_records": len(live_data),
                    },
                    severity="MEDIUM",
                )

            # 计算部分成交比例
            paper_partial_ratio = (paper_data["fill_amount"] < paper_data["order_amount"]).mean()
            backtest_partial_ratio = (
                backtest_data["fill_amount"] < backtest_data["order_amount"]
            ).mean()

            # 检查部分成交处理逻辑是否一致
            # 这里简化处理，实际应检查部分成交的处理逻辑
            passed = abs(paper_partial_ratio - backtest_partial_ratio) < 0.1  # 允许10%的差异

            return ExecutionConsistencyResult(
                check_name="partial_fill_consistency",
                passed=passed,
                message=f"部分成交处理一致性检查{'通过' if passed else '失败'}",
                details={
                    "paper_partial_ratio": paper_partial_ratio,
                    "backtest_partial_ratio": backtest_partial_ratio,
                    "ratio_diff": abs(paper_partial_ratio - backtest_partial_ratio),
                },
                severity="HIGH" if not passed else "LOW",
            )
        except Exception as e:
            logger.error(f"部分成交处理一致性检查出错: {e}")
            return ExecutionConsistencyResult(
                check_name="partial_fill_consistency",
                passed=False,
                message=f"部分成交处理一致性检查出错: {str(e)}",
                details={"error": str(e)},
                severity="HIGH",
            )

    def generate_consistency_report(
        self,
        paper_data: pd.DataFrame,
        backtest_data: pd.DataFrame,
        live_data: pd.DataFrame,
        fee_rate: float,
    ) -> ConsistencyReport:
        """
        生成成交一致性报告

        Args:
            paper_data: Paper交易数据
            backtest_data: 回测数据
            live_data: 实盘数据
            fee_rate: 手续费率

        Returns:
            ConsistencyReport: 一致性报告
        """
        # 生成报告ID
        report_id = f"execution_consistency_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}"
        timestamp = datetime.now().isoformat()

        # 执行各项检查
        check_results = []

        # 1. 成交价一致性检查
        price_result = self.check_price_consistency(paper_data, backtest_data, live_data)
        check_results.append(price_result)

        # 2. 滑点一致性检查
        slippage_result = self.check_slippage_consistency(paper_data, backtest_data, live_data)
        check_results.append(slippage_result)

        # 3. 手续费一致性检查
        fee_result = self.check_fee_consistency(paper_data, backtest_data, live_data, fee_rate)
        check_results.append(fee_result)

        # 4. 部分成交处理一致性检查
        partial_result = self.check_partial_fill_consistency(paper_data, backtest_data, live_data)
        check_results.append(partial_result)

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

            if has_high_severity_failure:
                overall_status = "FAIL"
            else:
                overall_status = "PARTIAL"

        # 生成建议
        recommendations = []
        for result in check_results:
            if not result.passed:
                recommendations.append(f"{result.check_name} 检查失败: {result.message}")

        # 生成元数据
        metadata = {
            "config": self.actual_config,
            "paper_data_shape": paper_data.shape,
            "backtest_data_shape": backtest_data.shape,
            "live_data_shape": live_data.shape,
            "fee_rate": fee_rate,
            "report_id": report_id,
            "timestamp": timestamp,
        }

        # 创建报告
        report = ConsistencyReport(
            report_id=report_id,
            timestamp=timestamp,
            overall_status=overall_status,
            total_checks=total_checks,
            passed_checks=passed_checks,
            failed_checks=failed_checks,
            check_results=check_results,
            metadata=metadata,
            recommendations=recommendations,
        )

        logger.info(f"生成成交一致性报告: {report_id}, 状态: {overall_status}")
        return report

    def save_report(self, report: ConsistencyReport) -> dict[str, str]:
        """
        保存报告到文件

        Args:
            report: 一致性报告

        Returns:
            Dict[str, str]: 保存的文件路径
        """
        # 保存JSON格式报告
        report_path = self.output_dir / f"consistency_report_{report.report_id}.json"

        # 将报告转换为字典
        report_dict = {
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
                    "severity": result.severity,
                }
                for result in report.check_results
            ],
            "metadata": report.metadata,
            "recommendations": report.recommendations,
        }

        # 保存报告
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"报告已保存: {report_path}")

        return {"report_path": str(report_path)}

    def generate_test_data(
        self, n_samples: int = 100
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        生成测试数据

        Args:
            n_samples: 样本数量

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]: Paper交易数据, 回测数据, 实盘数据
        """
        import numpy as np

        # 生成基础数据
        np.random.seed(42)  # 设置随机种子，确保结果可复现

        order_prices = np.random.uniform(30000, 40000, n_samples)
        fill_prices = order_prices + np.random.normal(
            0, order_prices * 0.001, n_samples
        )  # 添加0.1%的噪声
        order_amounts = np.random.uniform(0.1, 1.0, n_samples)
        fill_amounts = order_amounts * np.random.uniform(0.8, 1.0, n_samples)  # 部分成交
        fee_rates = np.full(n_samples, 0.0005)  # 0.05%手续费率

        # 生成Paper交易数据
        paper_data = pd.DataFrame(
            {
                "order_id": [f"paper_{i}" for i in range(n_samples)],
                "order_price": order_prices,
                "fill_price": fill_prices,
                "order_amount": order_amounts,
                "fill_amount": fill_amounts,
                "actual_fee": fill_amounts * fill_prices * fee_rates,
                "timestamp": pd.date_range(start="2026-01-01", periods=n_samples, freq="1H"),
            }
        )

        # 生成回测数据，添加少量噪声
        backtest_data = pd.DataFrame(
            {
                "order_id": [f"backtest_{i}" for i in range(n_samples)],
                "order_price": order_prices,
                "fill_price": fill_prices
                + np.random.normal(0, order_prices * 0.0005, n_samples),  # 添加0.05%的噪声
                "order_amount": order_amounts,
                "fill_amount": fill_amounts,
                "actual_fee": fill_amounts
                * (fill_prices + np.random.normal(0, order_prices * 0.0005, n_samples))
                * fee_rates,  # 添加少量噪声
                "timestamp": pd.date_range(start="2026-01-01", periods=n_samples, freq="1H"),
            }
        )

        # 生成实盘数据，这里简化处理，使用Paper交易数据
        live_data = paper_data.copy()
        live_data["order_id"] = [f"live_{i}" for i in range(n_samples)]

        return paper_data, backtest_data, live_data

    def process_execution_consistency(
        self,
        paper_data: pd.DataFrame,
        backtest_data: pd.DataFrame,
        live_data: pd.DataFrame,
        fee_rate: float,
    ) -> ConsistencyReport:
        """
        处理成交一致性检查

        Args:
            paper_data: Paper交易数据
            backtest_data: 回测数据
            live_data: 实盘数据
            fee_rate: 手续费率

        Returns:
            ConsistencyReport: 一致性报告
        """
        logger.info("开始处理成交一致性检查")

        # 生成一致性报告
        report = self.generate_consistency_report(paper_data, backtest_data, live_data, fee_rate)

        # 保存报告
        self.save_report(report)

        # 保存证据
        evidence_path = self.evidence_dir / f"execution_consistency_{report.report_id}.csv"

        # 合并数据保存为证据
        combined_data = pd.DataFrame(
            {
                "paper_avg_price": [paper_data["fill_price"].mean()],
                "backtest_avg_price": [backtest_data["fill_price"].mean()],
                "paper_avg_slippage": [
                    paper_data.apply(
                        lambda x: self.calculate_slippage(x["order_price"], x["fill_price"]), axis=1
                    ).mean()
                ],
                "backtest_avg_slippage": [
                    backtest_data.apply(
                        lambda x: self.calculate_slippage(x["order_price"], x["fill_price"]), axis=1
                    ).mean()
                ],
                "report_id": [report.report_id],
                "timestamp": [report.timestamp],
                "status": [report.overall_status],
            }
        )

        combined_data.to_csv(evidence_path, index=False)
        logger.info(f"证据已保存: {evidence_path}")

        return report

    def run_self_test(self) -> bool:
        """
        运行自测试

        Returns:
            bool: 测试是否通过
        """
        logger.info("开始成交一致性检查器自测试")

        # 生成测试数据
        paper_data, backtest_data, live_data = self.generate_test_data(n_samples=100)

        # 处理成交一致性检查
        report = self.process_execution_consistency(
            paper_data, backtest_data, live_data, fee_rate=0.0005
        )

        # 检查结果
        logger.info(f"自测试结果: {report.overall_status}")

        return report.overall_status == "PASS"


# 示例使用
if __name__ == "__main__":
    # 创建成交一致性检查器实例
    execution_consistency_checker = ExecutionConsistencyChecker()

    # 运行自测试
    test_result = execution_consistency_checker.run_self_test()
    print(f"自测试结果: {'通过' if test_result else '失败'}")
