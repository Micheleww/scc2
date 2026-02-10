#!/usr/bin/env python3
"""
获取选择的15个最佳因子及其数值
"""

import logging

from eth_hourly_multi_factor import ETHHourlyMultiFactor

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """
    主函数，运行策略并获取最佳因子
    """
    logger.info("=== 开始获取15个最佳因子 ===")

    # 创建策略实例
    strategy = ETHHourlyMultiFactor()

    # 创建测试数据
    test_data = strategy.create_test_data(n_samples=365 * 24)

    # 加载数据
    strategy.load_data(test_data)

    # 运行完整的策略流程，选择15个最佳因子
    results = strategy.run_full_pipeline(
        n_factors=50,  # 生成50个因子
        n_best=15,  # 选择15个最佳因子
        model_type="ridge",
        signal_type="rank",
    )

    # 获取最佳因子
    best_factors = results["best_factors"]

    # 保存最佳因子到CSV文件
    best_factors_file = "best_factors.csv"
    best_factors.to_csv(best_factors_file)
    logger.info(f"最佳因子已保存到 {best_factors_file}")

    # 打印因子名称
    logger.info("\n=== 选择的15个因子 ===")
    for factor_name in best_factors.columns:
        logger.info(factor_name)

    # 打印因子的前几行数值
    logger.info("\n=== 因子数值示例 (前5行) ===")
    print(best_factors.head())

    # 打印因子的统计信息
    logger.info("\n=== 因子统计信息 ===")
    print(best_factors.describe())

    logger.info("\n=== 获取最佳因子完成 ===")


if __name__ == "__main__":
    main()
