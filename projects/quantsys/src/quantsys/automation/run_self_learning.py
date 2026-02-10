#!/usr/bin/env python3
"""
运行自学习系统来持续优化ETH小时级多因子策略
"""

import logging

import numpy as np
import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 导入自定义模块
from eth_hourly_multi_factor import ETHHourlyMultiFactor


def run_self_learning_demo():
    """
    运行自学习系统演示
    """
    logger.info("=== 启动ETH小时级多因子策略自学习系统 ===")

    # 创建测试数据
    logger.info("创建测试数据...")
    np.random.seed(42)
    n_samples = 8760  # 一年的小时数据
    dates = pd.date_range(start="2023-01-01", periods=n_samples, freq="h")

    # 创建模拟的OHLCV数据
    base_price = 1500  # ETH起始价格
    price_changes = np.random.normal(0, 0.02, n_samples)
    prices = base_price * np.exp(np.cumsum(price_changes))

    data = pd.DataFrame(
        {
            "open": prices,
            "high": prices * (1 + np.random.uniform(0, 0.03, n_samples)),
            "low": prices * (1 - np.random.uniform(0, 0.03, n_samples)),
            "close": prices * (1 + np.random.uniform(-0.02, 0.02, n_samples)),
            "volume": np.random.uniform(1000, 10000, n_samples),
            "amount": np.random.uniform(1000000, 10000000, n_samples),
        },
        index=dates,
    )

    logger.info(f"测试数据创建完成，形状: {data.shape}")

    # 初始化策略
    strategy = ETHHourlyMultiFactor(data)

    # 运行自学习循环
    logger.info("开始运行自学习循环...")

    # 第一次完整运行
    results1 = strategy.run_full_pipeline(
        n_factors=50, n_best=15, model_type="ridge", signal_type="rank"
    )

    logger.info(f"第一轮策略运行完成，夏普比率: {results1['metrics']['sharpe_ratio']:.4f}")

    # 模拟一段时间后更新
    logger.info("\n=== 模拟30天后的自学习更新 ===")

    # 再次运行完整流程，模拟自学习更新
    results2 = strategy.run_full_pipeline(
        n_factors=50, n_best=15, model_type="ridge", signal_type="rank"
    )

    logger.info(f"第二轮策略运行完成，夏普比率: {results2['metrics']['sharpe_ratio']:.4f}")

    # 比较结果
    logger.info("\n=== 自学习效果比较 ===")
    logger.info(f"第一轮夏普比率: {results1['metrics']['sharpe_ratio']:.4f}")
    logger.info(f"第二轮夏普比率: {results2['metrics']['sharpe_ratio']:.4f}")

    if not pd.isna(results1["metrics"]["sharpe_ratio"]) and not pd.isna(
        results2["metrics"]["sharpe_ratio"]
    ):
        improvement = results2["metrics"]["sharpe_ratio"] - results1["metrics"]["sharpe_ratio"]
        logger.info(
            f"夏普比率变化: {improvement:.4f} ({improvement / abs(results1['metrics']['sharpe_ratio']) * 100:.2f}%)"
        )

    logger.info("=== 自学习系统演示完成 ===")


if __name__ == "__main__":
    run_self_learning_demo()
