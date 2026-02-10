import logging
from datetime import datetime

import pandas as pd
import statsmodels.api as sm
from sklearn.ensemble import RandomForestRegressor

from ..data.database_manager import DatabaseManager
from .factor_library import FactorLibrary

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FactorEvaluationSystem:
    """
    因子评价系统，用于测试单因子和多因子组合的有效性
    支持因子有效性测试、相关性分析、重要性评估等功能
    """

    def __init__(self, config=None):
        """
        初始化因子评价系统
        """
        self.config = config or {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "quant_trading",
                "user": "postgres",
                "password": "postgres",
            },
            "evaluation": {
                "lookback_period": 20,
                "confidence_level": 0.95,
                "correlation_threshold": 0.7,
            },
        }

        # 数据库管理器
        self.db_manager = DatabaseManager(self.config["database"])

        # 因子库
        self.factor_lib = FactorLibrary(self.config)

    def evaluate_single_factor(self, factor_code, symbol, timeframe, start_time, end_time):
        """
        单因子有效性测试
        """
        logger.info(f"开始单因子有效性测试: {factor_code} - {symbol} {timeframe}")

        # 获取交易数据
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
        if df.empty:
            logger.error(f"未找到交易数据: {symbol} {timeframe}")
            return None

        # 获取因子值
        factor_df = self.factor_lib.get_factor_values(
            factor_code, symbol, timeframe, start_time, end_time
        )
        if factor_df.empty:
            logger.error(f"未找到因子值: {factor_code} - {symbol} {timeframe}")
            return None

        # 合并数据
        merged_df = df.join(factor_df, how="inner")
        merged_df.rename(columns={"value": factor_code}, inplace=True)

        # 计算未来收益率（使用下一期的收益率作为预测目标）
        merged_df["future_return"] = merged_df["close"].pct_change(periods=1).shift(-1)

        # 去除NaN值
        merged_df.dropna(inplace=True)

        if len(merged_df) < 20:
            logger.error(f"数据量不足，无法进行因子评价: {len(merged_df)} 条")
            return None

        # 单因子有效性测试
        factor = merged_df[factor_code]
        future_returns = merged_df["future_return"]

        # 1. 线性回归分析
        X = sm.add_constant(factor)
        model = sm.OLS(future_returns, X).fit()
        alpha = model.params["const"]
        beta = model.params[factor_code]
        t_stat = model.tvalues[factor_code]
        p_value = model.pvalues[factor_code]
        r_squared = model.rsquared
        adjusted_r_squared = model.rsquared_adj

        # 2. 信息系数（IC）
        ic = factor.corr(future_returns, method="spearman")

        # 3. 分组测试
        n_groups = 5
        merged_df["group"] = pd.qcut(factor, n_groups, labels=False)
        group_returns = merged_df.groupby("group")["future_return"].mean()
        group_std = merged_df.groupby("group")["future_return"].std()
        group_count = merged_df.groupby("group")["future_return"].count()

        # 计算多空收益率（最高价组 - 最低价组）
        long_short_return = group_returns.iloc[-1] - group_returns.iloc[0]
        long_short_ic = group_returns.corr(pd.Series(range(n_groups)))

        # 4. 单调性测试（斯皮尔曼相关系数）
        monotonicity = group_returns.corr(pd.Series(range(n_groups)), method="spearman")

        # 5. 因子稳定性
        # 滚动IC
        rolling_ic = factor.rolling(window=self.config["evaluation"]["lookback_period"]).corr(
            future_returns, method="spearman"
        )
        avg_rolling_ic = rolling_ic.mean()
        ic_std = rolling_ic.std()
        ic_ir = avg_rolling_ic / ic_std if ic_std != 0 else 0

        # 6. 因子分布统计
        factor_stats = {
            "mean": factor.mean(),
            "std": factor.std(),
            "skew": factor.skew(),
            "kurtosis": factor.kurtosis(),
            "min": factor.min(),
            "max": factor.max(),
            "p10": factor.quantile(0.1),
            "p50": factor.median(),
            "p90": factor.quantile(0.9),
        }

        # 整合评价结果
        evaluation_result = {
            "factor_code": factor_code,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_time": start_time.strftime("%Y-%m-%d"),
            "end_time": end_time.strftime("%Y-%m-%d"),
            "sample_size": len(merged_df),
            "linear_regression": {
                "alpha": alpha,
                "beta": beta,
                "t_stat": t_stat,
                "p_value": p_value,
                "r_squared": r_squared,
                "adjusted_r_squared": adjusted_r_squared,
            },
            "information_coefficient": {
                "ic": ic,
                "avg_rolling_ic": avg_rolling_ic,
                "ic_std": ic_std,
                "ic_ir": ic_ir,
            },
            "group_test": {
                "n_groups": n_groups,
                "group_returns": group_returns.to_dict(),
                "group_std": group_std.to_dict(),
                "group_count": group_count.to_dict(),
                "long_short_return": long_short_return,
                "long_short_ic": long_short_ic,
            },
            "monotonicity": monotonicity,
            "factor_stats": factor_stats,
            "is_significant": p_value < (1 - self.config["evaluation"]["confidence_level"]),
        }

        logger.info(f"单因子有效性测试完成: {factor_code} - {symbol} {timeframe}")
        logger.info(f"因子IC: {ic:.4f}, 显著性: {evaluation_result['is_significant']}")

        return evaluation_result

    def evaluate_factor_combination(self, factor_codes, symbol, timeframe, start_time, end_time):
        """
        多因子组合有效性测试
        """
        logger.info(f"开始多因子组合有效性测试: {factor_codes} - {symbol} {timeframe}")

        # 获取交易数据
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
        if df.empty:
            logger.error(f"未找到交易数据: {symbol} {timeframe}")
            return None

        # 合并所有因子值
        merged_df = df.copy()
        for factor_code in factor_codes:
            factor_df = self.factor_lib.get_factor_values(
                factor_code, symbol, timeframe, start_time, end_time
            )
            if factor_df.empty:
                logger.error(f"未找到因子值: {factor_code} - {symbol} {timeframe}")
                return None
            merged_df = merged_df.join(factor_df, how="inner")
            merged_df.rename(columns={"value": factor_code}, inplace=True)

        # 计算未来收益率
        merged_df["future_return"] = merged_df["close"].pct_change(periods=1).shift(-1)

        # 去除NaN值
        merged_df.dropna(inplace=True)

        if len(merged_df) < 20:
            logger.error(f"数据量不足，无法进行因子组合评价: {len(merged_df)} 条")
            return None

        # 准备特征和目标变量
        X = merged_df[factor_codes]
        y = merged_df["future_return"]

        # 1. 多元线性回归
        X_linear = sm.add_constant(X)
        linear_model = sm.OLS(y, X_linear).fit()
        linear_r_squared = linear_model.rsquared
        linear_adjusted_r_squared = linear_model.rsquared_adj
        linear_p_values = linear_model.pvalues.to_dict()
        linear_coefficients = linear_model.params.to_dict()

        # 2. 随机森林回归（用于特征重要性）
        rf_model = RandomForestRegressor(n_estimators=100, random_state=42)
        rf_model.fit(X, y)
        feature_importance = dict(zip(factor_codes, rf_model.feature_importances_))

        # 3. 计算组合因子IC
        # 创建等权组合因子
        combined_factor = X.mean(axis=1)
        combined_ic = combined_factor.corr(y, method="spearman")

        # 4. 因子相关性分析
        correlation_matrix = X.corr(method="spearman")

        # 5. 因子冗余性分析
        redundant_pairs = []
        for i in range(len(factor_codes)):
            for j in range(i + 1, len(factor_codes)):
                corr = correlation_matrix.iloc[i, j]
                if abs(corr) > self.config["evaluation"]["correlation_threshold"]:
                    redundant_pairs.append(
                        {
                            "factor1": factor_codes[i],
                            "factor2": factor_codes[j],
                            "correlation": corr,
                        }
                    )

        # 6. 信息系数（IC）矩阵
        ic_matrix = pd.DataFrame(index=factor_codes, columns=["IC"])
        for factor_code in factor_codes:
            ic_matrix.loc[factor_code, "IC"] = X[factor_code].corr(y, method="spearman")

        # 7. 分组测试（使用组合因子）
        n_groups = 5
        merged_df["combined_factor"] = combined_factor
        merged_df["group"] = pd.qcut(combined_factor, n_groups, labels=False)
        group_returns = merged_df.groupby("group")["future_return"].mean()
        group_std = merged_df.groupby("group")["future_return"].std()
        long_short_return = group_returns.iloc[-1] - group_returns.iloc[0]
        monotonicity = group_returns.corr(pd.Series(range(n_groups)), method="spearman")

        # 整合评价结果
        evaluation_result = {
            "factor_codes": factor_codes,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_time": start_time.strftime("%Y-%m-%d"),
            "end_time": end_time.strftime("%Y-%m-%d"),
            "sample_size": len(merged_df),
            "linear_regression": {
                "r_squared": linear_r_squared,
                "adjusted_r_squared": linear_adjusted_r_squared,
                "p_values": linear_p_values,
                "coefficients": linear_coefficients,
            },
            "random_forest": {"feature_importance": feature_importance},
            "combined_factor": {
                "ic": combined_ic,
                "group_test": {
                    "group_returns": group_returns.to_dict(),
                    "long_short_return": long_short_return,
                    "monotonicity": monotonicity,
                },
            },
            "correlation": {
                "matrix": correlation_matrix.to_dict(),
                "redundant_pairs": redundant_pairs,
            },
            "ic_matrix": ic_matrix.to_dict(),
        }

        logger.info(f"多因子组合有效性测试完成: {factor_codes} - {symbol} {timeframe}")
        logger.info(f"组合因子IC: {combined_ic:.4f}, R²: {linear_r_squared:.4f}")

        return evaluation_result

    def calculate_factor_correlation(self, factor_codes, symbol, timeframe, start_time, end_time):
        """
        计算因子之间的相关性
        """
        logger.info(f"开始计算因子相关性: {factor_codes} - {symbol} {timeframe}")

        # 获取交易数据
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
        if df.empty:
            logger.error(f"未找到交易数据: {symbol} {timeframe}")
            return None

        # 合并所有因子值
        merged_df = df.copy()
        for factor_code in factor_codes:
            factor_df = self.factor_lib.get_factor_values(
                factor_code, symbol, timeframe, start_time, end_time
            )
            if factor_df.empty:
                logger.error(f"未找到因子值: {factor_code} - {symbol} {timeframe}")
                return None
            merged_df = merged_df.join(factor_df, how="inner")
            merged_df.rename(columns={"value": factor_code}, inplace=True)

        # 去除NaN值
        merged_df.dropna(inplace=True)

        if len(merged_df) < 20:
            logger.error(f"数据量不足，无法计算相关性: {len(merged_df)} 条")
            return None

        # 计算相关性矩阵
        correlation_pearson = merged_df[factor_codes].corr(method="pearson")
        correlation_spearman = merged_df[factor_codes].corr(method="spearman")

        # 整合结果
        correlation_result = {
            "factor_codes": factor_codes,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_time": start_time.strftime("%Y-%m-%d"),
            "end_time": end_time.strftime("%Y-%m-%d"),
            "sample_size": len(merged_df),
            "pearson": correlation_pearson.to_dict(),
            "spearman": correlation_spearman.to_dict(),
        }

        logger.info(f"因子相关性计算完成: {factor_codes} - {symbol} {timeframe}")

        return correlation_result

    def evaluate_all_factors(self, factor_codes, symbols, timeframes, start_time, end_time):
        """
        批量评价所有因子
        """
        logger.info(f"开始批量评价因子: {factor_codes}")

        results = {
            "single_factor_results": [],
            "correlation_results": [],
            "combination_results": [],
        }

        # 1. 单因子评价
        for symbol in symbols:
            for timeframe in timeframes:
                for factor_code in factor_codes:
                    single_result = self.evaluate_single_factor(
                        factor_code, symbol, timeframe, start_time, end_time
                    )
                    if single_result:
                        results["single_factor_results"].append(single_result)

        # 2. 因子相关性分析
        for symbol in symbols:
            for timeframe in timeframes:
                correlation_result = self.calculate_factor_correlation(
                    factor_codes, symbol, timeframe, start_time, end_time
                )
                if correlation_result:
                    results["correlation_results"].append(correlation_result)

        # 3. 多因子组合评价
        for symbol in symbols:
            for timeframe in timeframes:
                combination_result = self.evaluate_factor_combination(
                    factor_codes, symbol, timeframe, start_time, end_time
                )
                if combination_result:
                    results["combination_results"].append(combination_result)

        logger.info(
            f"因子批量评价完成，共评价 {len(results['single_factor_results'])} 个单因子实例"
        )

        return results

    def get_factor_ranking(self, symbol, timeframe, start_time, end_time, top_n=10):
        """
        获取因子排名
        """
        logger.info(f"开始获取因子排名: {symbol} {timeframe}")

        # 获取所有因子
        all_factors = self.factor_lib.list_factors()

        # 评价所有因子
        rankings = []
        for factor_code in all_factors:
            result = self.evaluate_single_factor(
                factor_code, symbol, timeframe, start_time, end_time
            )
            if result:
                rankings.append(
                    {
                        "factor_code": factor_code,
                        "ic": result["information_coefficient"]["ic"],
                        "t_stat": result["linear_regression"]["t_stat"],
                        "p_value": result["linear_regression"]["p_value"],
                        "r_squared": result["linear_regression"]["r_squared"],
                        "is_significant": result["is_significant"],
                    }
                )

        # 按IC排序
        rankings.sort(key=lambda x: abs(x["ic"]), reverse=True)

        # 取前N个因子
        top_factors = rankings[:top_n]

        logger.info(f"因子排名完成，前 {top_n} 个因子已选出")

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_time": start_time.strftime("%Y-%m-%d"),
            "end_time": end_time.strftime("%Y-%m-%d"),
            "total_factors": len(rankings),
            "top_factors": top_factors,
        }

    def analyze_factor_stability(
        self, factor_code, symbol, timeframe, start_time, end_time, rolling_window=60
    ):
        """
        分析因子稳定性
        """
        logger.info(f"开始分析因子稳定性: {factor_code} - {symbol} {timeframe}")

        # 获取交易数据
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
        if df.empty:
            logger.error(f"未找到交易数据: {symbol} {timeframe}")
            return None

        # 获取因子值
        factor_df = self.factor_lib.get_factor_values(
            factor_code, symbol, timeframe, start_time, end_time
        )
        if factor_df.empty:
            logger.error(f"未找到因子值: {factor_code} - {symbol} {timeframe}")
            return None

        # 合并数据
        merged_df = df.join(factor_df, how="inner")
        merged_df.rename(columns={"value": factor_code}, inplace=True)

        # 计算未来收益率
        merged_df["future_return"] = merged_df["close"].pct_change(periods=1).shift(-1)

        # 去除NaN值
        merged_df.dropna(inplace=True)

        if len(merged_df) < rolling_window:
            logger.error(f"数据量不足，无法分析因子稳定性: {len(merged_df)} 条")
            return None

        # 计算滚动统计指标
        factor = merged_df[factor_code]
        future_returns = merged_df["future_return"]

        # 滚动IC
        rolling_ic = factor.rolling(window=rolling_window).corr(future_returns, method="spearman")

        # 滚动均值
        rolling_mean = factor.rolling(window=rolling_window).mean()

        # 滚动标准差
        rolling_std = factor.rolling(window=rolling_window).std()

        # 滚动分位数
        rolling_q1 = factor.rolling(window=rolling_window).quantile(0.25)
        rolling_q3 = factor.rolling(window=rolling_window).quantile(0.75)

        # 整合结果
        stability_result = {
            "factor_code": factor_code,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_time": start_time.strftime("%Y-%m-%d"),
            "end_time": end_time.strftime("%Y-%m-%d"),
            "rolling_window": rolling_window,
            "sample_size": len(merged_df),
            "rolling_ic": {
                "mean": rolling_ic.mean(),
                "std": rolling_ic.std(),
                "min": rolling_ic.min(),
                "max": rolling_ic.max(),
                "positive_ratio": (rolling_ic > 0).mean(),
                "significant_ratio": (abs(rolling_ic) > 0.1).mean(),
            },
            "factor_stability": {
                "mean_mean": rolling_mean.mean(),
                "mean_std": rolling_mean.std(),
                "std_mean": rolling_std.mean(),
                "std_std": rolling_std.std(),
                "q1_mean": rolling_q1.mean(),
                "q3_mean": rolling_q3.mean(),
            },
        }

        logger.info(f"因子稳定性分析完成: {factor_code} - {symbol} {timeframe}")

        return stability_result

    def close(self):
        """
        关闭数据库连接
        """
        self.factor_lib.close()
        self.db_manager.disconnect()


# 示例使用
if __name__ == "__main__":
    # 创建因子评价系统实例
    evaluation_system = FactorEvaluationSystem()

    try:
        # 示例：单因子评价
        factor_code = "ma"
        symbol = "ETH-USDT"
        timeframe = "1h"
        start_time = datetime(2025, 1, 1)
        end_time = datetime(2025, 6, 1)

        result = evaluation_system.evaluate_single_factor(
            factor_code, symbol, timeframe, start_time, end_time
        )
        if result:
            logger.info(f"单因子评价结果: {result}")

        # 示例：因子相关性分析
        factor_codes = ["ma", "rsi", "macd", "volatility", "momentum"]
        corr_result = evaluation_system.calculate_factor_correlation(
            factor_codes, symbol, timeframe, start_time, end_time
        )
        if corr_result:
            logger.info(f"因子相关性分析结果: {corr_result}")

        # 示例：因子组合评价
        combo_result = evaluation_system.evaluate_factor_combination(
            factor_codes, symbol, timeframe, start_time, end_time
        )
        if combo_result:
            logger.info(f"因子组合评价结果: {combo_result}")

    except Exception as e:
        logger.error(f"因子评价失败: {e}")
    finally:
        # 关闭连接
        evaluation_system.close()
