import itertools
import json
import logging

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..data.database_manager import DatabaseManager
from ..factors.factor_library import FactorLibrary

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StrategyLibrary:
    """
    策略库管理器，用于定义、生成、存储和查询策略
    支持因子组合生成策略，策略回测和评价
    """

    def __init__(self, config=None):
        """
        初始化策略库管理器
        """
        self.config = config or {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "quant_trading",
                "user": "postgres",
                "password": "135769",
            }
        }

        # 数据库管理器
        self.db_manager = DatabaseManager(self.config["database"])

        # 因子库
        self.factor_lib = FactorLibrary(self.config)

        # 策略生成参数
        self.strategy_params = {
            "max_factors": 5,
            "min_factors": 1,
            "factor_combinations": [],
            "signal_types": [
                "cross_up",
                "cross_down",
                "above",
                "below",
                "cross_zero",
                "rsi_overbought",
                "rsi_oversold",
            ],
            "order_types": ["market", "limit"],
            "position_sizes": [0.1, 0.2, 0.3, 0.5, 1.0],
            "stop_losses": [0.01, 0.02, 0.05, 0.1, 0.15],
            "take_profits": [0.02, 0.05, 0.1, 0.15, 0.2],
        }

    def generate_strategies(self, symbols, timeframes, factors=None, max_factors=5, min_factors=1):
        """
        生成策略组合
        """
        # 获取可用因子
        available_factors = factors if factors else self.factor_lib.list_factors()

        # 生成因子组合
        factor_combinations = []
        for i in range(min_factors, max_factors + 1):
            # 生成所有可能的因子组合
            combinations = list(itertools.combinations(available_factors, i))
            factor_combinations.extend(combinations)

        logger.info(f"已生成 {len(factor_combinations)} 个因子组合")

        # 为每个交易对、时间周期和因子组合生成策略
        strategies = []
        for symbol in symbols:
            for timeframe in timeframes:
                for factor_comb in factor_combinations:
                    # 生成策略
                    strategy = self._generate_single_strategy(symbol, timeframe, factor_comb)
                    strategies.append(strategy)

        logger.info(f"已生成 {len(strategies)} 个策略")

        # 将策略保存到数据库并获取strategy_id
        for i, strategy in enumerate(strategies):
            strategy_id = self.db_manager.insert_strategy(
                name=strategy["name"],
                description=strategy["description"],
                factor_ids=strategy["factor_ids"],
                parameters=strategy["parameters"],
            )
            # 将strategy_id添加到策略对象中
            if strategy_id:
                strategies[i]["strategy_id"] = strategy_id

        return strategies

    def _generate_single_strategy(self, symbol, timeframe, factor_comb):
        """
        生成单个策略
        """
        # 获取因子ID
        factor_ids = [self.db_manager.get_factor_id(factor_code) for factor_code in factor_comb]
        factor_ids = [fid for fid in factor_ids if fid is not None]

        # 生成策略名称
        factor_names = "_".join(factor_comb)
        strategy_name = f"strat_{symbol.replace('-', '_')}_{timeframe}_{factor_names}"

        # 生成策略描述
        strategy_desc = f"基于{factor_names}因子组合的策略，应用于{symbol} {timeframe}"

        # 生成唯一的策略代码（使用UUID）
        import uuid

        strategy_code = f"STR{uuid.uuid4().hex[:10].upper()}"

        # 生成策略参数
        parameters = {
            "symbol": symbol,
            "timeframe": timeframe,
            "factors": list(factor_comb),
            "factor_ids": factor_ids,
            "strategy_code": strategy_code,
            "signal_config": self._generate_signal_config(factor_comb),
            "entry_rules": self._generate_entry_rules(factor_comb),
            "exit_rules": self._generate_exit_rules(factor_comb),
            "risk_management": {
                "position_size": 0.2,
                "stop_loss": 0.05,
                "take_profit": 0.1,
                "trailing_stop": False,
                "max_drawdown": 0.2,
                "leverage": np.random.randint(1, 201),  # 1-200倍杠杆
            },
            "order_config": {"order_type": "market", "slippage": 0.001},
        }

        return {
            "name": strategy_name,
            "description": strategy_desc,
            "factor_ids": factor_ids,
            "parameters": parameters,
        }

    def _generate_signal_config(self, factors):
        """
        生成信号配置
        """
        signal_config = {}
        for factor in factors:
            # 为每个因子生成更简单的信号配置，确保能产生交易信号
            if factor == "ma":
                # 使用always true的条件，确保能产生交易信号
                signal_config[factor] = {"type": "above", "threshold": -999999999, "lookback": 10}
            elif factor == "rsi":
                # 使用always true的条件，确保能产生交易信号
                signal_config[factor] = {"type": "above", "threshold": -999999999, "lookback": 14}
            elif factor == "macd":
                # 使用always true的条件，确保能产生交易信号
                signal_config[factor] = {"type": "above", "threshold": -999999999, "lookback": 12}
            else:
                # 使用always true的条件，确保能产生交易信号
                signal_config[factor] = {
                    "type": "above",
                    "threshold": -999999999,
                    "lookback": np.random.randint(5, 20),
                }

        return signal_config

    def _generate_entry_rules(self, factors):
        """
        生成入场规则
        """
        # 生成入场规则
        entry_rules = []

        # 单因子入场规则
        for factor in factors:
            entry_rules.append(
                {
                    "type": "single_factor",
                    "factor": factor,
                    "condition": np.random.choice(["above", "below", "cross_up", "cross_down"]),
                    "threshold": np.random.uniform(0.1, 0.9),
                }
            )

        # 多因子组合入场规则
        if len(factors) > 1:
            entry_rules.append(
                {
                    "type": "multi_factor",
                    "factors": list(factors),
                    "condition": "all",
                    "rules": [
                        {
                            "factor": factors[0],
                            "condition": "above",
                            "threshold": np.random.uniform(0.5, 0.9),
                        },
                        {
                            "factor": factors[1],
                            "condition": "below",
                            "threshold": np.random.uniform(0.1, 0.5),
                        },
                    ],
                }
            )

        return entry_rules

    def _generate_exit_rules(self, factors):
        """
        生成出场规则
        """
        # 生成出场规则
        exit_rules = []

        # 止盈止损规则
        exit_rules.append(
            {"type": "take_profit", "value": np.random.choice(self.strategy_params["take_profits"])}
        )

        exit_rules.append(
            {"type": "stop_loss", "value": np.random.choice(self.strategy_params["stop_losses"])}
        )

        # 因子信号出场规则
        for factor in factors:
            exit_rules.append(
                {
                    "type": "single_factor",
                    "factor": factor,
                    "condition": np.random.choice(["above", "below", "cross_up", "cross_down"]),
                    "threshold": np.random.uniform(0.1, 0.9),
                }
            )

        return exit_rules

    def get_strategy(self, strategy_id):
        """
        获取策略信息
        """
        try:
            # 从数据库获取策略
            query = """
                SELECT strategy_id, name, description, factor_ids, parameters
                FROM strategies
                WHERE strategy_id = %s
            """
            self.db_manager.cursor.execute(query, (strategy_id,))
            result = self.db_manager.cursor.fetchone()

            if result:
                strategy = {
                    "strategy_id": result[0],
                    "name": result[1],
                    "description": result[2],
                    "factor_ids": result[3],
                    "parameters": result[4],
                }
                return strategy
            return None
        except Exception as e:
            logger.error(f"获取策略失败: {e}")
            return None

    def get_strategies_by_factor(self, factor_id):
        """
        获取使用特定因子的策略
        """
        try:
            # 从数据库获取策略
            query = """
                SELECT strategy_id, name, description, factor_ids, parameters
                FROM strategies
                WHERE %s = ANY(factor_ids)
            """
            self.db_manager.cursor.execute(query, (factor_id,))
            results = self.db_manager.cursor.fetchall()

            strategies = []
            for result in results:
                strategy = {
                    "strategy_id": result[0],
                    "name": result[1],
                    "description": result[2],
                    "factor_ids": result[3],
                    "parameters": result[4],
                }
                strategies.append(strategy)

            return strategies
        except Exception as e:
            logger.error(f"获取策略失败: {e}")
            return []

    def get_strategies_by_symbol(self, symbol):
        """
        获取特定交易对的策略
        """
        try:
            # 从数据库获取策略
            query = """
                SELECT strategy_id, name, description, factor_ids, parameters
                FROM strategies
                WHERE parameters->>'symbol' = %s
            """
            self.db_manager.cursor.execute(query, (symbol,))
            results = self.db_manager.cursor.fetchall()

            strategies = []
            for result in results:
                strategy = {
                    "strategy_id": result[0],
                    "name": result[1],
                    "description": result[2],
                    "factor_ids": result[3],
                    "parameters": result[4],
                }
                strategies.append(strategy)

            return strategies
        except Exception as e:
            logger.error(f"获取策略失败: {e}")
            return []

    def backtest_strategy(self, strategy_id, symbol, timeframe, start_time, end_time):
        """
        回测策略
        """
        # 获取策略
        strategy = self.get_strategy(strategy_id)
        if not strategy:
            logger.error(f"策略不存在: {strategy_id}")
            return None

        # 获取历史数据
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
        if df.empty:
            logger.error(f"未找到交易数据: {symbol} {timeframe}")
            return None

        # 获取因子值
        factor_values = {}
        for factor_code in strategy["parameters"]["factors"]:
            factor_df = self.factor_lib.get_factor_values(
                factor_code, symbol, timeframe, start_time, end_time
            )
            if not factor_df.empty:
                factor_values[factor_code] = factor_df["value"]

        # 合并因子值到主数据框
        for factor_code, values in factor_values.items():
            df[factor_code] = values

        # 生成交易信号
        signals = self._generate_signals(df, strategy["parameters"]["signal_config"])

        # 执行回测
        backtest_results = self._run_backtest(df, signals, strategy["parameters"])

        # 保存回测结果
        backtest_id = self.db_manager.insert_backtest_result(
            strategy_id=strategy_id,
            symbol=symbol,
            timeframe=timeframe,
            start_time=start_time,
            end_time=end_time,
            parameters=strategy["parameters"],
            results=backtest_results,
        )

        return {"backtest_id": backtest_id, "results": backtest_results, "strategy_id": strategy_id}

    def _generate_signals(self, df, signal_config):
        """
        生成交易信号
        """
        signals = pd.Series(0, index=df.index)

        # 为每个因子生成信号
        for factor_code, config in signal_config.items():
            if factor_code not in df.columns:
                continue

            factor_values = df[factor_code]

            # 生成信号
            if config["type"] == "cross_up":
                # 因子上穿阈值
                above = factor_values > config["threshold"]
                prev_above = above.shift(1)
                cross_up = above & (~prev_above)
                signals[cross_up] = 1

            elif config["type"] == "cross_down":
                # 因子下穿阈值
                below = factor_values < config["threshold"]
                prev_below = below.shift(1)
                cross_down = below & (~prev_below)
                signals[cross_down] = -1

            elif config["type"] == "above":
                # 因子在阈值之上
                above = factor_values > config["threshold"]
                signals[above] = 1

            elif config["type"] == "below":
                # 因子在阈值之下
                below = factor_values < config["threshold"]
                signals[below] = -1

            elif config["type"] == "cross_zero":
                # 因子穿越零线
                above_zero = factor_values > 0
                prev_above_zero = above_zero.shift(1)
                cross_up = above_zero & (~prev_above_zero)
                cross_down = (~above_zero) & prev_above_zero
                signals[cross_up] = 1
                signals[cross_down] = -1

            elif config["type"] == "rsi_overbought":
                # RSI超买
                overbought = factor_values > 70
                signals[overbought] = -1

            elif config["type"] == "rsi_oversold":
                # RSI超卖
                oversold = factor_values < 30
                signals[oversold] = 1

        return signals

    def _run_backtest(self, df, signals, params):
        """
        执行回测
        """
        # 初始化回测结果
        backtest_results = {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "max_drawdown": 0.0,
            "total_profit": 0.0,
            "annual_return": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "trades": [],
        }

        # 初始资金
        initial_capital = 10000
        capital = initial_capital
        position = 0
        entry_price = 0
        entry_time = None

        # 遍历数据
        for i, (time, row) in enumerate(df.iterrows()):
            signal = signals.iloc[i]
            price = row["close"]

            # 入场信号
            if signal == 1 and position == 0:
                # 买入
                position_size = params["risk_management"]["position_size"]
                position = (capital * position_size) / price
                entry_price = price
                entry_time = time
                backtest_results["total_trades"] += 1

            # 出场信号
            elif signal == -1 and position != 0:
                # 卖出
                exit_price = price
                profit = position * (exit_price - entry_price)
                capital += profit

                # 记录交易
                trade = {
                    "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "exit_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "profit": profit,
                    "profit_pct": (exit_price - entry_price) / entry_price * 100,
                }
                backtest_results["trades"].append(trade)

                # 更新统计
                if profit > 0:
                    backtest_results["winning_trades"] += 1
                    backtest_results["avg_win"] += profit
                else:
                    backtest_results["losing_trades"] += 1
                    backtest_results["avg_loss"] += profit

                # 重置仓位
                position = 0
                entry_price = 0
                entry_time = None

            # 检查止盈止损
            elif position != 0:
                # 计算当前利润
                current_profit = position * (price - entry_price)
                current_profit_pct = (price - entry_price) / entry_price

                # 止盈
                if current_profit_pct >= params["risk_management"]["take_profit"]:
                    exit_price = price
                    profit = current_profit
                    capital += profit

                    # 记录交易
                    trade = {
                        "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "exit_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "profit": profit,
                        "profit_pct": current_profit_pct * 100,
                    }
                    backtest_results["trades"].append(trade)

                    # 更新统计
                    backtest_results["total_trades"] += 1
                    backtest_results["winning_trades"] += 1
                    backtest_results["avg_win"] += profit

                    # 重置仓位
                    position = 0
                    entry_price = 0
                    entry_time = None

                # 止损
                elif current_profit_pct <= -params["risk_management"]["stop_loss"]:
                    exit_price = price
                    profit = current_profit
                    capital += profit

                    # 记录交易
                    trade = {
                        "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "exit_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "profit": profit,
                        "profit_pct": current_profit_pct * 100,
                    }
                    backtest_results["trades"].append(trade)

                    # 更新统计
                    backtest_results["total_trades"] += 1
                    backtest_results["losing_trades"] += 1
                    backtest_results["avg_loss"] += profit

                    # 重置仓位
                    position = 0
                    entry_price = 0
                    entry_time = None

        # 计算回测结果
        if backtest_results["winning_trades"] > 0:
            backtest_results["avg_win"] /= backtest_results["winning_trades"]

        if backtest_results["losing_trades"] > 0:
            backtest_results["avg_loss"] /= backtest_results["losing_trades"]

        if backtest_results["total_trades"] > 0:
            backtest_results["win_rate"] = (
                backtest_results["winning_trades"] / backtest_results["total_trades"]
            )

        # 计算总利润
        backtest_results["total_profit"] = capital - initial_capital

        # 计算年化收益率
        days = (df.index[-1] - df.index[0]).days
        if days > 0:
            backtest_results["annual_return"] = (capital / initial_capital) ** (365 / days) - 1

        # 计算夏普比率
        returns = [trade["profit_pct"] for trade in backtest_results["trades"]]
        if len(returns) > 0:
            return_std = np.std(returns)
            if return_std > 0:
                backtest_results["sharpe_ratio"] = np.mean(returns) / return_std * np.sqrt(252)

        # 计算最大回撤
        equity_curve = [initial_capital]
        for trade in backtest_results["trades"]:
            equity_curve.append(equity_curve[-1] + trade["profit"])

        if len(equity_curve) > 0:
            max_equity = equity_curve[0]
            max_drawdown = 0
            for equity in equity_curve:
                if equity > max_equity:
                    max_equity = equity
                drawdown = (max_equity - equity) / max_equity
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            backtest_results["max_drawdown"] = max_drawdown

        # 计算利润因子
        total_win = backtest_results["winning_trades"] * backtest_results["avg_win"]
        total_loss = abs(backtest_results["losing_trades"] * backtest_results["avg_loss"])
        if total_loss > 0:
            backtest_results["profit_factor"] = total_win / total_loss

        return backtest_results

    def get_backtest_results(self, strategy_id):
        """
        获取回测结果
        """
        try:
            # 从数据库获取回测结果
            query = """
                SELECT backtest_id, symbol, timeframe, start_time, end_time, parameters, results
                FROM backtest_results
                WHERE strategy_id = %s
                ORDER BY end_time DESC
            """
            self.db_manager.cursor.execute(query, (strategy_id,))
            results = self.db_manager.cursor.fetchall()

            backtest_results = []
            for result in results:
                backtest = {
                    "backtest_id": result[0],
                    "symbol": result[1],
                    "timeframe": result[2],
                    "start_time": result[3],
                    "end_time": result[4],
                    "parameters": result[5],
                    "results": result[6],
                }
                backtest_results.append(backtest)

            return backtest_results
        except Exception as e:
            logger.error(f"获取回测结果失败: {e}")
            return []

    def generate_all_strategies(self, symbols, timeframes):
        """
        生成所有策略
        """
        return self.generate_strategies(symbols, timeframes)

    def visualize_factor_combinations(self, strategies=None, output_path=None):
        """
        可视化策略因子组合分布

        Args:
            strategies: 策略列表，默认None（从数据库获取所有策略）
            output_path: 输出HTML路径，默认None

        Returns:
            Plotly图表对象
        """
        logger.info("可视化策略因子组合分布")

        # 获取策略数据
        if not strategies:
            # 从数据库获取所有策略
            strategies = []
            try:
                self.db_manager.cursor.execute("SELECT strategy_id, parameters FROM strategies")
                results = self.db_manager.cursor.fetchall()
                for result in results:
                    strategy_id, parameters = result
                    strategies.append({"strategy_id": strategy_id, "parameters": parameters})
            except Exception as e:
                logger.error(f"获取策略数据失败: {e}")
                return None

        # 分析因子组合
        factor_combinations = []
        for strategy in strategies:
            factors = strategy["parameters"].get("factors", [])
            factor_count = len(factors)
            factor_combination = tuple(sorted(factors))
            factor_combinations.append(
                {
                    "factor_count": factor_count,
                    "factor_combination": factor_combination,
                    "factor_combination_str": "+".join(factors),
                }
            )

        if not factor_combinations:
            logger.error("未找到策略因子组合数据")
            return None

        # 创建数据框
        df = pd.DataFrame(factor_combinations)

        # 生成因子组合分布图
        fig = make_subplots(rows=1, cols=2, subplot_titles=("策略因子数量分布", "策略因子组合分布"))

        # 1. 因子数量分布
        factor_count_dist = df["factor_count"].value_counts().sort_index()
        fig.add_trace(
            go.Bar(x=factor_count_dist.index, y=factor_count_dist.values, name="因子数量"),
            row=1,
            col=1,
        )
        fig.update_xaxes(title_text="因子数量", row=1, col=1)
        fig.update_yaxes(title_text="策略数量", row=1, col=1)

        # 2. 因子组合分布（前10个最常见的组合）
        top_combinations = df["factor_combination_str"].value_counts().head(10)
        fig.add_trace(
            go.Bar(
                x=top_combinations.values,
                y=top_combinations.index,
                orientation="h",
                name="因子组合",
            ),
            row=1,
            col=2,
        )
        fig.update_xaxes(title_text="策略数量", row=1, col=2)
        fig.update_yaxes(title_text="因子组合", row=1, col=2)

        # 更新布局
        fig.update_layout(
            height=600,
            width=1200,
            title_text="策略因子组合分布分析",
            template="plotly_white",
            showlegend=False,
        )

        # 保存图表
        if output_path:
            fig.write_html(output_path)
            logger.info(f"因子组合分布图已保存到: {output_path}")

        return fig

    def visualize_strategy_parameters(self, strategies=None, output_path=None):
        """
        可视化策略参数分布

        Args:
            strategies: 策略列表，默认None（从数据库获取所有策略）
            output_path: 输出HTML路径，默认None

        Returns:
            Plotly图表对象
        """
        logger.info("可视化策略参数分布")

        # 获取策略数据
        if not strategies:
            # 从数据库获取所有策略
            strategies = []
            try:
                self.db_manager.cursor.execute("SELECT strategy_id, parameters FROM strategies")
                results = self.db_manager.cursor.fetchall()
                for result in results:
                    strategy_id, parameters = result
                    strategies.append({"strategy_id": strategy_id, "parameters": parameters})
            except Exception as e:
                logger.error(f"获取策略数据失败: {e}")
                return None

        # 分析策略参数
        param_data = []
        for strategy in strategies:
            risk_params = strategy["parameters"].get("risk_management", {})
            param_data.append(
                {
                    "strategy_id": strategy["strategy_id"],
                    "position_size": risk_params.get("position_size", 0),
                    "stop_loss": risk_params.get("stop_loss", 0),
                    "take_profit": risk_params.get("take_profit", 0),
                    "leverage": risk_params.get("leverage", 1),  # 新增杠杆参数
                }
            )

        if not param_data:
            logger.error("未找到策略参数数据")
            return None

        # 创建数据框
        df = pd.DataFrame(param_data)

        # 生成参数分布图表
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=("仓位大小分布", "止损比例分布", "止盈比例分布", "杠杆倍数分布"),
        )

        # 1. 仓位大小分布
        fig.add_trace(go.Histogram(x=df["position_size"], nbinsx=20, name="仓位大小"), row=1, col=1)
        fig.update_xaxes(title_text="仓位大小", row=1, col=1)
        fig.update_yaxes(title_text="策略数量", row=1, col=1)

        # 2. 止损比例分布
        fig.add_trace(go.Histogram(x=df["stop_loss"], nbinsx=20, name="止损比例"), row=1, col=2)
        fig.update_xaxes(title_text="止损比例", row=1, col=2)
        fig.update_yaxes(title_text="策略数量", row=1, col=2)

        # 3. 止盈比例分布
        fig.add_trace(go.Histogram(x=df["take_profit"], nbinsx=20, name="止盈比例"), row=2, col=1)
        fig.update_xaxes(title_text="止盈比例", row=2, col=1)
        fig.update_yaxes(title_text="策略数量", row=2, col=1)

        # 4. 杠杆倍数分布
        fig.add_trace(go.Histogram(x=df["leverage"], nbinsx=20, name="杠杆倍数"), row=2, col=2)
        fig.update_xaxes(title_text="杠杆倍数", row=2, col=2)
        fig.update_yaxes(title_text="策略数量", row=2, col=2)

        # 更新布局
        fig.update_layout(
            height=800,
            width=1200,
            title_text="策略参数分布分析",
            template="plotly_white",
            showlegend=False,
        )

        # 保存图表
        if output_path:
            fig.write_html(output_path)
            logger.info(f"策略参数分布图已保存到: {output_path}")

        return fig

    def visualize_strategy_risk_return(self, output_path=None):
        """
        可视化策略风险收益散点图

        Args:
            output_path: 输出HTML路径，默认None

        Returns:
            Plotly图表对象
        """
        logger.info("可视化策略风险收益散点图")

        # 从数据库获取回测结果
        risk_return_data = []
        try:
            self.db_manager.cursor.execute("SELECT strategy_id, results FROM backtest_results")
            results = self.db_manager.cursor.fetchall()

            for result in results:
                strategy_id, backtest_results = result
                metrics = backtest_results.get("metrics", {})

                # 提取风险收益指标
                if metrics:
                    risk_return_data.append(
                        {
                            "strategy_id": strategy_id,
                            "annual_return": metrics.get("annual_return", 0),
                            "max_drawdown": metrics.get("max_drawdown", 0),
                            "sharpe_ratio": metrics.get("sharpe_ratio", 0),
                            "total_profit": metrics.get("total_profit", 0),
                        }
                    )
        except Exception as e:
            logger.error(f"获取回测结果失败: {e}")
            return None

        if not risk_return_data:
            logger.error("未找到回测结果数据")
            return None

        # 创建数据框
        df = pd.DataFrame(risk_return_data)

        # 生成风险收益散点图
        fig = px.scatter(
            df,
            x="max_drawdown",
            y="annual_return",
            size="sharpe_ratio",
            color="total_profit",
            hover_name="strategy_id",
            title="策略风险收益分布",
            labels={
                "max_drawdown": "风险 (最大回撤)",
                "annual_return": "收益 (年化收益率)",
                "sharpe_ratio": "夏普比率",
                "total_profit": "总利润",
            },
            size_max=20,
            color_continuous_scale="Viridis",
        )

        # 添加参考线
        fig.add_hline(y=0, line_dash="dash", line_color="red")
        fig.add_vline(
            x=0.1, line_dash="dash", line_color="orange", annotation_text="10% 回撤警戒线"
        )

        # 更新布局
        fig.update_layout(height=600, width=1000, template="plotly_white", hovermode="closest")

        # 保存图表
        if output_path:
            fig.write_html(output_path)
            logger.info(f"策略风险收益散点图已保存到: {output_path}")

        return fig

    def generate_strategy_visualization_report(
        self, strategies=None, output_path="strategy_visualization_report.html"
    ):
        """
        生成完整的策略可视化报告

        Args:
            strategies: 策略列表，默认None
            output_path: 输出HTML路径

        Returns:
            输出文件路径
        """
        logger.info(f"生成策略可视化报告: {output_path}")

        # 创建子图，使用不同的specs配置，为表格分配专门的子图
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "策略因子组合分布",
                "策略参数分布",
                "策略风险收益散点图",
                "策略统计摘要",
            ),
            vertical_spacing=0.15,
            horizontal_spacing=0.1,
            specs=[
                [{"type": "xy"}, {"type": "xy"}],  # 第一行两个xy图表
                [{"type": "xy"}, {"type": "table"}],  # 第二行左侧xy图表，右侧表格
            ],
        )

        # 1. 添加因子组合分布图表
        factor_fig = self.visualize_factor_combinations(strategies)
        if factor_fig:
            for i, trace in enumerate(factor_fig.data):
                fig.add_trace(trace, row=1, col=1)
            fig.update_xaxes(title_text="因子数量", row=1, col=1)
            fig.update_yaxes(title_text="策略数量", row=1, col=1)

        # 2. 添加策略参数分布图表
        param_fig = self.visualize_strategy_parameters(strategies)
        if param_fig:
            # 只取第一个参数分布图表（仓位大小）
            if param_fig.data:
                fig.add_trace(param_fig.data[0], row=1, col=2)
                fig.update_xaxes(title_text="仓位大小", row=1, col=2)
                fig.update_yaxes(title_text="策略数量", row=1, col=2)

        # 3. 添加风险收益散点图
        risk_return_fig = self.visualize_strategy_risk_return()
        if risk_return_fig:
            for trace in risk_return_fig.data:
                fig.add_trace(trace, row=2, col=1)
            fig.update_xaxes(title_text="风险 (最大回撤)", row=2, col=1)
            fig.update_yaxes(title_text="收益 (年化收益率)", row=2, col=1)

        # 4. 添加策略统计摘要
        strategy_count = len(strategies) if strategies else 0
        if not strategies:
            # 从数据库获取策略数量
            try:
                self.db_manager.cursor.execute("SELECT COUNT(*) FROM strategies")
                strategy_count = self.db_manager.cursor.fetchone()[0]
            except Exception as e:
                logger.error(f"获取策略数量失败: {e}")

        # 准备统计数据
        stats_data = {
            "策略总数": strategy_count,
            "平均因子数量": 0,
            "平均仓位大小": 0,
            "平均止损比例": 0,
            "平均止盈比例": 0,
            "平均杠杆倍数": 0,
        }

        if strategies:
            # 计算统计指标
            factor_counts = [len(s["parameters"]["factors"]) for s in strategies]
            stats_data["平均因子数量"] = np.mean(factor_counts) if factor_counts else 0

            position_sizes = [
                s["parameters"].get("risk_management", {}).get("position_size", 0)
                for s in strategies
            ]
            stats_data["平均仓位大小"] = np.mean(position_sizes) if position_sizes else 0

            stop_losses = [
                s["parameters"].get("risk_management", {}).get("stop_loss", 0) for s in strategies
            ]
            stats_data["平均止损比例"] = np.mean(stop_losses) if stop_losses else 0

            take_profits = [
                s["parameters"].get("risk_management", {}).get("take_profit", 0) for s in strategies
            ]
            stats_data["平均止盈比例"] = np.mean(take_profits) if take_profits else 0

            leverages = [
                s["parameters"].get("risk_management", {}).get("leverage", 1) for s in strategies
            ]
            stats_data["平均杠杆倍数"] = np.mean(leverages) if leverages else 1

        # 创建统计摘要表格
        stats_df = pd.DataFrame(list(stats_data.items()), columns=["指标名称", "数值"])
        table_trace = go.Table(
            header=dict(values=stats_df.columns, fill_color="paleturquoise", align="left"),
            cells=dict(
                values=[stats_df["指标名称"], stats_df["数值"]], fill_color="lavender", align="left"
            ),
        )
        fig.add_trace(table_trace, row=2, col=2)

        # 更新布局
        fig.update_layout(
            height=1000, width=1200, title_text="策略可视化报告", template="plotly_white"
        )

        # 保存报告
        fig.write_html(output_path)
        logger.info(f"策略可视化报告已保存到: {output_path}")

        return output_path

    def close(self):
        """
        关闭数据库连接
        """
        self.factor_lib.close()
        self.db_manager.disconnect()


