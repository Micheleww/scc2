import logging

from ..data.database_manager import DatabaseManager

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StrategyEvaluationSystem:
    """
    策略评价系统，用于对策略表现进行赋分和排序
    支持多指标加权评分，基于回测结果进行综合评价
    """

    def __init__(self, config=None):
        """
        初始化策略评价系统
        """
        self.config = config or {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "quant_trading",
                "user": "postgres",
                "password": "135769",
            },
            "scoring": {
                "weights": {
                    "annual_return": 0.25,
                    "max_drawdown": 0.20,
                    "sharpe_ratio": 0.20,
                    "sortino_ratio": 0.15,
                    "win_rate": 0.10,
                    "profit_factor": 0.10,
                },
                "max_drawdown_threshold": 0.5,  # 最大回撤超过50%将被严重扣分
            },
        }

        # 数据库管理器
        self.db_manager = DatabaseManager(self.config["database"])

    def evaluate_strategy(self, strategy_id, backtest_id=None):
        """
        评价单个策略

        Args:
            strategy_id (int): 策略ID
            backtest_id (int, optional): 回测结果ID，如不指定则使用最新回测结果

        Returns:
            dict: 策略评价结果
        """
        logger.info(f"开始评价策略: {strategy_id}")

        try:
            # 获取回测结果
            if backtest_id:
                # 使用指定的回测结果
                query = """
                    SELECT * FROM backtest_results 
                    WHERE backtest_id = %s AND strategy_id = %s
                """
                self.db_manager.cursor.execute(query, (backtest_id, strategy_id))
            else:
                # 使用最新的回测结果
                query = """
                    SELECT * FROM backtest_results 
                    WHERE strategy_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """
                self.db_manager.cursor.execute(query, (strategy_id,))

            backtest_row = self.db_manager.cursor.fetchone()
            if not backtest_row:
                logger.error(f"未找到策略回测结果: {strategy_id}")
                return None

            # 获取策略信息
            query = """
                SELECT * FROM strategies 
                WHERE strategy_id = %s
            """
            self.db_manager.cursor.execute(query, (strategy_id,))
            strategy_row = self.db_manager.cursor.fetchone()
            if not strategy_row:
                logger.error(f"未找到策略信息: {strategy_id}")
                return None

            # 解析回测结果
            backtest_results = backtest_row[6]  # results字段

            # 计算各项评分
            scores = self._calculate_scores(backtest_results)

            # 计算总分
            total_score = self._calculate_total_score(scores)

            # 整合评价结果
            evaluation_result = {
                "strategy_id": strategy_id,
                "strategy_name": strategy_row[1],
                "backtest_id": backtest_row[0],
                "symbol": backtest_row[2],
                "timeframe": backtest_row[3],
                "start_time": backtest_row[4],
                "end_time": backtest_row[5],
                "created_at": backtest_row[7],
                "backtest_results": backtest_results,
                "scores": scores,
                "total_score": total_score,
                "ranking": None,  # 将在批量评价时计算
            }

            logger.info(f"策略评价完成: {strategy_id}, 总分: {total_score:.2f}")
            return evaluation_result

        except Exception as e:
            logger.error(f"评价策略失败: {e}")
            return None

    def _calculate_scores(self, backtest_results):
        """
        计算各项评分

        Args:
            backtest_results (dict): 回测结果

        Returns:
            dict: 各项评分
        """
        scores = {}
        metrics = backtest_results.get("metrics", {})

        # 1. 年化收益率评分 (0-100)
        annual_return = metrics.get("annual_return", 0)
        if annual_return > 0.5:  # 年化收益超过50%得满分
            scores["annual_return"] = 100
        elif annual_return < -0.5:  # 年化亏损超过50%得0分
            scores["annual_return"] = 0
        else:
            # 线性映射到0-100分
            scores["annual_return"] = 50 + (annual_return / 0.5) * 50

        # 2. 最大回撤评分 (0-100)
        max_drawdown = abs(metrics.get("max_drawdown", 0))
        if max_drawdown < 0.05:  # 最大回撤小于5%得满分
            scores["max_drawdown"] = 100
        elif max_drawdown > self.config["scoring"]["max_drawdown_threshold"]:
            # 超过阈值得0分
            scores["max_drawdown"] = 0
        else:
            # 线性映射，最大回撤越大分数越低
            scores["max_drawdown"] = (
                100 - (max_drawdown / self.config["scoring"]["max_drawdown_threshold"]) * 100
            )

        # 3. 夏普比率评分 (0-100)
        sharpe_ratio = metrics.get("sharpe_ratio", 0)
        if sharpe_ratio > 3:
            scores["sharpe_ratio"] = 100
        elif sharpe_ratio < -1:
            scores["sharpe_ratio"] = 0
        else:
            # 线性映射
            scores["sharpe_ratio"] = max(0, 50 + (sharpe_ratio - 1) * 25)

        # 4. 索提诺比率评分 (0-100)
        sortino_ratio = metrics.get("sortino_ratio", 0)
        if sortino_ratio > 4:
            scores["sortino_ratio"] = 100
        elif sortino_ratio < -1:
            scores["sortino_ratio"] = 0
        else:
            # 线性映射
            scores["sortino_ratio"] = max(0, 50 + (sortino_ratio - 1.5) * 20)

        # 5. 胜率评分 (0-100)
        win_rate = metrics.get("win_rate", 0)
        if win_rate > 0.7:
            scores["win_rate"] = 100
        elif win_rate < 0.3:
            scores["win_rate"] = 0
        else:
            # 线性映射
            scores["win_rate"] = (win_rate - 0.3) / 0.4 * 100

        # 6. 盈利因子评分 (0-100)
        profit_factor = metrics.get("profit_factor", 0)
        if profit_factor > 2:
            scores["profit_factor"] = 100
        elif profit_factor < 0.8:
            scores["profit_factor"] = 0
        else:
            # 线性映射
            scores["profit_factor"] = min(100, (profit_factor - 0.8) / 1.2 * 100)

        return scores

    def _calculate_total_score(self, scores):
        """
        计算总分

        Args:
            scores (dict): 各项评分

        Returns:
            float: 总分
        """
        total_score = 0.0
        weights = self.config["scoring"]["weights"]

        for metric, score in scores.items():
            if metric in weights:
                total_score += score * weights[metric]

        return round(total_score, 2)

    def evaluate_all_strategies(self):
        """
        评价所有策略

        Returns:
            list: 所有策略的评价结果，按总分排序
        """
        logger.info("开始评价所有策略")

        try:
            # 获取所有策略ID
            query = """
                SELECT strategy_id FROM strategies
            """
            self.db_manager.cursor.execute(query)
            strategy_rows = self.db_manager.cursor.fetchall()

            all_evaluations = []

            # 评价每个策略
            for strategy_row in strategy_rows:
                strategy_id = strategy_row[0]
                evaluation = self.evaluate_strategy(strategy_id)
                if evaluation:
                    all_evaluations.append(evaluation)

            # 排序并分配排名
            all_evaluations.sort(key=lambda x: x["total_score"], reverse=True)

            for i, evaluation in enumerate(all_evaluations):
                evaluation["ranking"] = i + 1

            logger.info(f"所有策略评价完成，共评价 {len(all_evaluations)} 个策略")

            return all_evaluations

        except Exception as e:
            logger.error(f"评价所有策略失败: {e}")
            return []

    def get_strategy_ranking(self, top_n=10):
        """
        获取策略排名

        Args:
            top_n (int): 返回前N个策略

        Returns:
            list: 前N个策略的评价结果
        """
        logger.info(f"获取策略排名，前 {top_n} 名")

        all_evaluations = self.evaluate_all_strategies()
        return all_evaluations[:top_n]

    def backtest_and_evaluate(
        self, strategy, symbol, timeframe, start_time, end_time, parameters=None
    ):
        """
        回测并评价策略

        Args:
            strategy (object): 策略对象
            symbol (str): 交易对
            timeframe (str): 时间周期
            start_time (datetime): 开始时间
            end_time (datetime): 结束时间
            parameters (dict, optional): 策略参数

        Returns:
            dict: 回测和评价结果
        """
        logger.info(f"开始回测并评价策略: {symbol} {timeframe}")

        try:
            # 这里假设strategy对象有backtest方法
            backtest_result = strategy.backtest(symbol, timeframe, start_time, end_time, parameters)

            if not backtest_result:
                logger.error("回测失败")
                return None

            # 计算评分
            scores = self._calculate_scores(backtest_result)
            total_score = self._calculate_total_score(scores)

            evaluation_result = {
                "symbol": symbol,
                "timeframe": timeframe,
                "start_time": start_time,
                "end_time": end_time,
                "backtest_result": backtest_result,
                "scores": scores,
                "total_score": total_score,
            }

            logger.info(f"回测并评价完成，总分: {total_score:.2f}")

            return evaluation_result

        except Exception as e:
            logger.error(f"回测并评价策略失败: {e}")
            return None

    def get_strategy_comparison(self, strategy_ids):
        """
        比较多个策略

        Args:
            strategy_ids (list): 策略ID列表

        Returns:
            list: 策略比较结果
        """
        logger.info(f"开始比较策略: {strategy_ids}")

        comparisons = []

        for strategy_id in strategy_ids:
            evaluation = self.evaluate_strategy(strategy_id)
            if evaluation:
                comparisons.append(evaluation)

        # 按总分排序
        comparisons.sort(key=lambda x: x["total_score"], reverse=True)

        logger.info(f"策略比较完成，共比较 {len(comparisons)} 个策略")

        return comparisons

    def update_scoring_weights(self, new_weights):
        """
        更新评分权重

        Args:
            new_weights (dict): 新的权重配置

        Returns:
            bool: 更新是否成功
        """
        try:
            # 验证权重总和为1
            total_weight = sum(new_weights.values())
            if not (0.99 <= total_weight <= 1.01):
                logger.error(f"权重总和必须为1，当前总和: {total_weight}")
                return False

            self.config["scoring"]["weights"] = new_weights
            logger.info(f"已更新评分权重: {new_weights}")
            return True

        except Exception as e:
            logger.error(f"更新评分权重失败: {e}")
            return False

    def close(self):
        """
        关闭数据库连接
        """
        self.db_manager.disconnect()


# 示例使用
if __name__ == "__main__":
    # 创建策略评价系统实例
    evaluation_system = StrategyEvaluationSystem()

    try:
        # 示例：评价所有策略并获取排名
        top_strategies = evaluation_system.get_strategy_ranking(top_n=5)

        # 打印结果
        for i, strategy_eval in enumerate(top_strategies):
            logger.info(
                f"\n排名 {i + 1}: 策略 {strategy_eval['strategy_name']} (ID: {strategy_eval['strategy_id']})"
            )
            logger.info(f"  总分: {strategy_eval['total_score']}")
            logger.info(
                f"  年化收益率: {strategy_eval['backtest_results']['metrics'].get('annual_return', 0):.4f}"
            )
            logger.info(
                f"  最大回撤: {strategy_eval['backtest_results']['metrics'].get('max_drawdown', 0):.4f}"
            )
            logger.info(
                f"  夏普比率: {strategy_eval['backtest_results']['metrics'].get('sharpe_ratio', 0):.4f}"
            )
            logger.info(f"  各项评分: {strategy_eval['scores']}")

    except Exception as e:
        logger.error(f"策略评价系统示例运行失败: {e}")
    finally:
        # 关闭连接
        evaluation_system.close()
