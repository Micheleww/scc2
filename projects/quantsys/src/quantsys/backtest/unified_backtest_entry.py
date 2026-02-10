#!/usr/bin/env python3
"""
QuantSys 统一回测入口

这是QuantSys系统的唯一回测入口点，整合了所有回测功能：
- 从PostgreSQL数据库读取数据回测
- 从本地文件（Feather/CSV/Parquet）读取数据回测
- Freqtrade集成回测
- 多策略对比回测
- 回测结果分析和可视化

使用方式：
    from src.quantsys.backtest.unified_backtest_entry import UnifiedBacktestEntry

    backtest = UnifiedBacktestEntry()
    results = backtest.run(
        strategy='eth_perp_trend_range.py',
        symbol='ETH-USDT',
        timeframe='1h',
        start_date='2021-01-01',
        end_date='2024-01-05',
        data_source='database'  # 或 'file'
    )
"""

import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

from src.quantsys.backtest.backtest_execution import BacktestExecutor
from src.quantsys.data.database_manager import DatabaseManager

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class UnifiedBacktestEntry:
    """
    QuantSys统一回测入口类

    这是系统唯一的回测入口点，提供统一的API接口来执行各种类型的回测。
    """

    def __init__(self, config_path: str | None = None):
        """
        初始化统一回测入口

        Args:
            config_path: 配置文件路径（可选），默认使用configs/config_backtest.json
        """
        self.project_root = project_root
        self.config_path = config_path or str(project_root / "configs" / "config_backtest.json")
        self.config = self._load_config()
        self.db_manager = None
        self.backtest_executor = None

    def _load_config(self) -> dict[str, Any]:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.warning(f"配置文件不存在: {self.config_path}，使用默认配置")
                return self._get_default_config()
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}，使用默认配置")
            return self._get_default_config()

    def _get_default_config(self) -> dict[str, Any]:
        """获取默认配置"""
        return {
            "backtest": {
                "initial_capital": 100000,
                "symbol": "ETH-USDT",
                "timeframe": "1h",
                "start_date": "2021-01-01",
                "end_date": "2024-01-05",
                "leverage": 3,
                "fee": 0.0005,
                "use_local_data_only": True,
            },
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "quant_trading",
                "user": "postgres",
                "password": "postgres",
            },
        }

    def run(
        self,
        strategy: str,
        symbol: str | None = None,
        timeframe: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        data_source: str = "database",
        data_path: str | None = None,
        initial_capital: float | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        执行回测（统一入口方法）

        Args:
            strategy: 策略文件路径或策略类名
            symbol: 交易对（如 'ETH-USDT'），默认从配置读取
            timeframe: 时间周期（如 '1h'），默认从配置读取
            start_date: 开始日期（格式：'YYYY-MM-DD'），默认从配置读取
            end_date: 结束日期（格式：'YYYY-MM-DD'），默认从配置读取
            data_source: 数据源类型，'database'（PostgreSQL）或 'file'（本地文件）
            data_path: 数据文件路径（当data_source='file'时必需）
            initial_capital: 初始资金，默认从配置读取
            **kwargs: 其他回测参数

        Returns:
            Dict: 回测结果，包含绩效指标、详细结果、风险指标等

        Example:
            >>> backtest = UnifiedBacktestEntry()
            >>> results = backtest.run(
            ...     strategy='src/quantsys/strategy/eth_perp_trend_range.py',
            ...     symbol='ETH-USDT',
            ...     timeframe='1h',
            ...     start_date='2021-01-01',
            ...     end_date='2024-01-05',
            ...     data_source='database'
            ... )
        """
        logger.info("=" * 60)
        logger.info("QuantSys 统一回测入口")
        logger.info("=" * 60)

        # 使用配置或参数
        symbol = symbol or self.config["backtest"].get("symbol", "ETH-USDT")
        timeframe = timeframe or self.config["backtest"].get("timeframe", "1h")
        start_date = start_date or self.config["backtest"].get("start_date", "2021-01-01")
        end_date = end_date or self.config["backtest"].get("end_date", "2024-01-05")
        initial_capital = initial_capital or self.config["backtest"].get("initial_capital", 100000)

        logger.info(f"策略: {strategy}")
        logger.info(f"交易对: {symbol}")
        logger.info(f"时间周期: {timeframe}")
        logger.info(f"时间范围: {start_date} 到 {end_date}")
        logger.info(f"初始资金: {initial_capital}")
        logger.info(f"数据源: {data_source}")

        # 根据数据源选择回测方法
        if data_source == "database":
            return self._run_from_database(
                strategy=strategy,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                **kwargs,
            )
        elif data_source == "file":
            if not data_path:
                raise ValueError("当data_source='file'时，必须提供data_path参数")
            return self._run_from_file(
                strategy=strategy,
                data_path=data_path,
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                **kwargs,
            )
        else:
            raise ValueError(f"不支持的数据源类型: {data_source}，支持的类型: 'database', 'file'")

    def _run_from_database(
        self,
        strategy: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_capital: float,
        **kwargs,
    ) -> dict[str, Any]:
        """从PostgreSQL数据库读取数据执行回测"""
        logger.info("\n从PostgreSQL数据库读取数据...")

        try:
            # 连接数据库
            if not self.db_manager:
                self.db_manager = DatabaseManager()

            # 转换symbol格式 (ETH-USDT -> ETH_USDT)
            db_symbol = symbol.replace("-", "_")

            # 转换日期
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")

            # 从数据库获取数据
            logger.info(f"查询数据: symbol={db_symbol}, timeframe={timeframe}")
            df = self.db_manager.get_trading_data(
                symbol=db_symbol, timeframe=timeframe, start_time=start_dt, end_time=end_dt
            )

            if df.empty:
                logger.warning("指定时间范围内没有数据，尝试获取所有可用数据...")
                df = self.db_manager.get_trading_data(symbol=db_symbol, timeframe=timeframe)

            if df.empty:
                raise ValueError(f"数据库中没有找到数据: {db_symbol} {timeframe}")

            logger.info(f"从数据库获取到 {len(df)} 行数据")
            logger.info(f"数据时间范围: {df.index.min()} 到 {df.index.max()}")

            # 保存到临时文件
            temp_file = self.project_root / "temp_backtest_data.feather"
            logger.info(f"保存数据到临时文件: {temp_file}")
            df.reset_index().to_feather(temp_file)

            # 执行回测
            results = self._execute_backtest(
                strategy=strategy,
                data_path=str(temp_file),
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                initial_capital=initial_capital,
                **kwargs,
            )

            # 清理临时文件
            if temp_file.exists():
                temp_file.unlink()
                logger.info(f"已删除临时文件: {temp_file}")

            return results

        except Exception as e:
            logger.error(f"数据库回测失败: {e}", exc_info=True)
            raise
        finally:
            if self.db_manager:
                try:
                    self.db_manager.disconnect()
                except:
                    pass

    def _run_from_file(
        self,
        strategy: str,
        data_path: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_capital: float,
        **kwargs,
    ) -> dict[str, Any]:
        """从本地文件读取数据执行回测"""
        logger.info("\n从本地文件读取数据...")

        data_path_full = Path(data_path)
        if not data_path_full.is_absolute():
            data_path_full = self.project_root / data_path

        if not data_path_full.exists():
            raise FileNotFoundError(f"数据文件不存在: {data_path_full}")

        logger.info(f"数据文件: {data_path_full}")
        file_size = data_path_full.stat().st_size / (1024 * 1024)  # MB
        logger.info(f"文件大小: {file_size:.2f} MB")

        # 验证文件格式
        if data_path_full.suffix not in [".feather", ".csv", ".parquet"]:
            raise ValueError(
                f"不支持的文件格式: {data_path_full.suffix}，支持: .feather, .csv, .parquet"
            )

        # 执行回测
        return self._execute_backtest(
            strategy=strategy,
            data_path=str(data_path_full),
            symbol=symbol,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            **kwargs,
        )

    def _execute_backtest(
        self,
        strategy: str,
        data_path: str,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        initial_capital: float,
        **kwargs,
    ) -> dict[str, Any]:
        """执行回测（内部方法）"""
        logger.info("\n开始执行回测...")

        try:
            # 初始化回测执行器
            if not self.backtest_executor:
                self.backtest_executor = BacktestExecutor()

            # 准备回测参数
            backtest_params = {
                "timerange": f"{start_date} - {end_date}",
                "starting_balance": initial_capital,
                "symbol": symbol,
                "timeframe": timeframe,
                **kwargs,
            }

            # 执行回测
            results = self.backtest_executor._execute_freqtrade_backtest(
                strategy_path=strategy, data_path=data_path, backtest_params=backtest_params
            )

            logger.info("\n" + "=" * 60)
            logger.info("回测完成")
            logger.info("=" * 60)

            return results

        except Exception as e:
            logger.error(f"回测执行失败: {e}", exc_info=True)
            raise

    def run_multiple(
        self,
        strategies: list[str],
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        data_source: str = "database",
        **kwargs,
    ) -> dict[str, dict[str, Any]]:
        """
        执行多策略对比回测

        Args:
            strategies: 策略文件路径列表
            symbol: 交易对
            timeframe: 时间周期
            start_date: 开始日期
            end_date: 结束日期
            data_source: 数据源类型
            **kwargs: 其他回测参数

        Returns:
            Dict: 每个策略的回测结果
        """
        logger.info(f"\n执行多策略对比回测，共 {len(strategies)} 个策略")

        results = {}
        for i, strategy in enumerate(strategies, 1):
            logger.info(f"\n[{i}/{len(strategies)}] 回测策略: {strategy}")
            try:
                result = self.run(
                    strategy=strategy,
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    data_source=data_source,
                    **kwargs,
                )
                results[strategy] = result
            except Exception as e:
                logger.error(f"策略 {strategy} 回测失败: {e}")
                results[strategy] = {"error": str(e)}

        return results

    def compare_results(self, results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        """
        对比多个回测结果

        Args:
            results: 多策略回测结果字典

        Returns:
            Dict: 对比分析结果
        """
        logger.info("\n对比回测结果...")

        comparison = {"strategies": list(results.keys()), "metrics": {}}

        # 提取关键指标
        metrics = ["夏普比率", "年化收益率", "最大回撤", "胜率", "交易次数"]

        for metric in metrics:
            comparison["metrics"][metric] = {}
            for strategy, result in results.items():
                if "error" not in result:
                    perf = result.get("绩效指标", {})
                    comparison["metrics"][metric][strategy] = perf.get(metric, None)

        # 找出最佳策略
        best_strategies = {}
        for metric in metrics:
            if metric in comparison["metrics"]:
                values = {k: v for k, v in comparison["metrics"][metric].items() if v is not None}
                if values:
                    if metric in ["最大回撤"]:
                        # 最大回撤越小越好
                        best = min(values.items(), key=lambda x: x[1])
                    else:
                        # 其他指标越大越好
                        best = max(values.items(), key=lambda x: x[1])
                    best_strategies[metric] = best

        comparison["best_strategies"] = best_strategies

        return comparison


def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(description="QuantSys 统一回测入口")
    parser.add_argument("--strategy", "-s", required=True, help="策略文件路径")
    parser.add_argument("--symbol", default=None, help="交易对（如 ETH-USDT）")
    parser.add_argument("--timeframe", "-t", default=None, help="时间周期（如 1h）")
    parser.add_argument("--start-date", default=None, help="开始日期（YYYY-MM-DD）")
    parser.add_argument("--end-date", default=None, help="结束日期（YYYY-MM-DD）")
    parser.add_argument(
        "--data-source",
        choices=["database", "file"],
        default="database",
        help="数据源类型：database（PostgreSQL）或 file（本地文件）",
    )
    parser.add_argument(
        "--data-path", default=None, help="数据文件路径（当data-source=file时必需）"
    )
    parser.add_argument("--initial-capital", type=float, default=None, help="初始资金")
    parser.add_argument("--output", "-o", default=None, help="结果输出文件路径（JSON格式）")
    parser.add_argument("--config", "-c", default=None, help="配置文件路径")

    args = parser.parse_args()

    # 创建回测入口
    backtest = UnifiedBacktestEntry(config_path=args.config)

    # 执行回测
    try:
        results = backtest.run(
            strategy=args.strategy,
            symbol=args.symbol,
            timeframe=args.timeframe,
            start_date=args.start_date,
            end_date=args.end_date,
            data_source=args.data_source,
            data_path=args.data_path,
            initial_capital=args.initial_capital,
        )

        # 输出结果
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"\n结果已保存到: {args.output}")
        else:
            print(json.dumps(results, ensure_ascii=False, indent=2))

        sys.exit(0)

    except Exception as e:
        logger.error(f"回测失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
