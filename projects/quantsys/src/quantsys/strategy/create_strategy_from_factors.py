#!/usr/bin/env python3
"""
独立的策略创建模块
用于从因子库中选择因子并生成策略
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
from strategy_library_manager import StrategyLibraryManager


def parse_args():
    """
    解析命令行参数
    """
    parser = argparse.ArgumentParser(description="独立策略创建模块")

    # 基本参数
    parser.add_argument("--symbol", type=str, default="ETH/USDT", help="交易对")
    parser.add_argument("--timeframe", type=str, default="1h", help="时间周期")
    parser.add_argument("--days", type=int, default=60, help="数据天数")

    # 因子选择参数
    parser.add_argument("--factor-set-id", type=int, default=None, help="因子集ID")
    parser.add_argument("--factor-set-name", type=str, default=None, help="因子集名称")
    parser.add_argument("--signal-type", type=str, default="rank", help="信号类型")

    # 输出参数
    parser.add_argument("--strategy-name", type=str, default=None, help="策略名称")

    return parser.parse_args()


def create_strategy(args):
    """
    从因子库中选择因子并生成策略

    Args:
        args: 命令行参数
    """
    logger.info("=== 开始创建策略 ===")

    # 打印参数
    logger.info("\n参数配置:")
    logger.info(f"交易对: {args.symbol}")
    logger.info(f"时间周期: {args.timeframe}")
    logger.info(f"数据天数: {args.days}")
    logger.info(f"因子集ID: {args.factor_set_id}")
    logger.info(f"因子集名称: {args.factor_set_name}")
    logger.info(f"信号类型: {args.signal_type}")

    # 1. 加载数据
    logger.info("\n1. 加载数据...")
    data = collect_data("okx", args.symbol, args.timeframe, args.days)

    if data is None:
        logger.error("无法加载数据，策略创建失败")
        return False

    logger.info(f"数据加载完成，形状: {data.shape}")

    # 2. 初始化策略实例
    logger.info("\n2. 初始化策略实例...")
    strategy = ETHHourlyMultiFactor(timeframe=args.timeframe)

    # 3. 加载数据到策略
    logger.info("3. 加载数据到策略...")
    strategy.load_data(data)

    # 4. 从因子库加载因子
    logger.info("\n4. 从因子库加载因子...")

    # 初始化数据库管理器
    db_manager = DatabaseManager()

    # 加载因子集
    factor_names = None
    if args.factor_set_id or args.factor_set_name:
        factor_names = db_manager.load_factor_set(args.factor_set_id, args.factor_set_name)

    if factor_names:
        logger.info(f"成功从因子库加载因子集，包含 {len(factor_names)} 个因子")
        logger.info(f"因子列表: {factor_names}")

        # 生成指定因子
        best_factors = strategy.run_factor_generation(
            n_factors=len(factor_names), n_best=len(factor_names), use_dl_factors=True
        )

        # 只保留因子集中的因子
        available_factors = [f for f in factor_names if f in best_factors.columns]
        best_factors = best_factors[available_factors]

        logger.info(f"实际生成了 {len(best_factors.columns)} 个因子")
    else:
        # 如果无法加载因子集，使用默认生成方式
        logger.info("无法加载因子集，使用默认生成方式")
        best_factors = strategy.run_factor_generation(n_factors=50, n_best=15, use_dl_factors=True)

    logger.info(f"因子生成完成，形状: {best_factors.shape}")
    factor_matrix = best_factors

    # 6. 将因子添加到数据框架
    logger.info("\n6. 将因子添加到数据框架...")
    for factor_name in factor_matrix.columns:
        strategy.data_framework.add_factor(factor_name, factor_matrix[factor_name])

    # 清理因子矩阵
    strategy.data_framework.clean_factor_matrix()

    # 7. 训练模型（只使用ridge模型）
    logger.info("\n7. 训练ridge模型...")
    model, model_metrics = strategy.train_model(model_type="ridge")

    logger.info(f"模型训练完成，IC: {model_metrics['ic']:.4f}")

    # 8. 生成交易信号
    logger.info("\n8. 生成交易信号...")
    signal = strategy.generate_trading_signals(signal_type=args.signal_type)

    # 9. 计算策略绩效
    logger.info("\n9. 计算策略绩效...")
    performance_metrics = strategy.calculate_strategy_performance(signal)

    logger.info(
        f"策略绩效计算完成，夏普比率: {performance_metrics['sharpe_ratio']:.4f}, 最大回撤: {performance_metrics['max_drawdown']:.4f}"
    )

    # 10. 保存策略到策略库
    logger.info("\n10. 保存策略到策略库...")

    # 生成策略名称
    if args.strategy_name:
        strategy_name = args.strategy_name
    else:
        strategy_name = f"strategy_{args.symbol.replace('/', '_')}_{args.timeframe}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 初始化策略库管理器
    strategy_library = StrategyLibraryManager()

    # 准备策略数据
    strategy_data = {
        "model": strategy.factor_optimizer.model,
        "model_type": "ridge",
        "best_factors": factor_matrix,
        "feature_importance": strategy.factor_optimizer.get_feature_importance(),
        "performance_metrics": performance_metrics,
        "train_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": {
            "symbol": args.symbol,
            "timeframe": args.timeframe,
            "signal_type": args.signal_type,
        },
        "scaler": strategy.factor_optimizer.scaler,
    }

    # 保存策略
    strategy_id = strategy_library.save_strategy(strategy_data, strategy_name)

    if not strategy_id:
        logger.error("保存策略到策略库失败")
        return False

    logger.info(f"策略保存成功，策略ID: {strategy_id}, 名称: {strategy_name}")

    # 11. 显示策略结果
    logger.info("\n11. 策略结果:")
    logger.info("模型类型: ridge")
    logger.info(f"夏普比率: {performance_metrics['sharpe_ratio']:.4f}")
    logger.info(f"最大回撤: {performance_metrics['max_drawdown']:.4f}")
    logger.info(f"年化收益率: {performance_metrics['annual_return']:.4f}")
    logger.info(f"胜率: {performance_metrics['win_rate']:.4f}")
    logger.info(f"累计收益率: {performance_metrics['cumulative_return']:.4f}")
    logger.info(f"因子数量: {len(factor_matrix.columns)}")
    logger.info("特征重要性(前5):")
    for factor_name, importance in (
        strategy.factor_optimizer.get_feature_importance().head(5).items()
    ):
        logger.info(f"  {factor_name}: {importance:.4f}")

    logger.info("\n=== 策略创建完成 ===")
    logger.info(f"策略ID: {strategy_id}")
    logger.info(f"策略名称: {strategy_name}")

    return True


def main():
    """
    主函数
    """
    args = parse_args()
    create_strategy(args)


if __name__ == "__main__":
    main()
