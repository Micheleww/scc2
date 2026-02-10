#!/usr/bin/env python3
"""
自动因子生成模块
通过算子组合和随机搜索生成新因子
"""

import logging
import random
from collections.abc import Callable

import numpy as np
import pandas as pd
from ..data.database_manager import DatabaseManager
from tqdm import tqdm

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AutoFactorGenerator:
    """
    自动因子生成器
    通过算子组合和随机搜索生成新因子
    """

    def __init__(
        self, base_features: pd.DataFrame, symbol: str = "ETH/USDT", timeframe: str = "1h"
    ):
        """
        初始化自动因子生成器

        Args:
            base_features: 基础特征矩阵
            symbol: 交易对
            timeframe: 时间周期
        """
        self.base_features = base_features
        self.symbol = symbol
        self.timeframe = timeframe
        self.generated_factors = pd.DataFrame()
        self.factor_scores = {}  # 存储因子得分

        # 定义基础变量
        self.base_vars = self._define_base_vars()

        # 定义算子
        self.unary_ops = self._define_unary_ops()
        self.binary_ops = self._define_binary_ops()

        # 初始化数据库管理器
        self.db_manager = DatabaseManager()

        logger.info(
            f"自动因子生成器初始化完成，基础变量数量: {len(self.base_vars)}, 一元算子数量: {len(self.unary_ops)}, 二元算子数量: {len(self.binary_ops)}"
        )

    def _define_base_vars(self) -> list[str]:
        """
        定义基础变量

        Returns:
            base_vars: 基础变量列表
        """
        # 从基础特征中选择可用的变量
        return list(self.base_features.columns)

    def _define_unary_ops(self) -> dict[str, Callable]:
        """
        定义一元算子

        Returns:
            unary_ops: 一元算子字典，键为算子名称，值为算子函数
        """
        return {
            "log": lambda x: np.log(x),
            "abs": lambda x: np.abs(x),
            "sqrt": lambda x: np.sqrt(x),
            "rank": lambda x: x.rank(pct=True),
            "zscore": lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0,
            "rolling_mean_12h": lambda x: x.rolling(window=12).mean(),
            "rolling_mean_24h": lambda x: x.rolling(window=24).mean(),
            "rolling_std_12h": lambda x: x.rolling(window=12).std(),
            "rolling_std_48h": lambda x: x.rolling(window=48).std(),
            "rolling_max_12h": lambda x: x.rolling(window=12).max(),
            "rolling_min_12h": lambda x: x.rolling(window=12).min(),
            "rolling_sum_12h": lambda x: x.rolling(window=12).sum(),
        }

    def _define_binary_ops(self) -> dict[str, Callable]:
        """
        定义二元算子

        Returns:
            binary_ops: 二元算子字典，键为算子名称，值为算子函数
        """
        return {
            "+": lambda x, y: x + y,
            "-": lambda x, y: x - y,
            "*": lambda x, y: x * y,
            "/": lambda x, y: x / (y + 1e-8),  # 避免除以零
            "max": lambda x, y: np.maximum(x, y),
            "min": lambda x, y: np.minimum(x, y),
        }

    def generate_factor_expressions(self, n_factors: int = 100) -> list[str]:
        """
        生成因子表达式

        Args:
            n_factors: 生成因子的数量

        Returns:
            factor_expressions: 因子表达式列表
        """
        logger.info(f"开始生成 {n_factors} 个因子表达式")

        factor_expressions = []

        logger.info("生成因子表达式...")
        for i in tqdm(range(n_factors), desc="生成因子表达式", total=n_factors):
            # 随机选择因子生成方式
            expr_type = random.choice(["unary", "binary"])

            if expr_type == "unary":
                # 一元算子表达式: op(var)
                var = random.choice(self.base_vars)
                op = random.choice(list(self.unary_ops.keys()))
                expr = f"{op}({var})"
            else:
                # 二元算子表达式：分为特殊运算符（+、-、*、/）和普通二元函数（max、min）
                expr_depth = random.choice(["shallow", "deep"])

                # 选择二元算子
                op = random.choice(list(self.binary_ops.keys()))

                if expr_depth == "shallow":
                    # 浅层表达式
                    var1 = random.choice(self.base_vars)
                    var2 = random.choice(self.base_vars)

                    if op in ["+", "-", "*", "/"]:
                        # 特殊运算符：使用中缀表达式 (var1 op var2)
                        expr = f"({var1} {op} {var2})"
                    else:
                        # 普通二元函数：使用函数调用 op(var1, var2)
                        expr = f"{op}({var1}, {var2})"
                else:
                    # 深层表达式
                    var1 = random.choice(self.base_vars)
                    op1 = random.choice(list(self.unary_ops.keys()))
                    var2 = random.choice(self.base_vars)
                    op2 = random.choice(list(self.unary_ops.keys()))

                    if op in ["+", "-", "*", "/"]:
                        # 特殊运算符：使用中缀表达式 (op1(var1) op op2(var2))
                        expr = f"({op1}({var1}) {op} {op2}({var2}))"
                    else:
                        # 普通二元函数：使用函数调用 op(op1(var1), op2(var2))
                        expr = f"{op}({op1}({var1}), {op2}({var2}))"

            factor_expressions.append(expr)

        logger.info(f"因子表达式生成完成，共生成 {len(factor_expressions)} 个表达式")
        return factor_expressions

    def evaluate_factor_expression(self, expr: str) -> pd.Series:
        """
        计算因子表达式的值

        Args:
            expr: 因子表达式

        Returns:
            factor_values: 因子值序列
        """
        try:
            # 构建评估环境
            eval_env = {"np": np, "pd": pd}

            # 添加基础变量到评估环境
            for var in self.base_vars:
                eval_env[var] = self.base_features[var]

            # 添加一元算子到评估环境
            for op_name, op_func in self.unary_ops.items():
                eval_env[op_name] = op_func

            # 添加二元算子到评估环境
            for op_name, op_func in self.binary_ops.items():
                eval_env[op_name] = op_func

            # 评估表达式
            factor_values = eval(expr, eval_env)

            # 确保返回值是Series
            if isinstance(factor_values, pd.Series):
                return factor_values
            else:
                return pd.Series(factor_values, index=self.base_features.index)

        except Exception as e:
            logger.error(f"评估因子表达式失败: {expr}, 错误: {e}")
            return pd.Series(np.nan, index=self.base_features.index)

    def calculate_factor_ic(self, factor_values: pd.Series, labels: pd.Series) -> float:
        """
        计算因子的信息系数(IC)

        Args:
            factor_values: 因子值序列
            labels: 标签序列（未来收益率）

        Returns:
            ic: 信息系数
        """
        # 确保索引一致
        common_index = factor_values.index.intersection(labels.index)
        factor_values = factor_values.loc[common_index]
        labels = labels.loc[common_index]

        # 计算Spearman相关系数
        try:
            ic = factor_values.corr(labels, method="spearman")
            return ic if not np.isnan(ic) else 0
        except Exception as e:
            logger.error(f"计算IC失败: {e}")
            return 0

    def generate_factors(self, n_factors: int = 100, labels: pd.Series = None) -> pd.DataFrame:
        """
        生成因子

        Args:
            n_factors: 生成因子的数量
            labels: 标签序列，用于计算IC得分

        Returns:
            generated_factors: 生成的因子矩阵
        """
        logger.info(f"开始生成 {n_factors} 个因子")

        # 生成因子表达式
        factor_expressions = self.generate_factor_expressions(n_factors)

        # 计算因子值
        generated_factors = pd.DataFrame()
        self.factor_scores = {}

        logger.info("计算因子值...")
        for i, expr in tqdm(
            enumerate(factor_expressions), desc="计算因子", total=len(factor_expressions)
        ):
            factor_name = f"factor_{i + 1}"
            # logger.info(f"计算因子 {factor_name}: {expr}")

            # 计算因子值
            factor_values = self.evaluate_factor_expression(expr)
            generated_factors[factor_name] = factor_values

            # 计算因子得分
            if labels is not None:
                ic = self.calculate_factor_ic(factor_values, labels)
                self.factor_scores[factor_name] = {"expression": expr, "ic": ic, "abs_ic": abs(ic)}
                # 每10个因子打印一次IC值
                if (i + 1) % 10 == 0 or i == len(factor_expressions) - 1:
                    logger.info(f"因子 {factor_name} 的IC: {ic:.4f}")

            # 将因子保存到因子库
            try:
                # 插入因子信息到factors表
                factor_id = self.db_manager.insert_factor(
                    name=factor_name,
                    description=f"自动生成因子: {expr}",
                    type="ai_ml",  # AI/ML因子类型
                    calculation_method=expr,
                )

                # 保存因子值到factor_values表
                for timestamp, value in factor_values.items():
                    if not pd.isna(value):
                        self.db_manager.insert_factor_value(
                            timestamp=timestamp,
                            symbol=self.symbol,
                            timeframe=self.timeframe,
                            factor_id=factor_id,
                            value=value,
                        )

                logger.info(f"因子 {factor_name} 已保存到因子库")
            except Exception as e:
                logger.error(f"保存因子 {factor_name} 到因子库失败: {e}")

        logger.info(f"因子生成完成，共生成 {len(generated_factors.columns)} 个因子")

        self.generated_factors = generated_factors
        return generated_factors

    def filter_factors(self, min_abs_ic: float = 0.01, max_corr: float = 0.8) -> pd.DataFrame:
        """
        过滤因子

        Args:
            min_abs_ic: 最小绝对IC值
            max_corr: 最大相关性

        Returns:
            filtered_factors: 过滤后的因子矩阵
        """
        if not self.factor_scores:
            logger.error("没有因子得分，无法过滤因子")
            return self.generated_factors

        logger.info(f"开始过滤因子，最小绝对IC: {min_abs_ic}, 最大相关性: {max_corr}")

        # 1. 按IC值过滤
        high_ic_factors = [
            factor for factor, score in self.factor_scores.items() if abs(score["ic"]) >= min_abs_ic
        ]

        if not high_ic_factors:
            logger.warning("没有满足IC条件的因子")
            return self.generated_factors

        # 2. 按相关性过滤
        filtered_factors = []
        for factor in high_ic_factors:
            # 检查与已选因子的相关性
            if not filtered_factors:
                filtered_factors.append(factor)
            else:
                # 计算与所有已选因子的相关性
                corr_matrix = self.generated_factors[[factor] + filtered_factors].corr()
                max_correlation = corr_matrix.loc[factor, filtered_factors].abs().max()

                if max_correlation <= max_corr:
                    filtered_factors.append(factor)

        logger.info(
            f"因子过滤完成，从 {len(high_ic_factors)} 个高IC因子中选择了 {len(filtered_factors)} 个低相关性因子"
        )

        # 返回过滤后的因子
        return self.generated_factors[filtered_factors]

    def get_factor_scores(self) -> dict[str, dict[str, float]]:
        """
        获取因子得分

        Returns:
            factor_scores: 因子得分字典
        """
        return self.factor_scores

    def get_generated_factors(self) -> pd.DataFrame:
        """
        获取生成的因子

        Returns:
            generated_factors: 生成的因子矩阵
        """
        return self.generated_factors

    def generate_best_factors(
        self,
        n_factors: int = 100,
        n_best: int = 20,
        min_abs_ic: float = 0.01,
        max_corr: float = 0.8,
        labels: pd.Series = None,
    ) -> pd.DataFrame:
        """
        生成并选择最佳因子

        Args:
            n_factors: 生成因子的数量
            n_best: 选择最佳因子的数量
            min_abs_ic: 最小绝对IC值
            max_corr: 最大相关性
            labels: 标签序列，用于计算IC得分

        Returns:
            best_factors: 最佳因子矩阵
        """
        logger.info(f"开始生成并选择最佳因子，生成数量: {n_factors}, 选择数量: {n_best}")

        # 生成因子
        self.generate_factors(n_factors, labels)

        # 过滤因子
        filtered_factors = self.filter_factors(min_abs_ic, max_corr)

        # 选择得分最高的n_best个因子
        if labels is not None:
            # 计算每个因子的IC值
            ic_scores = {
                factor: abs(self.calculate_factor_ic(filtered_factors[factor], labels))
                for factor in filtered_factors.columns
            }

            # 按IC值降序排序
            sorted_factors = sorted(ic_scores.items(), key=lambda x: x[1], reverse=True)

            # 选择前n_best个因子
            best_factor_names = [factor for factor, score in sorted_factors[:n_best]]
            best_factors = filtered_factors[best_factor_names]
        else:
            # 如果没有标签，返回所有过滤后的因子
            best_factors = filtered_factors

        logger.info(f"最佳因子选择完成，共选择 {len(best_factors.columns)} 个因子")

        return best_factors
