#!/usr/bin/env python3
"""
使用蒙特卡洛方法检测ETH小时级多因子策略的过拟合情况
"""

import logging

import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 导入策略类
from eth_hourly_multi_factor import ETHHourlyMultiFactor


def check_overfitting_for_models():
    """
    对不同模型进行过拟合检测
    """
    logger.info("=== 开始多模型过拟合检测 ===")

    # 初始化策略
    strategy = ETHHourlyMultiFactor()

    # 创建测试数据（使用更长时间的数据以提高检测准确性）
    test_data = strategy.create_test_data(n_samples=365 * 24)  # 一年数据

    # 加载数据
    strategy.load_data(test_data)

    # 生成因子
    logger.info("=== 开始生成因子 ===")
    best_factors = strategy.run_factor_generation(
        n_factors=50,  # 生成50个因子
        n_best=15,  # 选择前15个最优因子
        use_dl_factors=True,  # 使用深度学习因子
    )

    # 测试不同模型
    model_types = ["ridge", "lasso", "rf", "gbdt"]
    overfitting_results = {}

    for model_type in model_types:
        logger.info(f"\n=== 检测模型: {model_type} ===")

        try:
            # 运行过拟合检测
            results = strategy.check_overfitting(
                model_type=model_type,
                n_simulations=50,  # 50次模拟，平衡准确性和速度
            )

            overfitting_results[model_type] = results

        except Exception as e:
            logger.error(f"检测 {model_type} 模型过拟合失败: {str(e)}")
            continue

    # 总结结果
    logger.info("\n=== 过拟合检测结果总结 ===")

    for model_type, results in overfitting_results.items():
        logger.info(f"\n{model_type} 模型:")
        logger.info(f"  真实IC: {results['real_ic']:.4f}")
        logger.info(f"  模拟平均IC: {results['mean_simulated_ic']:.4f}")
        logger.info(f"  p值: {results['p_value']:.4f}")
        logger.info(f"  Z值: {results['z_score']:.4f}")
        logger.info(f"  过拟合分数: {results['overfitting_score']:.4f}")

        if results["p_value"] < 0.05:
            logger.info("  结论: 未显著过拟合")
        else:
            logger.info("  结论: 可能存在过拟合风险")

    # 保存结果到文件
    results_df = pd.DataFrame.from_dict(overfitting_results, orient="index")
    results_df.to_csv("overfitting_detection_results.csv")
    logger.info("\n过拟合检测结果已保存到 overfitting_detection_results.csv")

    return overfitting_results


if __name__ == "__main__":
    check_overfitting_for_models()
