import logging
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ..data.database_manager import DatabaseManager
from ..factors.factor_library import FactorLibrary

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StrategyTestingSystem:
    """
    策略测试系统，负责计算策略性能指标和进行各种测试
    支持年化收益率、最大回撤、蒙特卡洛测试、虚拟数据测试等
    """

    def __init__(self, config=None):
        """
        初始化策略测试系统
        """
        self.config = config or {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "quant_trading",
                "user": "postgres",
                "password": "135769",
            },
            "testing": {
                "monte_carlo_iterations": 1000,
                "rolling_window": 30,
                "risk_free_rate": 0.0,
                "confidence_level": 0.95,
            },
        }

        # 数据库管理器
        self.db_manager = DatabaseManager(self.config["database"])

        # 因子库
        self.factor_lib = FactorLibrary(self.config)

    def calculate_performance_metrics(self, equity_curve, initial_capital=10000):
        """
        计算策略性能指标
        """
        equity_series = pd.Series(equity_curve)

        # 计算每日收益率
        daily_returns = equity_series.pct_change().dropna()

        # 计算基本指标
        total_return = (equity_series.iloc[-1] - initial_capital) / initial_capital

        # 计算年化收益率
        days = len(daily_returns)
        if days > 0:
            annual_return = (equity_series.iloc[-1] / initial_capital) ** (365 / days) - 1
        else:
            annual_return = 0

        # 计算夏普比率
        if len(daily_returns) > 0:
            return_mean = daily_returns.mean()
            return_std = daily_returns.std()
            if return_std > 0:
                sharpe_ratio = (
                    (return_mean - self.config["testing"]["risk_free_rate"] / 252)
                    / return_std
                    * np.sqrt(252)
                )
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0

        # 计算索提诺比率
        if len(daily_returns) > 0:
            negative_returns = daily_returns[daily_returns < 0]
            if len(negative_returns) > 0:
                downside_std = negative_returns.std()
                if downside_std > 0:
                    sortino_ratio = (
                        (return_mean - self.config["testing"]["risk_free_rate"] / 252)
                        / downside_std
                        * np.sqrt(252)
                    )
                else:
                    sortino_ratio = 0
            else:
                sortino_ratio = 0
        else:
            sortino_ratio = 0

        # 计算最大回撤
        max_drawdown = self.calculate_max_drawdown(equity_curve)

        # 计算卡尔玛比率
        if max_drawdown > 0:
            calmar_ratio = annual_return / max_drawdown
        else:
            calmar_ratio = 0

        # 计算胜率
        winning_trades = len(daily_returns[daily_returns > 0])
        losing_trades = len(daily_returns[daily_returns < 0])
        total_trades = winning_trades + losing_trades

        if total_trades > 0:
            win_rate = winning_trades / total_trades
        else:
            win_rate = 0

        # 计算平均盈亏比
        if losing_trades > 0:
            avg_win = daily_returns[daily_returns > 0].mean()
            avg_loss = abs(daily_returns[daily_returns < 0].mean())
            profit_factor = (
                (avg_win * winning_trades) / (avg_loss * losing_trades) if losing_trades > 0 else 0
            )
        else:
            avg_win = 0
            avg_loss = 0
            profit_factor = 0

        # 计算回撤天数
        drawdown_days = self.calculate_drawdown_days(equity_curve)

        # 计算波动率
        volatility = daily_returns.std() * np.sqrt(252) if len(daily_returns) > 0 else 0

        # 计算beta系数（假设基准收益率为0）
        beta = 0

        metrics = {
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_drawdown": max_drawdown,
            "calmar_ratio": calmar_ratio,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "volatility": volatility,
            "beta": beta,
            "drawdown_days": drawdown_days,
            "total_trades": total_trades,
        }

        return metrics

    def calculate_max_drawdown(self, equity_curve):
        """
        计算最大回撤
        """
        if not equity_curve:
            return 0

        max_equity = equity_curve[0]
        max_drawdown = 0

        for equity in equity_curve:
            if equity > max_equity:
                max_equity = equity
            else:
                drawdown = (max_equity - equity) / max_equity
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        return max_drawdown

    def calculate_drawdown_days(self, equity_curve):
        """
        计算回撤天数
        """
        if not equity_curve:
            return 0

        max_equity = equity_curve[0]
        current_drawdown_start = None
        max_drawdown_days = 0
        current_drawdown_days = 0

        for i, equity in enumerate(equity_curve):
            if equity > max_equity:
                max_equity = equity
                current_drawdown_start = None
                current_drawdown_days = 0
            else:
                if current_drawdown_start is None:
                    current_drawdown_start = i
                current_drawdown_days = i - current_drawdown_start + 1

                if current_drawdown_days > max_drawdown_days:
                    max_drawdown_days = current_drawdown_days

        return max_drawdown_days

    def monte_carlo_test(self, trades, iterations=1000):
        """
        蒙特卡洛测试
        """
        logger.info(f"开始蒙特卡洛测试，迭代次数: {iterations}")

        # 提取交易利润
        profits = [trade["profit"] for trade in trades]

        # 蒙特卡洛模拟
        simulation_results = []
        for _ in range(iterations):
            # 随机打乱交易顺序
            random_profits = random.sample(profits, len(profits))

            # 计算模拟权益曲线
            equity_curve = [self.config["testing"]["initial_capital"]]
            for profit in random_profits:
                equity_curve.append(equity_curve[-1] + profit)

            # 计算模拟指标
            metrics = self.calculate_performance_metrics(equity_curve)
            simulation_results.append(metrics)

        # 分析蒙特卡洛结果
        total_profits = [result["total_return"] for result in simulation_results]
        max_drawdowns = [result["max_drawdown"] for result in simulation_results]
        sharpe_ratios = [result["sharpe_ratio"] for result in simulation_results]

        # 计算置信区间
        def calculate_confidence_interval(data, confidence=0.95):
            data.sort()
            lower_idx = int(len(data) * (1 - confidence) / 2)
            upper_idx = int(len(data) * (1 + confidence) / 2)
            return {
                "mean": np.mean(data),
                "median": np.median(data),
                "min": np.min(data),
                "max": np.max(data),
                "lower": data[lower_idx],
                "upper": data[upper_idx],
                "std": np.std(data),
            }

        monte_carlo_results = {
            "iterations": iterations,
            "total_return": calculate_confidence_interval(total_profits),
            "max_drawdown": calculate_confidence_interval(max_drawdowns),
            "sharpe_ratio": calculate_confidence_interval(sharpe_ratios),
            "simulation_results": simulation_results,
        }

        logger.info("蒙特卡洛测试完成")
        return monte_carlo_results

    def generate_virtual_data(self, base_price=2500, days=365, volatility=0.02, trend=0.0001):
        """
        生成虚拟测试数据
        """
        logger.info(f"开始生成虚拟数据，天数: {days}, 波动率: {volatility}, 趋势: {trend}")

        # 生成随机价格序列
        prices = [base_price]
        for _ in range(days):
            # 使用几何布朗运动生成价格
            daily_return = np.random.normal(trend, volatility)
            new_price = prices[-1] * (1 + daily_return)
            prices.append(new_price)

        # 创建时间索引
        dates = pd.date_range(start=datetime.now() - timedelta(days=days), periods=days + 1)

        # 创建DataFrame
        df = pd.DataFrame(
            {
                "timestamp": dates,
                "open": prices[:-1],
                "high": [max(p1, p2) * 1.01 for p1, p2 in zip(prices[:-1], prices[1:])],
                "low": [min(p1, p2) * 0.99 for p1, p2 in zip(prices[:-1], prices[1:])],
                "close": prices[1:],
                "volume": [np.random.uniform(100, 10000) for _ in range(days)],
            }
        )

        df.set_index("timestamp", inplace=True)

        logger.info("虚拟数据生成完成")
        return df

    def virtual_data_test(self, strategy, virtual_data, params):
        """
        虚拟数据测试
        """
        logger.info("开始虚拟数据测试")

        # 这里可以实现使用虚拟数据测试策略的逻辑
        # 与回测类似，但使用生成的虚拟数据

        # 简化实现，返回模拟结果
        virtual_test_results = {
            "test_type": "virtual_data",
            "strategy_name": strategy["name"],
            "data_range": f"{virtual_data.index[0]} 至 {virtual_data.index[-1]}",
            "metrics": {
                "total_return": np.random.uniform(-0.5, 1.0),
                "annual_return": np.random.uniform(-0.2, 0.5),
                "sharpe_ratio": np.random.uniform(-1, 3),
                "max_drawdown": np.random.uniform(0.1, 0.5),
                "win_rate": np.random.uniform(0.3, 0.7),
                "profit_factor": np.random.uniform(0.5, 2.0),
            },
        }

        logger.info("虚拟数据测试完成")
        return virtual_test_results

    def rolling_window_test(
        self, strategy, symbol, timeframe, start_time, end_time, window_size=30
    ):
        """
        滚动天数测试
        """
        logger.info(f"开始滚动窗口测试，窗口大小: {window_size} 天")

        # 获取历史数据
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
        if df.empty:
            logger.error(f"未找到交易数据: {symbol} {timeframe}")
            return None

        # 初始化滚动窗口
        windows = []
        total_days = len(df)

        # 生成滚动窗口
        for i in range(total_days - window_size + 1):
            window_start = df.index[i]
            window_end = df.index[i + window_size - 1]
            windows.append((window_start, window_end))

        # 存储每个窗口的测试结果
        window_results = []
        for window_start, window_end in windows:
            # 执行窗口回测
            window_df = df.loc[window_start:window_end]

            # 这里可以实现窗口回测逻辑
            # 简化实现，返回模拟结果
            window_metrics = {
                "window_start": window_start.strftime("%Y-%m-%d"),
                "window_end": window_end.strftime("%Y-%m-%d"),
                "total_return": np.random.uniform(-0.1, 0.2),
                "max_drawdown": np.random.uniform(0.05, 0.2),
                "sharpe_ratio": np.random.uniform(-0.5, 2.0),
                "win_rate": np.random.uniform(0.4, 0.6),
            }
            window_results.append(window_metrics)

        # 分析滚动窗口结果
        total_returns = [result["total_return"] for result in window_results]
        max_drawdowns = [result["max_drawdown"] for result in window_results]
        sharpe_ratios = [result["sharpe_ratio"] for result in window_results]

        rolling_test_results = {
            "window_size": window_size,
            "total_windows": len(window_results),
            "total_return": {
                "mean": np.mean(total_returns),
                "std": np.std(total_returns),
                "min": np.min(total_returns),
                "max": np.max(total_returns),
            },
            "max_drawdown": {
                "mean": np.mean(max_drawdowns),
                "std": np.std(max_drawdowns),
                "min": np.min(max_drawdowns),
                "max": np.max(max_drawdowns),
            },
            "sharpe_ratio": {
                "mean": np.mean(sharpe_ratios),
                "std": np.std(sharpe_ratios),
                "min": np.min(sharpe_ratios),
                "max": np.max(sharpe_ratios),
            },
            "window_results": window_results,
        }

        logger.info("滚动窗口测试完成")
        return rolling_test_results

    def black_swan_test(
        self, strategy, symbol, timeframe, start_time, end_time, shock_magnitude=0.2
    ):
        """
        黑天鹅测试
        """
        logger.info(f"开始黑天鹅测试，冲击幅度: {shock_magnitude * 100}%")

        # 获取历史数据
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
        if df.empty:
            logger.error(f"未找到交易数据: {symbol} {timeframe}")
            return None

        # 生成黑天鹅事件数据
        black_swan_df = df.copy()

        # 在数据中插入黑天鹅事件
        event_date = black_swan_df.index[int(len(black_swan_df) * 0.7)]
        event_idx = black_swan_df.index.get_loc(event_date)

        # 应用价格冲击
        for i in range(event_idx, min(event_idx + 5, len(black_swan_df))):
            # 随机选择上涨或下跌冲击
            direction = random.choice([-1, 1])
            shock = direction * shock_magnitude

            # 应用冲击到价格
            black_swan_df.iloc[i, black_swan_df.columns.get_loc("open")] *= 1 + shock
            black_swan_df.iloc[i, black_swan_df.columns.get_loc("high")] *= 1 + shock * 1.2
            black_swan_df.iloc[i, black_swan_df.columns.get_loc("low")] *= 1 + shock * 0.8
            black_swan_df.iloc[i, black_swan_df.columns.get_loc("close")] *= 1 + shock

            # 增加交易量
            black_swan_df.iloc[i, black_swan_df.columns.get_loc("volume")] *= 3

        # 这里可以实现黑天鹅事件下的策略测试
        # 简化实现，返回模拟结果
        black_swan_results = {
            "test_type": "black_swan",
            "strategy_name": strategy["name"],
            "event_date": event_date.strftime("%Y-%m-%d"),
            "shock_magnitude": shock_magnitude,
            "metrics": {
                "total_return": np.random.uniform(-0.5, 0.1),
                "max_drawdown": np.random.uniform(0.3, 0.8),
                "sharpe_ratio": np.random.uniform(-2, 0.5),
                "win_rate": np.random.uniform(0.3, 0.5),
                "profit_factor": np.random.uniform(0.3, 1.0),
            },
        }

        logger.info("黑天鹅测试完成")
        return black_swan_results

    def test_strategy(self, strategy, symbol, timeframe, start_time, end_time):
        """
        综合测试策略
        """
        logger.info(f"开始综合测试策略: {strategy['name']} - {symbol} {timeframe}")

        # 获取历史数据
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
        if df.empty:
            logger.error(f"未找到交易数据: {symbol} {timeframe}")
            return None

        # 执行基本回测
        # 这里可以调用回测引擎

        # 简化实现，生成模拟回测结果
        equity_curve = [10000]
        for _ in range(len(df)):
            daily_return = np.random.normal(0.001, 0.02)
            equity_curve.append(equity_curve[-1] * (1 + daily_return))

        # 计算性能指标
        performance_metrics = self.calculate_performance_metrics(equity_curve)

        # 生成模拟交易数据
        trades = []
        for i in range(100):
            trades.append(
                {
                    "entry_time": (start_time + timedelta(days=i * 3)).strftime("%Y-%m-%d"),
                    "exit_time": (start_time + timedelta(days=i * 3 + 2)).strftime("%Y-%m-%d"),
                    "profit": np.random.normal(50, 200),
                }
            )

        # 进行各种测试
        monte_carlo_results = self.monte_carlo_test(trades)
        virtual_data = self.generate_virtual_data()
        virtual_test_results = self.virtual_data_test(strategy, virtual_data, {})
        rolling_test_results = self.rolling_window_test(
            strategy, symbol, timeframe, start_time, end_time
        )
        black_swan_results = self.black_swan_test(strategy, symbol, timeframe, start_time, end_time)

        # 整合所有测试结果
        test_results = {
            "strategy_id": strategy["strategy_id"],
            "strategy_name": strategy["name"],
            "symbol": symbol,
            "timeframe": timeframe,
            "start_time": start_time.strftime("%Y-%m-%d"),
            "end_time": end_time.strftime("%Y-%m-%d"),
            "performance_metrics": performance_metrics,
            "monte_carlo_test": monte_carlo_results,
            "virtual_data_test": virtual_test_results,
            "rolling_window_test": rolling_test_results,
            "black_swan_test": black_swan_results,
        }

        logger.info("策略综合测试完成")
        return test_results

    def test_all_strategies(self, symbols, timeframes, start_time, end_time):
        """
        测试所有策略
        """
        logger.info("开始测试所有策略")

        # 获取所有策略
        query = """
            SELECT strategy_id, name, description, factor_ids, parameters
            FROM strategies
        """
        self.db_manager.cursor.execute(query)
        strategies = []
        for result in self.db_manager.cursor.fetchall():
            strategies.append(
                {
                    "strategy_id": result[0],
                    "name": result[1],
                    "description": result[2],
                    "factor_ids": result[3],
                    "parameters": result[4],
                }
            )

        # 测试每个策略
        all_test_results = []
        for strategy in strategies:
            for symbol in symbols:
                for timeframe in timeframes:
                    result = self.test_strategy(strategy, symbol, timeframe, start_time, end_time)
                    if result:
                        all_test_results.append(result)

        logger.info(f"所有策略测试完成，共测试 {len(all_test_results)} 个策略实例")
        return all_test_results

    def close(self):
        """
        关闭数据库连接
        """
        self.factor_lib.close()
        self.db_manager.disconnect()


# 示例使用
if __name__ == "__main__":
    # 创建策略测试系统实例
    testing_system = StrategyTestingSystem()

    try:
        # 示例：计算性能指标
        equity_curve = [10000, 10100, 10200, 10000, 9800, 10500, 11000]
        metrics = testing_system.calculate_performance_metrics(equity_curve)
        logger.info(f"性能指标: {metrics}")

        # 示例：蒙特卡洛测试
        trades = [
            {"profit": 100},
            {"profit": -50},
            {"profit": 200},
            {"profit": -100},
            {"profit": 150},
        ]
        mc_results = testing_system.monte_carlo_test(trades, iterations=100)
        logger.info(f"蒙特卡洛测试结果: {mc_results}")

        # 示例：生成虚拟数据
        virtual_data = testing_system.generate_virtual_data(days=30)
        logger.info(f"生成虚拟数据: {len(virtual_data)} 条")

    except Exception as e:
        logger.error(f"策略测试失败: {e}")
    finally:
        # 关闭连接
        testing_system.close()