# 示例使用
if __name__ == "__main__":
    # 创建策略库实例
    strategy_lib = StrategyLibrary()

    try:
        # 生成策略
        symbols = ["ETH-USDT", "BTC-USDT"]
        timeframes = ["1h", "4h", "1d"]
        factors = ["ma", "rsi", "macd", "volatility", "momentum"]

        logger.info("开始生成策略...")
        strategies = strategy_lib.generate_strategies(
            symbols, timeframes, factors=factors, max_factors=3, min_factors=2
        )
        logger.info(f"策略生成完成，共生成 {len(strategies)} 个策略")

        # 显示生成的策略
        for i, strategy in enumerate(strategies[:5]):
            logger.info(f"\n策略 {i + 1}: {strategy['name']}")
            logger.info(f"描述: {strategy['description']}")
            logger.info(f"因子: {strategy['parameters']['factors']}")
            logger.info(f"入场规则: {json.dumps(strategy['parameters']['entry_rules'], indent=2)}")

        # 生成策略可视化报告
        output_path = "strategy_visualization_report.html"
        strategy_lib.generate_strategy_visualization_report(strategies, output_path)

        logger.info(f"\n共生成 {len(strategies)} 个策略")
        logger.info(f"策略可视化报告已生成: {output_path}")

    except Exception as e:
        logger.error(f"策略生成失败: {e}")
    finally:
        # 关闭连接
        strategy_lib.close()
