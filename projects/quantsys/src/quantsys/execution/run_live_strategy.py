#!/usr/bin/env python3
"""
运行实盘策略脚本
用于启动表现最好的多因子策略，实现自动买入卖出
"""

import json
import logging

from eth_hourly_multi_factor import ETHHourlyMultiFactor

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_config(config_path):
    """
    加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        config: 配置字典
    """
    with open(config_path) as f:
        config = json.load(f)
    return config


def main():
    """
    主函数
    """
    logger.info("=== 启动实盘多因子策略 ===")

    # 加载配置
    config_path = "live_strategy_config.json"
    config = load_config(config_path)

    logger.info("配置文件加载完成")

    # 获取策略配置
    strategy_config = config["strategy"]

    # 创建策略实例，启用实盘交易模式
    strategy = ETHHourlyMultiFactor(
        symbol=strategy_config["symbol"],
        timeframe=strategy_config["timeframe"],
        live_trading=True,
        config=config,
    )

    # 创建测试数据或连接真实数据源
    # 在实际应用中，这里应该替换为从实时数据接口获取数据
    test_data = strategy.create_test_data(n_samples=365 * 24)

    # 加载数据
    strategy.load_data(test_data)

    # 运行实盘策略
    logger.info(f"开始运行实盘策略，更新间隔: {strategy_config['update_interval']} 秒")
    logger.info(
        f"策略配置: 交易对={strategy_config['symbol']}, 时间周期={strategy_config['timeframe']}"
    )
    logger.info(f"风险配置: 单笔最大金额={config['risk']['max_single_order_amount']} USDT")

    try:
        # 运行实盘策略
        strategy.run_live_strategy(update_interval=strategy_config["update_interval"])
    except KeyboardInterrupt:
        logger.info("实盘策略已停止")
    except Exception as e:
        logger.error(f"实盘策略运行出错: {e}")
    finally:
        logger.info("=== 实盘多因子策略运行结束 ===")


if __name__ == "__main__":
    main()
