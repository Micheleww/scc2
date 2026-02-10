#!/usr/bin/env python3
"""
回测多个不同参数配置的策略，选择表现最好的保存到策略库
"""

import json
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
from eth_hourly_multi_factor import ETHHourlyMultiFactor
from strategy_library_manager import StrategyLibraryManager


def run_backtest_with_params(
    symbol, timeframe, days, n_factors, n_best, signal_type, use_dl_factors
):
    """
    使用指定参数运行回测

    Args:
        symbol: 交易对
        timeframe: 时间周期
        days: 回测天数
        n_factors: 生成因子数量
        n_best: 选择最佳因子数量
        signal_type: 信号类型
        use_dl_factors: 是否使用深度学习因子

    Returns:
        dict: 回测结果
    """
    logger.info(
        f"\n=== 开始回测: n_factors={n_factors}, n_best={n_best}, signal_type={signal_type}, dl_factors={use_dl_factors} ==="
    )

    # 1. 加载数据
    logger.info("正在加载数据...")
    data = collect_data("okx", symbol, timeframe, days)

    if data is None:
        logger.error("无法加载数据，回测失败")
        return None

    logger.info(f"数据加载完成，数据形状: {data.shape}")

    # 2. 初始化策略
    strategy = ETHHourlyMultiFactor(timeframe=timeframe)

    # 3. 加载数据到策略
    strategy.load_data(data)

    # 4. 运行策略回测
    results = strategy.run_full_pipeline(
        n_factors=n_factors,
        n_best=n_best,
        model_type="ridge",  # 只使用ridge模型
        signal_type=signal_type,
        use_dl_factors=use_dl_factors,
    )

    # 5. 添加参数信息到结果
    results["params"] = {
        "symbol": symbol,
        "timeframe": timeframe,
        "days": days,
        "n_factors": n_factors,
        "n_best": n_best,
        "signal_type": signal_type,
        "use_dl_factors": use_dl_factors,
    }

    # 6. 输出简要结果
    logger.info(
        f"回测完成，夏普比率: {results['performance_metrics']['sharpe_ratio']:.4f}, 最大回撤: {results['performance_metrics']['max_drawdown']:.4f}"
    )

    return results


def main():
    """
    主函数
    """
    logger.info("=== 回测多个策略配置 ===")

    # 配置参数
    symbol = "ETH/USDT"
    timeframe = "1h"
    days = 60

    # 定义要测试的参数组合
    param_combinations = [
        # (n_factors, n_best, signal_type, use_dl_factors)
        (50, 15, "rank", True),
        (50, 20, "rank", True),
        (50, 15, "continuous", True),
        (70, 20, "rank", True),
        (70, 25, "rank", True),
        (50, 15, "rank", False),
        (50, 20, "rank", False),
        (70, 20, "rank", False),
    ]

    # 保存所有回测结果
    all_results = []

    # 运行所有参数组合的回测
    for params in param_combinations:
        results = run_backtest_with_params(symbol, timeframe, days, *params)
        if results:
            all_results.append(results)

    # 选择表现最好的策略
    if not all_results:
        logger.error("所有回测都失败了")
        return

    # 根据夏普比率排序
    all_results.sort(key=lambda x: x["performance_metrics"]["sharpe_ratio"], reverse=True)

    # 显示所有策略的结果
    logger.info("\n=== 所有策略回测结果对比 ===")
    for i, result in enumerate(all_results[:5]):
        perf = result["performance_metrics"]
        params = result["params"]
        logger.info(
            f"策略 {i + 1}: 夏普比率={perf['sharpe_ratio']:.4f}, 最大回撤={perf['max_drawdown']:.4f}, 年化收益率={perf['annual_return']:.4f}"
        )
        logger.info(
            f"  参数: n_factors={params['n_factors']}, n_best={params['n_best']}, signal_type={params['signal_type']}, dl_factors={params['use_dl_factors']}"
        )

    # 选择最佳策略
    best_result = all_results[0]
    logger.info("\n=== 最佳策略 ===")
    logger.info(f"夏普比率: {best_result['performance_metrics']['sharpe_ratio']:.4f}")
    logger.info(f"最大回撤: {best_result['performance_metrics']['max_drawdown']:.4f}")
    logger.info(f"年化收益率: {best_result['performance_metrics']['annual_return']:.4f}")
    logger.info(f"胜率: {best_result['performance_metrics']['win_rate']:.4f}")
    logger.info(f"累计收益率: {best_result['performance_metrics']['cumulative_return']:.4f}")
    logger.info(f"参数: {best_result['params']}")

    # 保存最佳策略到策略库
    strategy_library = StrategyLibraryManager()

    # 生成策略名称
    strategy_name = f"best_ridge_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 保存策略
    model_data = {
        "model": best_result["model"],
        "model_type": "ridge",
        "best_factors": best_result["best_factors"],
        "feature_importance": best_result["feature_importance"],
        "performance_metrics": best_result["performance_metrics"],
        "train_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": best_result["params"],
        "scaler": best_result["model"].scaler if hasattr(best_result["model"], "scaler") else None,
    }

    strategy_id = strategy_library.save_strategy(model_data, strategy_name)
    logger.info("\n=== 最佳策略已保存到策略库 ===")
    logger.info(f"策略ID: {strategy_id}")
    logger.info(f"策略名称: {strategy_name}")

    # 生成实盘配置
    live_config = {
        "exchange": {
            "name": "okx",
            "api_key": "your_api_key",
            "api_secret": "your_api_secret",
            "api_passphrase": "your_api_passphrase",
        },
        "strategy": {
            "symbol": "ETH-USDT-SWAP",
            "timeframe": "1h",
            "strategy_id": strategy_id,
            "update_interval": 3600,
            "use_dl_factors": best_result["params"]["use_dl_factors"],
            "n_factors": best_result["params"]["n_factors"],
            "n_best": best_result["params"]["n_best"],
            "signal_type": best_result["params"]["signal_type"],
            "leverage": 10,
            "base_order_amount": 10,
        },
        "risk": {"max_single_order_amount": 10, "max_daily_loss": 50, "max_position_amount": 100},
    }

    # 保存实盘配置
    config_path = f"live_config_{strategy_id}.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(live_config, f, indent=2, ensure_ascii=False)

    logger.info("\n=== 实盘配置已生成 ===")
    logger.info(f"配置文件: {config_path}")
    logger.info("使用以下命令运行实盘:")
    logger.info(f"python run_strategy_from_library.py --config {config_path}")

    return best_result


if __name__ == "__main__":
    main()
