#!/usr/bin/env python3
"""
因子优化和组合模块
实现多因子策略的组合和优化
"""

import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, r2_score
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from tqdm import tqdm

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FactorOptimizer:
    """
    因子优化器
    实现多因子策略的组合和优化
    """

    def __init__(self):
        """
        初始化因子优化器
        """
        self.model = None
        self.scaler = None
        self.feature_importance = None
        self.model_type = None

        logger.info("因子优化器初始化完成")

    def train_model(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        model_type: str = "ridge",
        params: dict[str, Any] = None,
    ) -> Any:
        """
        训练因子组合模型

        Args:
            X_train: 训练集因子矩阵
            y_train: 训练集标签
            model_type: 模型类型，目前只支持 'ridge'
            params: 模型参数

        Returns:
            model: 训练好的模型
        """
        # 检查因子矩阵中是否包含不可用数据（NaN）
        if X_train.isna().any().any():
            logger.error("因子矩阵中包含不可用数据（NaN），模型训练将被阻断")
            raise ValueError("因子矩阵中包含不可用数据（NaN），模型训练将被阻断")

        # 检查标签中是否包含不可用数据（NaN）
        if y_train.isna().any():
            logger.error("标签中包含不可用数据（NaN），模型训练将被阻断")
            raise ValueError("标签中包含不可用数据（NaN），模型训练将被阻断")

        # 根据用户要求，只使用ridge模型
        model_type = "ridge"
        logger.info(f"开始训练 {model_type} 模型")

        # 设置默认参数
        params = params or {}

        # 初始化模型
        self.model = Ridge(**params)

        # 记录模型类型
        self.model_type = model_type

        # 标准化特征
        self.scaler = StandardScaler()
        X_train_scaled = self.scaler.fit_transform(X_train)

        # 训练模型
        self.model.fit(X_train_scaled, y_train)

        # 计算特征重要性
        self._calculate_feature_importance(X_train.columns)

        logger.info("模型训练完成")

        return self.model

    def _calculate_feature_importance(self, feature_names: list[str]):
        """
        计算特征重要性

        Args:
            feature_names: 特征名称列表
        """
        if hasattr(self.model, "feature_importances_"):
            # 树模型的特征重要性
            self.feature_importance = pd.Series(
                self.model.feature_importances_, index=feature_names
            ).sort_values(ascending=False)
        elif hasattr(self.model, "coef_"):
            # 线性模型的系数
            self.feature_importance = pd.Series(
                np.abs(self.model.coef_), index=feature_names
            ).sort_values(ascending=False)
        else:
            # 其他模型，使用默认重要性
            self.feature_importance = pd.Series(np.ones(len(feature_names)), index=feature_names)

        logger.info("特征重要性计算完成")

    def predict(self, X: pd.DataFrame) -> pd.Series:
        """
        使用训练好的模型进行预测

        Args:
            X: 因子矩阵

        Returns:
            predictions: 预测结果
        """
        if self.model is None:
            raise ValueError("模型未训练")

        # 检查因子矩阵中是否包含不可用数据（NaN）
        if X.isna().any().any():
            logger.error("因子矩阵中包含不可用数据（NaN），预测将被阻断")
            raise ValueError("因子矩阵中包含不可用数据（NaN），预测将被阻断")

        # 标准化特征
        X_scaled = self.scaler.transform(X)

        # 预测
        predictions = self.model.predict(X_scaled)

        # 转换为Series
        return pd.Series(predictions, index=X.index)

    def evaluate_model(self, X_test: pd.DataFrame, y_test: pd.Series) -> dict[str, float]:
        """
        评估模型性能

        Args:
            X_test: 测试集因子矩阵
            y_test: 测试集标签

        Returns:
            metrics: 模型性能指标
        """
        if self.model is None:
            raise ValueError("模型未训练")

        logger.info("开始评估模型性能")

        # 预测
        predictions = self.predict(X_test)

        # 计算性能指标
        mse = mean_squared_error(y_test, predictions)
        rmse = np.sqrt(mse)
        r2 = r2_score(y_test, predictions)

        # 计算IC（信息系数）
        ic = predictions.corr(y_test, method="spearman")

        metrics = {"mse": mse, "rmse": rmse, "r2": r2, "ic": ic}

        logger.info(f"模型评估完成，MSE: {mse:.4f}, RMSE: {rmse:.4f}, R²: {r2:.4f}, IC: {ic:.4f}")

        return metrics

    def cross_validate(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        model_type: str = "ridge",
        params: dict[str, Any] = None,
        n_splits: int = 5,
    ) -> dict[str, float]:
        """
        交叉验证模型

        Args:
            X: 因子矩阵
            y: 标签
            model_type: 模型类型，目前只支持 'ridge'
            params: 模型参数
            n_splits: 交叉验证折数

        Returns:
            cv_metrics: 交叉验证结果
        """
        # 根据用户要求，只使用ridge模型
        model_type = "ridge"
        logger.info(f"开始交叉验证 {model_type} 模型")

        # 设置默认参数
        params = params or {}

        # 初始化模型
        model = Ridge(**params)

        # 时间序列交叉验证
        tscv = TimeSeriesSplit(n_splits=n_splits)

        # 标准化特征
        scaler = StandardScaler()

        # 存储各折的指标
        mse_scores = []
        r2_scores = []
        ic_scores = []

        # 使用tqdm跟踪交叉验证进度
        for train_index, test_index in tqdm(
            tscv.split(X), desc="交叉验证", total=n_splits, unit="折", ncols=80
        ):
            X_train, X_test = X.iloc[train_index], X.iloc[test_index]
            y_train, y_test = y.iloc[train_index], y.iloc[test_index]

            # 标准化
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # 训练和预测
            model.fit(X_train_scaled, y_train)
            predictions = model.predict(X_test_scaled)

            # 计算指标
            mse = mean_squared_error(y_test, predictions)
            r2 = r2_score(y_test, predictions)
            ic = pd.Series(predictions, index=y_test.index).corr(y_test, method="spearman")

            mse_scores.append(mse)
            r2_scores.append(r2)
            ic_scores.append(ic)

        # 计算平均指标
        cv_metrics = {
            "mean_mse": np.mean(mse_scores),
            "std_mse": np.std(mse_scores),
            "mean_r2": np.mean(r2_scores),
            "std_r2": np.std(r2_scores),
            "mean_ic": np.mean(ic_scores),
            "std_ic": np.std(ic_scores),
        }

        logger.info(
            f"交叉验证完成，平均MSE: {cv_metrics['mean_mse']:.4f}, 平均R²: {cv_metrics['mean_r2']:.4f}, 平均IC: {cv_metrics['mean_ic']:.4f}"
        )

        return cv_metrics

    def get_feature_importance(self) -> pd.Series:
        """
        获取特征重要性

        Returns:
            feature_importance: 特征重要性序列
        """
        if self.feature_importance is None:
            raise ValueError("特征重要性未计算")

        return self.feature_importance

    def generate_trading_signal(
        self,
        predictions: pd.Series,
        signal_type: str = "rank",
        top_pct: float = 0.2,
        bottom_pct: float = 0.2,
        vol_window: int = 24,
        max_position: float = 1.0,
        smooth_window: int = None,
    ) -> pd.Series:
        """
        生成交易信号，包含风险管理功能

        Args:
            predictions: 模型预测结果
            signal_type: 信号类型，支持 'rank'（排名信号）或 'continuous'（连续信号）
            top_pct: 多头信号的阈值（排名前N%）
            bottom_pct: 空头信号的阈值（排名后N%）
            vol_window: 波动率计算窗口
            max_position: 最大仓位限制
            smooth_window: 信号平滑窗口（MA）

        Returns:
            signal: 交易信号
        """
        logger.info(f"开始生成交易信号，信号类型: {signal_type}")

        if signal_type == "continuous":
            # 连续信号，使用预测值
            raw_signal = predictions
        elif signal_type == "rank":
            # 排名信号，生成-1, 0, 1信号
            rank = predictions.rank(pct=True)
            raw_signal = pd.Series(0, index=predictions.index)

            # 多头信号
            raw_signal[rank > (1 - top_pct)] = 1

            # 空头信号
            raw_signal[rank < bottom_pct] = -1
        else:
            raise ValueError(f"不支持的信号类型: {signal_type}")

        # 信号平滑
        if smooth_window is not None:
            raw_signal = raw_signal.rolling(window=smooth_window).mean()
            logger.info(f"信号平滑完成，窗口: {smooth_window}")

        # 波动率缩放（使用预测值的波动率）
        if vol_window is not None:
            # 计算预测值的滚动波动率
            vol = predictions.rolling(window=vol_window).std()
            # 波动率缩放，使信号具有相同的风险水平
            scaled_signal = raw_signal / (vol + 1e-8)  # 避免除以零
            logger.info("信号波动率缩放完成")
        else:
            scaled_signal = raw_signal

        # 仓位限制
        signal = scaled_signal.clip(-max_position, max_position)
        logger.info(f"仓位限制应用完成，最大仓位: {max_position}")

        logger.info("交易信号生成完成")

        return signal

    def calculate_strategy_metrics(
        self, signal: pd.Series, returns: pd.Series, timeframe: str = "1h"
    ) -> dict[str, float]:
        """
        计算策略绩效指标

        Args:
            signal: 交易信号
            returns: 实际收益率
            timeframe: 时间周期，用于动态调整年化计算参数

        Returns:
            metrics: 策略绩效指标
        """
        logger.info("开始计算策略绩效指标")

        # 确保信号和收益率的索引对齐
        common_index = signal.index.intersection(returns.index)
        signal = signal.loc[common_index]
        returns = returns.loc[common_index]

        # 计算策略收益率
        strategy_returns = signal.shift(1) * returns  # 信号滞后一期

        # 移除NaN值
        strategy_returns = strategy_returns.dropna()

        # 如果没有有效数据，返回默认值
        if len(strategy_returns) == 0:
            logger.warning("策略收益率中没有有效数据，返回默认绩效指标")
            return {
                "annual_return": 0.0,
                "annual_volatility": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "cumulative_return": 0.0,
            }

        # 计算累计收益率
        cumulative_returns = (1 + strategy_returns).cumprod()

        # 根据时间周期确定每年的周期数
        if timeframe == "1h":
            periods_per_year = 24 * 365  # 小时级: 24小时/天 * 365天/年
        elif timeframe == "30m":
            periods_per_year = 48 * 365  # 30分钟级: 48个30分钟/天 * 365天/年
        elif timeframe == "15m":
            periods_per_year = 96 * 365  # 15分钟级: 96个15分钟/天 * 365天/年
        elif timeframe == "5m":
            periods_per_year = 288 * 365  # 5分钟级: 288个5分钟/天 * 365天/年
        elif timeframe == "1m":
            periods_per_year = 1440 * 365  # 1分钟级: 1440分钟/天 * 365天/年
        else:
            periods_per_year = 24 * 365  # 默认小时级

        # 计算年化收益率
        try:
            # 确保 cumulative_returns 不为空且最后一个值有效
            if not np.isfinite(cumulative_returns.iloc[-1]):
                annual_return = 0.0
            else:
                annual_return = (
                    cumulative_returns.iloc[-1] ** (periods_per_year / len(cumulative_returns)) - 1
                )
        except Exception as e:
            logger.warning(f"计算年化收益率时出错: {e}，返回默认值0.0")
            annual_return = 0.0

        # 计算年化波动率
        try:
            annual_volatility = strategy_returns.std() * np.sqrt(periods_per_year)
            # 处理可能的NaN或无穷大值
            if not np.isfinite(annual_volatility):
                annual_volatility = 0.0
        except Exception as e:
            logger.warning(f"计算年化波动率时出错: {e}，返回默认值0.0")
            annual_volatility = 0.0

        # 计算夏普比率
        try:
            if annual_volatility > 0:
                sharpe_ratio = annual_return / annual_volatility
            else:
                sharpe_ratio = 0.0
            # 处理可能的NaN或无穷大值
            if not np.isfinite(sharpe_ratio):
                sharpe_ratio = 0.0
        except Exception as e:
            logger.warning(f"计算夏普比率时出错: {e}，返回默认值0.0")
            sharpe_ratio = 0.0

        # 计算最大回撤
        try:
            drawdown = cumulative_returns / cumulative_returns.cummax() - 1
            max_drawdown = drawdown.min()
            # 处理可能的NaN或无穷大值
            if not np.isfinite(max_drawdown):
                max_drawdown = 0.0
        except Exception as e:
            logger.warning(f"计算最大回撤时出错: {e}，返回默认值0.0")
            max_drawdown = 0.0

        # 计算胜率
        try:
            winning_trades = strategy_returns[strategy_returns > 0]
            win_rate = (
                len(winning_trades) / len(strategy_returns) if len(strategy_returns) > 0 else 0
            )
        except Exception as e:
            logger.warning(f"计算胜率时出错: {e}，返回默认值0.0")
            win_rate = 0.0

        # 计算累计收益率
        try:
            cumulative_return = cumulative_returns.iloc[-1] - 1
            # 处理可能的NaN或无穷大值
            if not np.isfinite(cumulative_return):
                cumulative_return = 0.0
        except Exception as e:
            logger.warning(f"计算累计收益率时出错: {e}，返回默认值0.0")
            cumulative_return = 0.0

        metrics = {
            "annual_return": annual_return,
            "annual_volatility": annual_volatility,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "cumulative_return": cumulative_return,
        }

        logger.info(
            f"策略绩效指标计算完成，年化收益率: {annual_return:.4f}, 夏普比率: {sharpe_ratio:.4f}, 最大回撤: {max_drawdown:.4f}"
        )

        return metrics

    def monte_carlo_overfitting_test(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        model_type: str = "ridge",
        params: dict[str, Any] = None,
        n_simulations: int = 100,
    ) -> dict[str, Any]:
        """
        使用蒙特卡洛模拟检测模型过拟合

        Args:
            X: 因子矩阵
            y: 标签
            model_type: 模型类型
            params: 模型参数
            n_simulations: 模拟次数

        Returns:
            results: 蒙特卡洛测试结果，包含真实IC、模拟IC分布、p值等
        """
        logger.info(f"开始蒙特卡洛过拟合检测，模拟次数: {n_simulations}")

        # 训练真实模型并计算IC
        real_model = self.train_model(X, y, model_type, params)
        real_predictions = self.predict(X)
        real_ic = real_predictions.corr(y, method="spearman")

        # 存储模拟结果
        simulated_ics = []

        # 进行蒙特卡洛模拟
        logger.info("开始蒙特卡洛模拟...")
        for i in tqdm(range(n_simulations), desc="蒙特卡洛模拟", total=n_simulations):
            # 随机打乱标签
            y_shuffled = y.sample(frac=1, random_state=i).reset_index(drop=True)
            y_shuffled.index = y.index  # 保持原索引

            # 训练模型并计算IC
            model = self.train_model(X, y_shuffled, model_type, params)
            predictions = self.predict(X)
            ic = predictions.corr(y_shuffled, method="spearman")
            simulated_ics.append(ic)
        logger.info("蒙特卡洛模拟完成")

        # 计算统计指标
        simulated_ics = np.array(simulated_ics)
        mean_simulated_ic = np.mean(simulated_ics)
        std_simulated_ic = np.std(simulated_ics)

        # 计算p值：真实IC大于等于模拟IC的比例
        p_value = np.mean(simulated_ics >= real_ic)

        # 计算Z值：(真实IC - 平均模拟IC) / 模拟IC标准差
        z_score = (real_ic - mean_simulated_ic) / (std_simulated_ic + 1e-8)  # 避免除以零

        # 计算过拟合程度：真实IC与模拟IC的差值
        overfitting_score = real_ic - mean_simulated_ic

        results = {
            "real_ic": real_ic,
            "mean_simulated_ic": mean_simulated_ic,
            "std_simulated_ic": std_simulated_ic,
            "p_value": p_value,
            "z_score": z_score,
            "overfitting_score": overfitting_score,
            "simulated_ics": simulated_ics,
            "n_simulations": n_simulations,
        }

        logger.info(
            f"蒙特卡洛过拟合检测完成：真实IC={real_ic:.4f}, 平均模拟IC={mean_simulated_ic:.4f}, p值={p_value:.4f}, Z值={z_score:.4f}"
        )

        return results

    def optimize_model(
        self,
        X: pd.DataFrame,
        y: pd.Series,
        model_type: str = "ridge",
        param_grid: dict[str, list[Any]] = None,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        """
        优化模型参数

        Args:
            X: 因子矩阵
            y: 标签
            model_type: 模型类型
            param_grid: 参数网格

        Returns:
            best_params: 最佳参数
            best_metrics: 最佳指标
        """
        logger.info(f"开始优化 {model_type} 模型参数")

        # 设置默认参数网格
        if param_grid is None:
            if model_type == "ridge":
                param_grid = {"alpha": [0.1, 1.0, 10.0, 100.0]}
            elif model_type == "lasso":
                param_grid = {"alpha": [0.001, 0.01, 0.1, 1.0]}
            elif model_type == "rf":
                param_grid = {"n_estimators": [50, 100, 200], "max_depth": [3, 5, 7]}
            elif model_type == "gbdt":
                param_grid = {
                    "n_estimators": [50, 100, 200],
                    "learning_rate": [0.01, 0.1, 0.2],
                    "max_depth": [3, 5, 7],
                }
            else:
                param_grid = {}

        # 生成所有参数组合
        from itertools import product

        param_names = list(param_grid.keys())
        param_combinations = list(product(*param_grid.values()))

        best_score = -np.inf
        best_params = None
        best_metrics = None

        # 遍历所有参数组合，使用tqdm跟踪进度
        for params_tuple in tqdm(
            param_combinations,
            desc="参数网格搜索",
            total=len(param_combinations),
            unit="组合",
            ncols=80,
        ):
            params = dict(zip(param_names, params_tuple))

            # 交叉验证
            metrics = self.cross_validate(X, y, model_type, params)

            # 使用平均IC作为评分指标
            score = metrics["mean_ic"]

            if score > best_score:
                best_score = score
                best_params = params
                best_metrics = metrics

        logger.info(
            f"参数优化完成，最佳参数: {best_params}, 最佳平均IC: {best_metrics['mean_ic']:.4f}"
        )

        return best_params, best_metrics
