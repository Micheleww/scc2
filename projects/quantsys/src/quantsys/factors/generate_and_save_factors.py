#!/usr/bin/env python3
"""
独立的因子生成模块
用于生成因子并保存到因子库
"""

import argparse
import logging
import sys
from datetime import datetime

# 添加项目路径
sys.path.append("d:/quantsys/ai_collaboration")

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 导入自定义模块
from data_collection import collect_data
from database_manager import DatabaseManager
from eth_hourly_multi_factor import ETHHourlyMultiFactor


def parse_args():
    """
    解析命令行参数
    """
    parser = argparse.ArgumentParser(description="独立因子生成模块")

    # 基本参数
    parser.add_argument("--symbol", type=str, default="ETH/USDT", help="交易对")
    parser.add_argument("--timeframe", type=str, default="1h", help="时间周期")
    parser.add_argument("--days", type=int, default=60, help="数据天数")

    # 因子生成参数
    parser.add_argument("--n-factors", type=int, default=50, help="生成因子数量")
    parser.add_argument("--n-best", type=int, default=15, help="选择最佳因子数量")
    parser.add_argument("--no-dl-factors", action="store_true", help="不使用深度学习因子")

    # 输出参数
    parser.add_argument("--factor-set-name", type=str, default=None, help="因子集名称")

    return parser.parse_args()


def generate_factors(args):
    """
    生成因子并保存到因子库

    Args:
        args: 命令行参数
    """
    logger.info("=== 开始生成因子 ===")

    # 打印参数
    logger.info("\n参数配置:")
    logger.info(f"交易对: {args.symbol}")
    logger.info(f"时间周期: {args.timeframe}")
    logger.info(f"数据天数: {args.days}")
    logger.info(f"生成因子数量: {args.n_factors}")
    logger.info(f"选择最佳因子数量: {args.n_best}")
    logger.info(f"使用深度学习因子: {not args.no_dl_factors}")

    # 1. 加载数据
    logger.info("\n1. 加载数据...")
    data = collect_data("okx", args.symbol, args.timeframe, args.days)

    if data is None:
        logger.error("无法加载数据，因子生成失败")
        return False

    logger.info(
        f"数据加载完成，形状: {data.shape}, 时间范围: {data.index.min()} 到 {data.index.max()}"
    )

    # 2. 初始化策略实例
    logger.info("\n2. 初始化策略实例...")
    strategy = ETHHourlyMultiFactor(timeframe=args.timeframe)

    # 3. 加载数据到策略
    logger.info("3. 加载数据到策略...")
    strategy.load_data(data)

    # 4. 生成因子
    logger.info("\n4. 生成因子...")
    best_factors = strategy.run_factor_generation(
        n_factors=args.n_factors, n_best=args.n_best, use_dl_factors=not args.no_dl_factors
    )

    logger.info(f"因子生成完成，生成了 {len(best_factors.columns)} 个因子")
    logger.info(f"最佳因子: {list(best_factors.columns)}")

    # 5. 保存因子到因子库
    logger.info("\n5. 保存因子到因子库...")

    # 生成因子集名称
    if args.factor_set_name:
        factor_set_name = args.factor_set_name
    else:
        factor_set_name = f"{args.symbol.replace('/', '_')}_{args.timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 初始化数据库管理器
    db_manager = DatabaseManager()

    # 保存因子集
    factor_names = list(best_factors.columns)
    factor_set_id = db_manager.save_factor_set(factor_set_name, factor_names)

    if factor_set_id:
        logger.info(f"因子集保存成功，ID: {factor_set_id}, 名称: {factor_set_name}")
    else:
        logger.error("保存因子集失败")
        return False

    logger.info(f"因子集生成完成，包含 {len(best_factors.columns)} 个因子")
    logger.info(f"最佳因子: {list(best_factors.columns)}")

    logger.info("\n=== 因子生成完成 ===")
    logger.info(f"因子数量: {len(best_factors.columns)}")
    logger.info(
        f"因子生成参数: n_factors={args.n_factors}, n_best={args.n_best}, dl_factors={not args.no_dl_factors}"
    )

    return True


def main():
    """
    主函数
    """
    args = parse_args()
    generate_factors(args)


if __name__ == "__main__":
    main()
