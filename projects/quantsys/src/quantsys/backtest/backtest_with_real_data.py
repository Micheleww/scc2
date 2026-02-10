#!/usr/bin/env python3
"""
使用真实数据回测ETH多因子策略
"""

import logging
import sys
from datetime import datetime

import pandas as pd

# 添加项目路径
sys.path.append("d:/quantsys/ai_collaboration")

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 导入自定义模块
from data_collection import collect_data
from eth_hourly_multi_factor import ETHHourlyMultiFactor


def backtest_with_real_data():
    """
    使用真实数据回测ETH多因子策略
    """
    logger.info("=== 开始使用真实数据回测ETH多因子策略 ===")

    # 配置回测参数
    symbol = "ETH/USDT"
    timeframe = "1h"  # 支持 1m, 5m, 15m, 30m, 1h
    days = 30  # 回测天数

    logger.info(f"回测参数: 交易对={symbol}, 时间周期={timeframe}, 回测天数={days}")

    # 1. 加载真实数据
    logger.info("正在加载真实数据...")
    data = collect_data("okx", symbol, timeframe, days)

    if data is None:
        logger.error("无法加载数据，回测失败")
        return

    logger.info(
        f"数据加载完成，数据形状: {data.shape}, 时间范围: {data.index.min()} 到 {data.index.max()}"
    )

    # 2. 初始化策略
    logger.info("正在初始化策略...")
    strategy = ETHHourlyMultiFactor(timeframe=timeframe)

    # 3. 加载数据到策略
    logger.info("正在加载数据到策略...")
    strategy.load_data(data)

    # 4. 运行策略回测
    logger.info("正在运行策略回测...")
    results = strategy.run_full_pipeline(
        n_factors=50,  # 生成50个因子
        n_best=15,  # 选择15个最佳因子
        model_type="ridge",  # 使用Ridge模型
        signal_type="rank",  # 使用排名信号
        use_dl_factors=True,  # 使用深度学习因子
    )

    # 5. 输出回测结果
    logger.info("=== 回测结果 ===")

    # 打印模型评估指标
    logger.info("\n模型评估指标:")
    for metric_name, metric_value in results["model_metrics"].items():
        logger.info(f"{metric_name}: {metric_value:.4f}")

    # 打印策略绩效指标
    logger.info("\n策略绩效指标:")
    performance_metrics = results["performance_metrics"]
    logger.info(f"年化收益率: {performance_metrics['annual_return']:.4f}")
    logger.info(f"年化波动率: {performance_metrics['annual_volatility']:.4f}")
    logger.info(f"夏普比率: {performance_metrics['sharpe_ratio']:.4f}")
    logger.info(f"最大回撤: {performance_metrics['max_drawdown']:.4f}")
    logger.info(f"胜率: {performance_metrics['win_rate']:.4f}")
    logger.info(f"累计收益率: {performance_metrics['cumulative_return']:.4f}")

    # 打印最佳因子
    logger.info("\n最佳因子:")
    logger.info(list(results["best_factors"].columns))

    # 打印特征重要性
    logger.info("\n特征重要性:")
    logger.info(results["feature_importance"].head(10))

    # 6. 保存回测结果
    save_results(results, strategy)

    logger.info("=== 回测完成 ===")


def save_results(results, strategy):
    """
    保存回测结果
    """
    # 创建结果目录
    import os

    result_dir = (
        f"d:/quantsys/ai_collaboration/backtest_results/{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    os.makedirs(result_dir, exist_ok=True)

    # 保存交易信号
    results["signal"].to_csv(f"{result_dir}/trading_signals.csv")
    logger.info(f"交易信号已保存到: {result_dir}/trading_signals.csv")

    # 保存最佳因子
    results["best_factors"].to_csv(f"{result_dir}/best_factors.csv")
    logger.info(f"最佳因子已保存到: {result_dir}/best_factors.csv")

    # 保存绩效指标
    performance_df = pd.DataFrame([results["performance_metrics"]])
    performance_df.to_csv(f"{result_dir}/performance_metrics.csv", index=False)
    logger.info(f"绩效指标已保存到: {result_dir}/performance_metrics.csv")

    # 保存特征重要性
    results["feature_importance"].to_csv(f"{result_dir}/feature_importance.csv")
    logger.info(f"特征重要性已保存到: {result_dir}/feature_importance.csv")

    # 运行回测并保存回测结果
    backtest_df = strategy.backtest_strategy(results["signal"])
    backtest_df.to_csv(f"{result_dir}/backtest_results.csv")
    logger.info(f"回测结果已保存到: {result_dir}/backtest_results.csv")


if __name__ == "__main__":
    backtest_with_real_data()
