"""
因子准入控制模块
实现因子的准入规则验证
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import pearsonr

from .registry import DimensionTag, Factor


@dataclass
class AdmissionResult:
    """因子准入验证结果"""

    passed: bool
    message: str
    check_name: str
    details: dict | None = None


class FactorAdmissionController:
    """因子准入控制器，实现因子的准入规则验证"""

    def __init__(self):
        self.max_correlation_threshold = 0.8  # 最大允许相关性

    def validate_no_lookahead(self, factor: Factor, market_data: pd.DataFrame) -> AdmissionResult:
        """验证因子没有未来函数

        Args:
            factor: 待验证的因子
            market_data: 市场数据

        Returns:
            AdmissionResult: 验证结果
        """
        try:
            # 创建原始数据的随机截断版本
            original_length = len(market_data)
            truncation_point = np.random.randint(factor.metadata.lookback * 2, original_length - 1)

            # 在截断点前后分别计算因子值
            full_result = factor.compute(market_data)
            truncated_result = factor.compute(market_data.iloc[:truncation_point])

            # 检查结果长度
            if len(truncated_result) < factor.metadata.lookback:
                return AdmissionResult(
                    passed=True,
                    message="截断数据结果长度不足，无法验证未来函数",
                    check_name="no_lookahead",
                )

            if len(full_result) < factor.metadata.lookback:
                return AdmissionResult(
                    passed=True,
                    message="完整数据结果长度不足，无法验证未来函数",
                    check_name="no_lookahead",
                )

            # 计算有效比较范围
            # 对于截断数据，有效结果从lookback位置开始
            truncated_valid_start = factor.metadata.lookback
            truncated_valid_end = len(truncated_result)

            # 对于完整数据，对应截断数据的有效范围是[0:truncation_point]，
            # 但因子计算结果会从lookback位置开始，所以对应范围是[lookback:truncation_point]
            full_valid_start = factor.metadata.lookback
            full_valid_end = truncation_point

            # 确保完整数据的有效范围足够长
            if full_valid_end <= full_valid_start:
                return AdmissionResult(
                    passed=True,
                    message="完整数据有效范围不足，无法验证未来函数",
                    check_name="no_lookahead",
                )

            # 计算比较长度
            comparison_length = min(
                truncated_valid_end - truncated_valid_start, full_valid_end - full_valid_start
            )

            if comparison_length <= 0:
                return AdmissionResult(
                    passed=True, message="比较长度不足，无法验证未来函数", check_name="no_lookahead"
                )

            # 提取比较数据
            truncated_slice = truncated_result.iloc[-comparison_length:]
            full_slice = full_result.iloc[full_valid_end - comparison_length : full_valid_end]

            # 检查长度是否一致
            if len(truncated_slice) != len(full_slice):
                return AdmissionResult(
                    passed=True,
                    message="比较切片长度不一致，无法验证未来函数",
                    check_name="no_lookahead",
                )

            # 验证截断点之前的因子值一致性（允许一定的数值误差）
            are_close = np.allclose(truncated_slice, full_slice, rtol=1e-5, atol=1e-8)

            if are_close:
                return AdmissionResult(
                    passed=True, message="因子没有未来函数", check_name="no_lookahead"
                )
            else:
                return AdmissionResult(
                    passed=False,
                    message="因子存在未来函数，截断数据前后结果不一致",
                    check_name="no_lookahead",
                    details={
                        "truncation_point": truncation_point,
                        "original_length": original_length,
                        "comparison_length": comparison_length,
                        "truncated_slice_length": len(truncated_slice),
                        "full_slice_length": len(full_slice),
                    },
                )
        except Exception as e:
            return AdmissionResult(
                passed=False, message=f"验证未来函数时出错: {str(e)}", check_name="no_lookahead"
            )

    def validate_redundancy(
        self, factors: list[Factor], market_data: pd.DataFrame
    ) -> list[AdmissionResult]:
        """验证因子集的冗余性

        Args:
            factors: 待验证的因子列表
            market_data: 市场数据

        Returns:
            List[AdmissionResult]: 每个因子的验证结果
        """
        results = []

        if len(factors) < 2:
            return [
                AdmissionResult(
                    passed=True, message="因子数量不足，无法验证冗余性", check_name="redundancy"
                )
                for _ in factors
            ]

        try:
            # 计算所有因子的值
            factor_results = {}
            for factor in factors:
                factor_results[factor.metadata.name] = factor.compute(market_data)

            # 检查因子间的相关性
            factor_names = list(factor_results.keys())
            for i, factor_name in enumerate(factor_names):
                redundant_with = []
                for j, other_name in enumerate(factor_names):
                    if i >= j:
                        continue

                    # 计算相关性
                    corr, _ = pearsonr(
                        factor_results[factor_name].dropna(), factor_results[other_name].dropna()
                    )

                    if abs(corr) > self.max_correlation_threshold:
                        redundant_with.append({"factor_name": other_name, "correlation": corr})

                if redundant_with:
                    results.append(
                        AdmissionResult(
                            passed=False,
                            message="因子与其他因子存在冗余相关性",
                            check_name="redundancy",
                            details={
                                "redundant_factors": redundant_with,
                                "threshold": self.max_correlation_threshold,
                            },
                        )
                    )
                else:
                    results.append(
                        AdmissionResult(
                            passed=True, message="因子没有冗余相关性", check_name="redundancy"
                        )
                    )

            return results
        except Exception as e:
            return [
                AdmissionResult(
                    passed=False, message=f"验证冗余性时出错: {str(e)}", check_name="redundancy"
                )
                for _ in factors
            ]

    def validate_stability(
        self, factor: Factor, market_data: pd.DataFrame, time_slices: int = 5
    ) -> AdmissionResult:
        """验证因子的稳定性

        Args:
            factor: 待验证的因子
            market_data: 市场数据
            time_slices: 时间切片数量

        Returns:
            AdmissionResult: 验证结果
        """
        try:
            if len(market_data) < time_slices * factor.metadata.lookback:
                return AdmissionResult(
                    passed=True, message="数据长度不足，无法验证稳定性", check_name="stability"
                )

            # 将数据划分为多个时间切片
            slice_size = len(market_data) // time_slices
            slice_results = []

            for i in range(time_slices):
                start_idx = i * slice_size
                end_idx = (i + 1) * slice_size if i < time_slices - 1 else len(market_data)

                if end_idx - start_idx < factor.metadata.lookback:
                    continue

                slice_data = market_data.iloc[start_idx:end_idx]
                slice_result = factor.compute(slice_data)
                slice_results.append(slice_result)

            # 检查各切片结果的统计特性稳定性
            if len(slice_results) < 2:
                return AdmissionResult(
                    passed=True, message="有效切片数量不足，无法验证稳定性", check_name="stability"
                )

            # 计算各切片结果的均值和标准差
            stats = []
            for result in slice_results:
                if len(result) > 0:
                    stats.append({"mean": np.mean(result), "std": np.std(result)})

            # 检查统计特性的变异系数
            means = [s["mean"] for s in stats if abs(s["mean"]) > 1e-8]
            stds = [s["std"] for s in stats]

            if len(means) < 2:
                return AdmissionResult(
                    passed=True, message="均值接近零，无法计算变异系数", check_name="stability"
                )

            # 计算变异系数的变异系数
            cv = [s["std"] / abs(s["mean"]) for s in stats if abs(s["mean"]) > 1e-8]
            cv_of_cv = np.std(cv) / np.mean(cv) if np.mean(cv) > 1e-8 else 0

            # 如果变异系数的变异系数小于0.5，认为因子稳定
            if cv_of_cv < 0.5:
                return AdmissionResult(
                    passed=True,
                    message="因子稳定性良好",
                    check_name="stability",
                    details={"cv_of_cv": cv_of_cv},
                )
            else:
                return AdmissionResult(
                    passed=False,
                    message="因子稳定性较差，统计特性变化较大",
                    check_name="stability",
                    details={"cv_of_cv": cv_of_cv},
                )
        except Exception as e:
            return AdmissionResult(
                passed=False, message=f"验证稳定性时出错: {str(e)}", check_name="stability"
            )

    def validate_dimension_tag(self, factor: Factor) -> AdmissionResult:
        """验证因子的维度标签

        Args:
            factor: 待验证的因子

        Returns:
            AdmissionResult: 验证结果
        """
        required_tags = [DimensionTag.DIRECTION, DimensionTag.MAGNITUDE, DimensionTag.TIME]

        # 检查是否包含至少一个必需的维度标签
        has_required_tag = any(tag in factor.metadata.dimension_tags for tag in required_tags)

        if has_required_tag:
            return AdmissionResult(
                passed=True, message="因子维度标签验证通过", check_name="dimension_tag"
            )
        else:
            return AdmissionResult(
                passed=False,
                message=f"因子必须包含至少一个维度标签: {required_tags}",
                check_name="dimension_tag",
            )

    def validate_forbidden_imports(self, factor_module_path: str) -> AdmissionResult:
        """验证因子模块没有导入禁止的模块

        Args:
            factor_module_path: 因子模块的路径

        Returns:
            AdmissionResult: 验证结果
        """
        forbidden_imports = ["portfolio", "execution", "pnl"]

        try:
            with open(factor_module_path, encoding="utf-8") as f:
                content = f.read()

            # 检查是否包含禁止的导入
            for forbidden in forbidden_imports:
                # 检查import语句和from...import语句
                if f"import {forbidden}" in content or f"from {forbidden}" in content:
                    return AdmissionResult(
                        passed=False,
                        message=f"因子模块导入了禁止的模块: {forbidden}",
                        check_name="forbidden_imports",
                    )

            return AdmissionResult(
                passed=True, message="因子模块没有导入禁止的模块", check_name="forbidden_imports"
            )
        except Exception as e:
            return AdmissionResult(
                passed=False,
                message=f"验证禁止导入时出错: {str(e)}",
                check_name="forbidden_imports",
            )

    def run_full_admission(
        self, factor: Factor, market_data: pd.DataFrame, factor_module_path: str | None = None
    ) -> list[AdmissionResult]:
        """运行完整的因子准入验证流程

        Args:
            factor: 待验证的因子
            market_data: 市场数据
            factor_module_path: 因子模块的路径（用于验证禁止导入）

        Returns:
            List[AdmissionResult]: 所有验证结果
        """
        results = []

        # 1. 验证维度标签
        results.append(self.validate_dimension_tag(factor))

        # 2. 验证没有未来函数
        results.append(self.validate_no_lookahead(factor, market_data))

        # 3. 验证稳定性
        results.append(self.validate_stability(factor, market_data))

        # 4. 验证禁止导入
        if factor_module_path:
            results.append(self.validate_forbidden_imports(factor_module_path))

        return results
