#!/usr/bin/env python3
"""
交易引擎CLI工具
提供命令行接口，替代freqtrade命令行工具
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

from src.quantsys.execution.execution_manager import ExecutionManager
from src.quantsys.trading_engine.api.server import TradingAPIServer
from src.quantsys.trading_engine.core.backtest_engine import BacktestEngine
from src.quantsys.trading_engine.core.data_provider import DataProvider
from src.quantsys.trading_engine.core.trading_bot import TradingBot

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_config(config_path: str) -> Dict[str, Any]:
    """加载配置文件"""
    path = Path(config_path)
    if not path.exists():
        logger.error(f"配置文件不存在: {config_path}")
        sys.exit(1)
    
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_strategy(strategy_name: str, config: Dict[str, Any]) -> Any:
    """动态加载策略"""
    try:
        # 尝试从user_data/strategies导入
        import importlib
        module_name = f"user_data.strategies.{strategy_name}"
        module = importlib.import_module(module_name)
        strategy_class = getattr(module, strategy_name)
        return strategy_class(config.get("strategy", {}))
    except Exception as e:
        logger.error(f"加载策略失败: {e}")
        sys.exit(1)


def cmd_trade(args):
    """交易命令"""
    config = load_config(args.config)
    strategy = load_strategy(args.strategy, config)
    
    # 初始化组件
    data_provider = DataProvider(config.get("data", {}))
    execution_manager = None
    
    if not config.get("dry_run", True):
        execution_manager = ExecutionManager(
            config=config,
            readiness=None,
            risk_engine=None,
        )
    
    # 创建交易机器人
    bot = TradingBot(
        strategy=strategy,
        config=config,
        data_provider=data_provider,
        execution_manager=execution_manager,
    )
    
    # 启动机器人
    bot.start()
    
    # 获取交易对列表
    pairs = config.get("exchange", {}).get("pair_whitelist", [])
    if not pairs:
        pairs = data_provider.get_available_pairs()
    
    logger.info(f"开始交易，交易对: {pairs}")
    
    try:
        import time
        while True:
            for pair in pairs:
                bot.process(pair)
            time.sleep(60)  # 每分钟处理一次
    except KeyboardInterrupt:
        logger.info("收到停止信号")
        bot.stop()


def cmd_backtest(args):
    """回测命令"""
    config = load_config(args.config)
    strategy = load_strategy(args.strategy, config)
    
    # 初始化组件
    data_provider = DataProvider(config.get("data", {}))
    
    # 创建回测引擎
    backtest_config = {
        "starting_balance": args.starting_balance or config.get("starting_balance", 1000),
        "stake_amount": config.get("stake_amount", 0.01),
        "max_open_trades": config.get("max_open_trades", 3),
    }
    
    engine = BacktestEngine(
        strategy=strategy,
        data_provider=data_provider,
        config=backtest_config,
    )
    
    # 获取交易对
    pairs = args.pairs or config.get("exchange", {}).get("pair_whitelist", [])
    if not pairs:
        pairs = data_provider.get_available_pairs()
    
    # 解析时间范围
    timerange = None
    if args.timerange:
        # 支持格式: "20240101-20240131" 或 "30d"
        if "-" in args.timerange:
            start_str, end_str = args.timerange.split("-")
            from datetime import datetime
            start = datetime.strptime(start_str, "%Y%m%d")
            end = datetime.strptime(end_str, "%Y%m%d")
            timerange = (start, end)
        else:
            timerange = (args.timerange, None)
    
    # 运行回测
    logger.info(f"开始回测: {pairs}, timerange: {timerange}")
    results = engine.run(pairs=pairs, timerange=timerange)
    
    # 输出结果
    print("\n" + "="*50)
    print("回测结果")
    print("="*50)
    print(f"初始资金: {results.get('initial_balance', 0):.2f}")
    print(f"最终资金: {results.get('final_balance', 0):.2f}")
    print(f"总盈亏: {results.get('total_profit', 0):.2f} ({results.get('total_profit_pct', 0):.2f}%)")
    print(f"总交易数: {results.get('total_trades', 0)}")
    print(f"盈利交易: {results.get('winning_trades', 0)}")
    print(f"亏损交易: {results.get('losing_trades', 0)}")
    print(f"胜率: {results.get('win_rate', 0):.2f}%")
    print(f"平均盈利: {results.get('avg_win', 0):.2f}")
    print(f"平均亏损: {results.get('avg_loss', 0):.2f}")
    print(f"盈亏比: {results.get('profit_factor', 0):.2f}")
    print(f"最大回撤: {results.get('max_drawdown', 0):.2f} ({results.get('max_drawdown_pct', 0):.2f}%)")
    print("="*50)
    
    # 保存结果
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        logger.info(f"回测结果已保存: {args.output}")


def cmd_webserver(args):
    """Web服务器命令"""
    config = load_config(args.config)
    strategy = load_strategy(args.strategy, config)
    
    # 初始化组件
    data_provider = DataProvider(config.get("data", {}))
    execution_manager = None
    
    if not config.get("dry_run", True):
        execution_manager = ExecutionManager(
            config=config,
            readiness=None,
            risk_engine=None,
        )
    
    # 创建交易机器人
    bot = TradingBot(
        strategy=strategy,
        config=config,
        data_provider=data_provider,
        execution_manager=execution_manager,
    )
    
    # 创建API服务器
    api_config = config.get("api_server", {})
    server = TradingAPIServer(trading_bot=bot, config=api_config)
    
    # 启动服务器
    logger.info("启动Web API服务器...")
    server.run(debug=args.debug)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="QuantSys Trading Engine CLI")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 交易命令
    trade_parser = subparsers.add_parser("trade", help="开始交易")
    trade_parser.add_argument("--config", required=True, help="配置文件路径")
    trade_parser.add_argument("--strategy", required=True, help="策略名称")
    
    # 回测命令
    backtest_parser = subparsers.add_parser("backtest", help="运行回测")
    backtest_parser.add_argument("--config", required=True, help="配置文件路径")
    backtest_parser.add_argument("--strategy", required=True, help="策略名称")
    backtest_parser.add_argument("--pairs", nargs="+", help="交易对列表")
    backtest_parser.add_argument("--timerange", help="时间范围，如: 20240101-20240131 或 30d")
    backtest_parser.add_argument("--starting-balance", type=float, help="初始资金")
    backtest_parser.add_argument("--output", help="结果输出文件")
    
    # Web服务器命令
    webserver_parser = subparsers.add_parser("webserver", help="启动Web API服务器")
    webserver_parser.add_argument("--config", required=True, help="配置文件路径")
    webserver_parser.add_argument("--strategy", required=True, help="策略名称")
    webserver_parser.add_argument("--debug", action="store_true", help="调试模式")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # 执行命令
    if args.command == "trade":
        cmd_trade(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    elif args.command == "webserver":
        cmd_webserver(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
