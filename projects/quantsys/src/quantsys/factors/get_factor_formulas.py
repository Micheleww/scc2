#!/usr/bin/env python3
"""
获取选择的15个因子的具体表达式和公式
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
    主函数，获取因子公式
    """
    logger.info("=== 开始获取因子公式 ===")

    # 创建策略实例
    strategy = ETHHourlyMultiFactor()

    # 创建测试数据
    test_data = strategy.create_test_data(n_samples=365 * 24)

    # 加载数据
    strategy.load_data(test_data)

    # 运行因子生成，获取因子表达式
    logger.info("生成因子并获取表达式...")

    # 生成因子
    strategy.factor_generator.generate_factors(n_factors=50, labels=strategy.data_framework.labels)

    # 获取因子得分和表达式
    factor_scores = strategy.factor_generator.get_factor_scores()

    # 过滤因子
    filtered_factors = strategy.factor_generator.filter_factors(min_abs_ic=0.01, max_corr=0.8)

    # 选择最佳15个因子
    if strategy.data_framework.labels is not None:
        # 计算每个因子的IC值
        ic_scores = {
            factor: abs(
                strategy.factor_generator.calculate_factor_ic(
                    filtered_factors[factor], strategy.data_framework.labels
                )
            )
            for factor in filtered_factors.columns
        }

        # 按IC值降序排序
        sorted_factors = sorted(ic_scores.items(), key=lambda x: x[1], reverse=True)

        # 选择前15个因子
        best_factor_names = [factor for factor, score in sorted_factors[:15]]

        logger.info("\n=== 选择的15个因子及其公式 ===")
        for factor_name in best_factor_names:
            if factor_name in factor_scores:
                expr = factor_scores[factor_name]["expression"]
                ic = factor_scores[factor_name]["ic"]
                logger.info(f"{factor_name}: {expr} (IC: {ic:.4f})")
            else:
                logger.info(f"{factor_name}: 表达式未找到")

    logger.info("\n=== 获取因子公式完成 ===")


if __name__ == "__main__":
    main()
