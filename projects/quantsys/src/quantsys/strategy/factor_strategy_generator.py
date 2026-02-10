#!/usr/bin/env python3
"""
遍历因子库的策略生成器
能够基于因子库中的所有因子生成多样化的交易策略
"""

import itertools
import json
import logging
from datetime import datetime

import numpy as np
from database_manager import DatabaseManager
from factor_library import FactorLibrary

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FactorStrategyGenerator:
    """
    遍历因子库的策略生成器
    能够基于因子库中的所有因子生成多样化的交易策略
    """

    def __init__(self, config=None):
        """
        初始化策略生成器
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
        self.params = {
            "max_factors": 3,  # 最大因子数量
            "min_factors": 1,  # 最小因子数量
            "signal_types": ["cross_up", "cross_down", "above", "below", "cross_zero"],
            "stop_losses": [0.01, 0.02, 0.05, 0.1],
            "take_profits": [0.02, 0.05, 0.1, 0.15],
            "position_sizes": [0.1, 0.2, 0.3, 0.5],
            "max_leverage": 200,  # 最大杠杆倍数
            "lookback_periods": [10, 14, 20, 50],
        }

        # 贝叶斯优化参数区段
        self.bayesian_sections = {
            "stop_loss": {"min": 0.005, "max": 0.2, "num_sections": 10},
            "take_profit": {"min": 0.01, "max": 0.3, "num_sections": 10},
            "lookback": {"min": 5, "max": 200, "num_sections": 15},
            "threshold": {"min": -2, "max": 2, "num_sections": 20},
            "leverage": {"min": 1, "max": self.params["max_leverage"], "num_sections": 20},
        }

        # 策略计数器
        self.strategy_counter = {
            "total": 0,
            "single_factor": 0,
            "multi_factor": {2: 0, 3: 0, 4: 0, 5: 0},
        }

    def get_factor_categories(self):
        """
        获取因子分类
        """
        categories = {"price": [], "volume": [], "volatility": [], "momentum": [], "trend": []}

        all_factors = self.factor_lib.list_factors()
        for factor_code in all_factors:
            # 获取因子信息
            factor_info = self.factor_lib.factors.get(factor_code, {})
            factor_type = factor_info.get("type", "price")
            if factor_type in categories:
                categories[factor_type].append(factor_code)
            else:
                categories["price"].append(factor_code)  # 默认价格类

        return categories

    def generate_single_factor_strategies(self, symbols, timeframes):
        """
        生成单因子策略
        """
        logger.info("开始生成单因子策略...")

        # 获取所有因子
        all_factors = self.factor_lib.list_factors()
        logger.info(f"可用因子数量: {len(all_factors)}")

        # 生成策略
        strategies = []
        for symbol in symbols:
            for timeframe in timeframes:
                for factor_code in all_factors:
                    # 生成单因子策略
                    strategy = self._generate_factor_strategy(symbol, timeframe, [factor_code])
                    strategies.append(strategy)
                    # 更新计数器
                    self.strategy_counter["single_factor"] += 1
                    self.strategy_counter["total"] += 1

        logger.info(f"单因子策略生成完成，共生成 {len(strategies)} 个策略")
        logger.info(
            f"当前策略统计: 单因子策略 {self.strategy_counter['single_factor']} 个，多因子策略 {sum(self.strategy_counter['multi_factor'].values())} 个，总计 {self.strategy_counter['total']} 个"
        )
        return strategies

    def generate_multi_factor_strategies(self, symbols, timeframes, max_factors=3, min_factors=2):
        """
        生成多因子组合策略
        """
        logger.info("开始生成多因子策略...")

        # 获取所有因子
        all_factors = self.factor_lib.list_factors()

        # 生成策略
        strategies = []
        for symbol in symbols:
            for timeframe in timeframes:
                # 生成不同因子数量的组合
                for num_factors in range(min_factors, max_factors + 1):
                    # 生成因子组合
                    factor_combinations = list(itertools.combinations(all_factors, num_factors))
                    logger.info(f"生成 {len(factor_combinations)} 个 {num_factors} 因子组合")

                    # 为每个组合生成策略
                    for factor_comb in factor_combinations:
                        strategy = self._generate_factor_strategy(symbol, timeframe, factor_comb)
                        strategies.append(strategy)
                        # 更新计数器
                        self.strategy_counter["multi_factor"][num_factors] += 1
                        self.strategy_counter["total"] += 1

        logger.info(f"多因子策略生成完成，共生成 {len(strategies)} 个策略")
        logger.info(
            f"当前策略统计: 单因子策略 {self.strategy_counter['single_factor']} 个，多因子策略 {sum(self.strategy_counter['multi_factor'].values())} 个，总计 {self.strategy_counter['total']} 个"
        )
        logger.info(f"多因子策略分布: {self.strategy_counter['multi_factor']}")
        return strategies

    def generate_category_based_strategies(self, symbols, timeframes, category_pairs=None):
        """
        基于因子分类生成策略
        例如：价格类+动量类，波动率类+趋势类等
        """
        logger.info("开始生成基于因子分类的策略...")

        # 获取因子分类
        categories = self.get_factor_categories()

        # 如果没有指定分类对，使用所有可能的组合
        if not category_pairs:
            category_pairs = list(itertools.combinations(categories.keys(), 2))

        strategies = []
        for symbol in symbols:
            for timeframe in timeframes:
                for cat1, cat2 in category_pairs:
                    # 获取两个分类的因子
                    factors1 = categories[cat1]
                    factors2 = categories[cat2]

                    # 生成跨分类因子组合
                    for factor1 in factors1:
                        for factor2 in factors2:
                            factor_comb = [factor1, factor2]
                            strategy = self._generate_factor_strategy(
                                symbol, timeframe, factor_comb
                            )
                            strategies.append(strategy)
                            # 更新计数器
                            self.strategy_counter["multi_factor"][len(factor_comb)] += 1
                            self.strategy_counter["total"] += 1

        logger.info(f"基于分类的策略生成完成，共生成 {len(strategies)} 个策略")
        logger.info(
            f"当前策略统计: 单因子策略 {self.strategy_counter['single_factor']} 个，多因子策略 {sum(self.strategy_counter['multi_factor'].values())} 个，总计 {self.strategy_counter['total']} 个"
        )
        logger.info(f"多因子策略分布: {self.strategy_counter['multi_factor']}")
        return strategies

    def generate_strategies_by_count(self, symbols, timeframes, target_count=2000):
        """
        生成指定数量的策略
        """
        logger.info(f"开始生成 {target_count} 个策略...")

        # 获取所有因子
        all_factors = self.factor_lib.list_factors()

        strategies = []

        # 重置计数器
        self.strategy_counter = {
            "total": 0,
            "single_factor": 0,
            "multi_factor": {2: 0, 3: 0, 4: 0, 5: 0},
        }

        while len(strategies) < target_count:
            # 随机选择因子数量（1-3个因子）
            num_factors = np.random.choice([1, 2, 3])

            # 随机选择因子组合
            if num_factors == 1:
                factor_comb = [np.random.choice(all_factors)]
            else:
                # 确保因子不重复
                factor_comb = list(np.random.choice(all_factors, size=num_factors, replace=False))

            # 随机选择交易对和时间周期
            symbol = np.random.choice(symbols)
            timeframe = np.random.choice(timeframes)

            # 生成策略
            strategy = self._generate_factor_strategy(symbol, timeframe, factor_comb)
            strategies.append(strategy)

            # 定期打印进度
            if len(strategies) % 100 == 0:
                logger.info(f"已生成 {len(strategies)} / {target_count} 个策略")

        logger.info(f"策略生成完成，共生成 {len(strategies)} 个策略")
        logger.info(
            f"策略统计: 单因子策略 {self.strategy_counter['single_factor']} 个，多因子策略 {sum(self.strategy_counter['multi_factor'].values())} 个，总计 {self.strategy_counter['total']} 个"
        )
        logger.info(f"多因子策略分布: {self.strategy_counter['multi_factor']}")

        return strategies

    def _generate_strategy_code(self):
        """
        生成唯一的策略代码，支持100亿+策略数量
        使用UUID v4生成全局唯一标识符
        """
        import uuid

        # 生成UUID并去除连字符，转换为大写
        return f"STR{uuid.uuid4().hex.upper()}"

    def _generate_factor_strategy(self, symbol, timeframe, factor_comb):
        """
        生成单个因子组合策略
        """
        # 获取因子ID
        factor_ids = [self.db_manager.get_factor_id(factor_code) for factor_code in factor_comb]
        factor_ids = [fid for fid in factor_ids if fid is not None]

        # 生成唯一策略代码
        strategy_code = self._generate_strategy_code()

        # 生成策略名称（基于策略代码，确保唯一性）
        factor_names = "_".join(factor_comb)
        strategy_name = (
            f"strat_{symbol.replace('-', '_')}_{timeframe}_{factor_names[:30]}"  # 限制因子名称长度
        )

        # 生成策略描述
        strategy_desc = f"基于{factor_names}因子组合的策略，应用于{symbol} {timeframe}"

        # 生成信号配置
        signal_config = self._generate_signal_config(factor_comb)

        # 生成风险参数
        risk_params = self._generate_risk_params()

        # 生成策略参数
        parameters = {
            "strategy_code": strategy_code,
            "symbol": symbol,
            "timeframe": timeframe,
            "factors": list(factor_comb),
            "factor_ids": factor_ids,
            "signal_config": signal_config,
            "risk_management": risk_params,
            "order_config": {"order_type": "market", "slippage": 0.001},
        }

        # 保存策略到数据库
        strategy_id = self.db_manager.insert_strategy(
            name=strategy_name,
            description=strategy_desc,
            factor_ids=factor_ids,
            parameters=parameters,
        )

        # 更新策略计数器
        num_factors = len(factor_comb)
        if num_factors == 1:
            self.strategy_counter["single_factor"] += 1
        else:
            if num_factors in self.strategy_counter["multi_factor"]:
                self.strategy_counter["multi_factor"][num_factors] += 1
            else:
                self.strategy_counter["multi_factor"][num_factors] = 1
        self.strategy_counter["total"] += 1

        return {
            "strategy_id": strategy_id,
            "strategy_code": strategy_code,
            "name": strategy_name,
            "description": strategy_desc,
            "parameters": parameters,
        }

    def _get_bayesian_parameter(self, param_name):
        """
        使用贝叶斯优化的方法生成参数值，采用有效的多个区段
        """
        if param_name in self.bayesian_sections:
            section_config = self.bayesian_sections[param_name]
            min_val = section_config["min"]
            max_val = section_config["max"]
            num_sections = section_config["num_sections"]

            # 生成区段边界
            sections = np.linspace(min_val, max_val, num_sections + 1)

            # 随机选择一个区段
            section_idx = np.random.randint(0, num_sections)
            section_min = sections[section_idx]
            section_max = sections[section_idx + 1]

            # 在选定区段内随机生成值
            if param_name == "leverage":
                # 杠杆需要整数
                return int(np.random.randint(section_min, section_max + 1))
            else:
                return np.random.uniform(section_min, section_max)
        else:
            # 如果没有配置贝叶斯区段，则使用默认值
            if param_name == "lookback":
                return np.random.choice(self.params["lookback_periods"])
            elif param_name == "stop_loss":
                return np.random.choice(self.params["stop_losses"])
            elif param_name == "take_profit":
                return np.random.choice(self.params["take_profits"])
            elif param_name == "threshold":
                return np.random.uniform(-1, 1)
            elif param_name == "leverage":
                return np.random.randint(1, self.params["max_leverage"] + 1)
            else:
                return 0

    def _generate_signal_config(self, factors):
        """
        生成信号配置
        """
        signal_config = {}

        for factor_code in factors:
            # 获取因子信息
            factor_info = self.factor_lib.factors.get(factor_code, {})
            factor_type = factor_info.get("type", "price")

            # 根据因子类型选择合适的信号类型
            if factor_type == "momentum":
                signal_type = np.random.choice(["cross_up", "cross_down", "cross_zero"])
            elif factor_type == "volatility":
                signal_type = np.random.choice(["above", "below"])
            elif factor_type == "trend":
                signal_type = np.random.choice(["cross_up", "cross_down", "above"])
            else:
                signal_type = np.random.choice(self.params["signal_types"])

            # 生成配置，使用贝叶斯优化区段
            signal_config[factor_code] = {
                "type": signal_type,
                "lookback": int(self._get_bayesian_parameter("lookback")),
                "threshold": self._get_bayesian_parameter("threshold"),
                "stop_loss": self._get_bayesian_parameter("stop_loss"),
                "take_profit": self._get_bayesian_parameter("take_profit"),
            }

        return signal_config

    def _get_default_threshold(self, factor_type, signal_type):
        """
        根据因子类型和信号类型获取默认阈值
        """
        if signal_type in ["cross_zero", "cross_up", "cross_down"]:
            return 0
        elif factor_type == "momentum":
            return np.random.uniform(-1, 1)
        elif factor_type == "volatility":
            return np.random.uniform(0.05, 0.2)
        elif factor_type == "price":
            return np.random.uniform(0, 1)
        else:
            return np.random.uniform(0, 1)

    def _generate_risk_params(self):
        """
        生成风险参数
        """
        return {
            "position_size": np.random.choice(self.params["position_sizes"]),
            "stop_loss": np.random.choice(self.params["stop_losses"]),
            "take_profit": np.random.choice(self.params["take_profits"]),
            "leverage": np.random.randint(
                1, self.params["max_leverage"] + 1
            ),  # 1到max_leverage之间的任意整数
            "trailing_stop": np.random.choice([True, False]),
            "max_drawdown": 0.2,
        }

    def run_strategy_optimization(self, strategy_id, symbol, timeframe, start_time, end_time):
        """
        运行策略优化
        """
        logger.info(f"开始优化策略: {strategy_id}")

        # 获取策略
        strategy = self.db_manager.get_strategy(strategy_id)
        if not strategy:
            logger.error(f"策略不存在: {strategy_id}")
            return None

        # 加载历史数据
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
        if df.empty:
            logger.error(f"未找到历史数据: {symbol} {timeframe}")
            return None

        # 优化参数组合
        best_params = None
        best_score = -float("inf")

        # 简单网格搜索
        for sl in self.params["stop_losses"]:
            for tp in self.params["take_profits"]:
                for pos_size in self.params["position_sizes"]:
                    # 更新策略参数
                    strategy["parameters"]["risk_management"]["stop_loss"] = sl
                    strategy["parameters"]["risk_management"]["take_profit"] = tp
                    strategy["parameters"]["risk_management"]["position_size"] = pos_size

                    # 运行回测
                    results = self._run_backtest(df, strategy)

                    # 计算评分（例如：夏普比率）
                    score = results.get("sharpe_ratio", -float("inf"))

                    # 更新最佳参数
                    if score > best_score:
                        best_score = score
                        best_params = {
                            "stop_loss": sl,
                            "take_profit": tp,
                            "position_size": pos_size,
                            "sharpe_ratio": score,
                        }

        logger.info(f"策略优化完成，最佳夏普比率: {best_score}")
        logger.info(f"最佳参数: {json.dumps(best_params, indent=2)}")

        return best_params

    def calculate_strategy_score(self, backtest_results):
        """
        计算策略评分
        基于夏普比率、胜率、年化收益和最大回撤等指标
        """
        # 提取关键指标
        sharpe_ratio = backtest_results.get("sharpe_ratio", 0)
        win_rate = backtest_results.get("win_rate", 0)
        annual_return = backtest_results.get("annual_return", 0)
        max_drawdown = backtest_results.get("max_drawdown", 1)
        profit_factor = backtest_results.get("profit_factor", 1)

        # 计算各项评分
        # 夏普比率评分（最高30分）
        sharpe_score = min(max(sharpe_ratio * 10, 0), 30)

        # 胜率评分（最高25分）
        win_rate_score = min(max(win_rate * 35.71, 0), 25)

        # 收益评分（最高25分）
        profit_score = min(max(annual_return * 16.67, 0), 25)

        # 回撤评分（最高20分，越小越好）
        drawdown_score = min(max((1 - max_drawdown) * 25, 0), 20)

        # 总评分
        total_score = round(sharpe_score + win_rate_score + profit_score + drawdown_score, 2)

        return {
            "total_score": total_score,
            "sharpe_score": round(sharpe_score, 2),
            "win_rate_score": round(win_rate_score, 2),
            "profit_score": round(profit_score, 2),
            "drawdown_score": round(drawdown_score, 2),
        }

    def generate_backtest_report(self, strategy, backtest_results, scores):
        """
        生成回测报告
        """
        report = {
            "strategy_code": strategy["parameters"].get("strategy_code", "N/A"),
            "strategy_name": strategy["name"],
            "symbol": strategy["parameters"].get("symbol", "N/A"),
            "timeframe": strategy["parameters"].get("timeframe", "N/A"),
            "factors": strategy["parameters"].get("factors", []),
            "backtest_results": backtest_results,
            "scores": scores,
            "generated_at": datetime.now().isoformat(),
        }
        return report

    def _run_backtest(self, df, strategy):
        """
        运行回测
        """
        # 这里可以调用现有的回测引擎
        # 简化实现，返回模拟结果
        return {
            "total_trades": np.random.randint(10, 100),
            "winning_trades": np.random.randint(5, 70),
            "losing_trades": np.random.randint(5, 50),
            "profit_factor": np.random.uniform(0.8, 2.5),
            "win_rate": np.random.uniform(0.3, 0.7),
            "total_profit": np.random.uniform(-1000, 5000),
            "annual_return": np.random.uniform(-0.5, 1.5),
            "sharpe_ratio": np.random.uniform(-1, 3),
            "max_drawdown": np.random.uniform(0.05, 0.5),
        }

    def backtest_all_strategies(self, symbols, timeframes, start_time, end_time):
        """
        回测所有策略
        """
        logger.info("开始回测所有策略...")

        # 获取所有策略
        self.db_manager.cursor.execute("SELECT strategy_id, name, parameters FROM strategies")
        strategies = self.db_manager.cursor.fetchall()

        results = []
        for strategy_id, name, params in strategies:
            symbol = params.get("symbol")
            timeframe = params.get("timeframe")

            if symbol in symbols and timeframe in timeframes:
                logger.info(f"回测策略: {name}")

                # 加载历史数据
                df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
                if not df.empty:
                    # 运行回测
                    backtest_results = self._run_backtest(
                        df, {"strategy_id": strategy_id, "name": name, "parameters": params}
                    )

                    # 计算策略评分
                    scores = self.calculate_strategy_score(backtest_results)

                    # 生成回测报告
                    report = self.generate_backtest_report(
                        {"strategy_id": strategy_id, "name": name, "parameters": params},
                        backtest_results,
                        scores,
                    )

                    # 保存回测结果到数据库
                    self.db_manager.insert_backtest_result(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        timeframe=timeframe,
                        start_time=start_time,
                        end_time=end_time,
                        parameters=params,
                        results=backtest_results,
                        scores=scores,
                    )

                    results.append(report)

        # 按总评分排序
        results.sort(key=lambda x: x["scores"]["total_score"], reverse=True)

        # 更新排名
        for i, result in enumerate(results):
            result["ranking"] = i + 1

        logger.info(f"回测完成，共回测 {len(results)} 个策略")
        return results

    def generate_strategy_ranking(self, symbols, timeframes, start_time, end_time, top_n=10):
        """
        生成策略排名
        """
        # 回测所有策略
        backtest_results = self.backtest_all_strategies(symbols, timeframes, start_time, end_time)

        # 取前N名
        top_strategies = backtest_results[:top_n]

        # 保存优秀策略到数据库
        for strategy in top_strategies:
            # 获取策略ID
            strategy_id = strategy.get("strategy_id")
            if strategy_id:
                # 保存到优秀策略表
                self.db_manager.insert_top_strategy(
                    strategy_info={
                        "strategy_id": strategy_id,
                        "name": strategy.get("strategy_name"),
                        "parameters": {
                            "strategy_code": strategy.get("strategy_code"),
                            "symbol": strategy.get("symbol"),
                            "timeframe": strategy.get("timeframe"),
                            "factors": strategy.get("factors"),
                        },
                    },
                    backtest_results=strategy.get("backtest_results", {}),
                    scores=strategy.get("scores", {}),
                    ranking=strategy.get("ranking", 0),
                    start_time=start_time,
                    end_time=end_time,
                )

        # 生成排名报告
        ranking_report = {
            "generated_at": datetime.now().isoformat(),
            "symbols": symbols,
            "timeframes": timeframes,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "total_strategies": len(backtest_results),
            "top_strategies": top_strategies,
            "ranking": [
                {
                    "rank": strategy["ranking"],
                    "strategy_code": strategy["strategy_code"],
                    "strategy_name": strategy["strategy_name"],
                    "total_score": strategy["scores"]["total_score"],
                    "sharpe_ratio": strategy["backtest_results"]["sharpe_ratio"],
                    "win_rate": strategy["backtest_results"]["win_rate"],
                    "annual_return": strategy["backtest_results"]["annual_return"],
                    "max_drawdown": strategy["backtest_results"]["max_drawdown"],
                }
                for strategy in top_strategies
            ],
        }

        return ranking_report

    def close(self):
        """
        关闭连接
        """
        self.factor_lib.close()
        self.db_manager.disconnect()


# 示例使用
if __name__ == "__main__":
    # 创建策略生成器实例
    generator = FactorStrategyGenerator()

    try:
        # 生成2000个策略
        logger.info("\n=== 生成2000个策略 ===")
        symbols = ["ETH-USDT", "BTC-USDT"]
        timeframes = ["1h", "4h"]

        # 使用generate_strategies_by_count方法生成2000个策略
        strategies = generator.generate_strategies_by_count(
            symbols=symbols, timeframes=timeframes, target_count=2000
        )

        # 显示生成的策略统计
        logger.info("\n=== 策略生成统计 ===")
        logger.info(f"单因子策略: {generator.strategy_counter['single_factor']} 个")
        logger.info(f"多因子策略分布: {generator.strategy_counter['multi_factor']}")
        logger.info(
            f"多因子策略总计: {sum(generator.strategy_counter['multi_factor'].values())} 个"
        )
        logger.info(f"总计生成策略: {generator.strategy_counter['total']} 个")
        logger.info("各因子数量策略分布:")
        for num_factors in sorted(generator.strategy_counter["multi_factor"].keys()):
            count = generator.strategy_counter["multi_factor"][num_factors]
            if count > 0:
                logger.info(f"  {num_factors}个因子: {count} 个策略")

    except Exception as e:
        logger.error(f"策略生成失败: {e}")
        import traceback

        traceback.print_exc()
    finally:
        # 关闭连接
        generator.close()
