#!/usr/bin/env python3
"""
自学习系统模块
实现策略的自动更新和改进
"""

import logging
from datetime import datetime
from typing import Any

import pandas as pd
from tqdm import tqdm

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SelfLearningSystem:
    """
    自学习系统
    实现策略的自动更新和改进
    """

    def __init__(self, data_framework, factor_generator, factor_optimizer):
        """
        初始化自学习系统

        Args:
            data_framework: 数据处理框架实例
            factor_generator: 自动因子生成器实例
            factor_optimizer: 因子优化器实例
        """
        self.data_framework = data_framework
        self.factor_generator = factor_generator
        self.factor_optimizer = factor_optimizer

        # 自学习参数
        self.update_interval = 24  # 每24小时更新一次
        self.last_update_time = datetime.now()
        self.performance_history = []

        logger.info("自学习系统初始化完成")

    def check_update_needed(self) -> bool:
        """
        检查是否需要更新策略

        Returns:
            update_needed: 是否需要更新
        """
        current_time = datetime.now()
        time_since_last_update = (current_time - self.last_update_time).total_seconds() / 3600

        return time_since_last_update >= self.update_interval

    def update_factors(self, n_factors: int = 100, n_best: int = 20) -> pd.DataFrame:
        """
        更新因子

        Args:
            n_factors: 生成因子的数量
            n_best: 选择最佳因子的数量

        Returns:
            best_factors: 最佳因子矩阵
        """
        logger.info("开始更新因子")

        # 获取标签
        labels = self.data_framework.get_labels()

        # 生成并选择最佳因子
        best_factors = self.factor_generator.generate_best_factors(
            n_factors=n_factors, n_best=n_best, labels=labels
        )

        # 更新数据框架中的因子矩阵
        self.data_framework.factor_matrix = best_factors

        # 清理因子矩阵
        self.data_framework.clean_factor_matrix()

        logger.info(f"因子更新完成，共更新 {len(best_factors.columns)} 个因子")

        return best_factors

    def retrain_model(self, model_type: str = "ridge", params: dict[str, Any] = None) -> Any:
        """
        重新训练模型

        Args:
            model_type: 模型类型
            params: 模型参数

        Returns:
            model: 训练好的模型
        """
        logger.info(f"开始重新训练 {model_type} 模型")

        # 划分训练集和测试集
        X_train, X_test, y_train, y_test = self.data_framework.split_data()

        # 训练模型
        model = self.factor_optimizer.train_model(X_train, y_train, model_type, params)

        # 评估模型
        metrics = self.factor_optimizer.evaluate_model(X_test, y_test)

        # 记录模型性能
        self.performance_history.append(
            {
                "timestamp": datetime.now(),
                "model_type": model_type,
                "params": params,
                "metrics": metrics,
            }
        )

        logger.info("模型重新训练完成")

        return model

    def optimize_strategy(self) -> dict[str, Any]:
        """
        优化策略参数

        Returns:
            optimization_results: 优化结果
        """
        logger.info("开始优化策略")

        # 获取因子矩阵和标签
        X = self.data_framework.get_factor_matrix()
        y = self.data_framework.get_labels()

        # 对齐数据
        common_index = X.index.intersection(y.index)
        X = X.loc[common_index]
        y = y.loc[common_index]

        # 优化模型参数
        best_params, best_metrics = self.factor_optimizer.optimize_model(X, y)

        # 使用最佳参数重新训练模型
        self.retrain_model(params=best_params)

        optimization_results = {
            "best_params": best_params,
            "best_metrics": best_metrics,
            "optimization_time": datetime.now(),
        }

        logger.info("策略优化完成")

        return optimization_results

    def run_self_learning_cycle(
        self, n_factors: int = 100, n_best: int = 20, model_type: str = "ridge"
    ) -> dict[str, Any]:
        """
        运行完整的自学习周期

        Args:
            n_factors: 生成因子的数量
            n_best: 选择最佳因子的数量
            model_type: 模型类型

        Returns:
            cycle_results: 自学习周期结果
        """
        logger.info("开始运行自学习周期")

        # 使用tqdm跟踪自学习周期的各个步骤
        with tqdm(total=5, desc="自学习周期", unit="步骤", ncols=80) as pbar:
            # 更新因子
            pbar.set_description("步骤1/5: 更新因子")
            best_factors = self.update_factors(n_factors, n_best)
            pbar.update(1)

            # 优化并重新训练模型
            pbar.set_description("步骤2/5: 优化并重新训练模型")
            optimization_results = self.optimize_strategy()
            pbar.update(1)

            # 更新最后更新时间
            self.last_update_time = datetime.now()

            # 生成交易信号
            pbar.set_description("步骤3/5: 生成交易信号")
            X = self.data_framework.get_factor_matrix()
            predictions = self.factor_optimizer.predict(X)
            signal = self.factor_optimizer.generate_trading_signal(predictions)
            pbar.update(1)

            # 计算策略绩效
            pbar.set_description("步骤4/5: 计算策略绩效")
            returns = self.data_framework.data["ret_1h"]
            strategy_metrics = self.factor_optimizer.calculate_strategy_metrics(signal, returns)
            pbar.update(1)

            # 整合结果
            pbar.set_description("步骤5/5: 整合结果")
            cycle_results = {
                "update_time": self.last_update_time,
                "best_factors": best_factors,
                "optimization_results": optimization_results,
                "signal": signal,
                "strategy_metrics": strategy_metrics,
            }
            pbar.update(1)

        logger.info(f"自学习周期完成，策略夏普比率: {strategy_metrics['sharpe_ratio']:.4f}")

        return cycle_results

    def get_performance_history(self) -> pd.DataFrame:
        """
        获取性能历史

        Returns:
            performance_history: 性能历史数据框
        """
        if not self.performance_history:
            return pd.DataFrame()

        return pd.DataFrame(self.performance_history)

    def run(self):
        """
        运行自学习系统
        """
        logger.info("启动自学习系统")

        while True:
            if self.check_update_needed():
                # 运行自学习周期
                self.run_self_learning_cycle()

            # 休眠1小时
            import time

            time.sleep(3600)
