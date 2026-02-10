#!/usr/bin/env python3
"""
量化交易系统主入口
集成所有模块，实现系统的整体运行
"""

import logging
import sys
import os
from datetime import datetime

import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("quant_system.log"), logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# 导入日志脱敏模块，确保所有日志都经过脱敏处理
from .common.log_redactor import setup_log_redaction

# 导入统一市场数据下载器
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DOWNLOADER_AVAILABLE = False
UnifiedMarketDataDownloader = None

# 尝试导入数据下载器，处理循环导入问题
# 先检查数据库管理器是否已经导入，避免循环导入
try:
    # 先导入基本模块
    from .data.database_manager import DatabaseManager
    
    # 然后导入统一市场数据下载器
    from corefiles.unified_market_data_downloader import UnifiedMarketDataDownloader
    DATA_DOWNLOADER_AVAILABLE = True
    logger.info("✅ 成功导入统一市场数据下载器")
except ImportError as e:
    logger.warning(f"无法导入统一市场数据下载器: {e}")
    DATA_DOWNLOADER_AVAILABLE = False
    UnifiedMarketDataDownloader = None

# 导入其他模块
from .backtest.backtest_engine import BacktestEngine
from .belief.market_belief import (
    HealthScore,
    MarketBeliefCalibrated,
    MarketBeliefRaw,
    generate_belief_from_factors,
    compress_belief_to_weight,
)
from .calibration.belief_calibration import BeliefCalibrator, BeliefScorer
from .data.real_time_data_manager import RealTimeDataManager
from .factors.factor_library import FactorLibrary
from .strategy.strategy_library import StrategyLibrary
from .strategy.strategy_testing_system import StrategyTestingSystem
from .execution.drill_mode import DrillModeManager
from .execution.readiness import ExecutionReadiness
from .execution.reconciliation import (
    ExchangeStandardizer,
    ReconciliationConfig,
    ReconciliationEngine,
    ReconciliationReport,
    reconcile,
)
from .factors.factor_evaluation_system import FactorEvaluationSystem
from .strategy.strategy_evaluation_system import StrategyEvaluationSystem


class QuantTradingSystem:
    """
    量化交易系统主类
    集成所有模块，实现系统的整体运行
    """

    def __init__(self, config=None):
        """
        初始化量化交易系统
        """
        self.config = config or {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "quant_trading",
                "user": "postgres",
                "password": "postgres",
            },
            "data_collection": {
                "exchanges": ["okx"],
                "symbols": ["BTC-USDT", "ETH-USDT"],
                "timeframes": ["1h", "4h", "1d"],
                "start_date": "2025-01-01",
                "end_date": "2025-06-01",
            },
            "real_time": {
                "exchanges": ["okx"],
                "symbols": ["BTC-USDT", "ETH-USDT"],
                "timeframes": ["1h"],
            },
            "risk": {
                "base_risk": 0.01  # 基础风险预算
            },
        }

        logger.info("初始化量化交易系统")

        # 初始化各个模块
        self.db_manager = DatabaseManager(self.config["database"])
        self.factor_lib = FactorLibrary(self.config)
        self.strategy_lib = StrategyLibrary(self.config)
        self.backtest_engine = BacktestEngine(self.config)
        self.strategy_testing = StrategyTestingSystem(self.config)
        self.factor_evaluation = FactorEvaluationSystem(self.config)
        self.strategy_evaluation = StrategyEvaluationSystem(self.config)

        # 初始化数据下载器
        if DATA_DOWNLOADER_AVAILABLE and UnifiedMarketDataDownloader:
            try:
                self.data_downloader = UnifiedMarketDataDownloader()
                logger.info("✅ 数据下载器初始化成功")
            except Exception as e:
                logger.warning(f"初始化数据下载器失败: {e}")
                self.data_downloader = None
        else:
            logger.warning("数据下载器不可用")
            self.data_downloader = None

        # 初始化执行就绪管理器
        self.readiness = ExecutionReadiness()

        # 初始化对账引擎
        self.reconciliation_config = ReconciliationConfig()
        self.reconciliation_engine = ReconciliationEngine(self.reconciliation_config)
        self.exchange_standardizer = ExchangeStandardizer()

        # 初始化DRILL模式管理器
        self.drill_manager = DrillModeManager(self.config)

        logger.info("量化交易系统初始化完成")

    def initialize_database(self):
        """
        初始化数据库
        """
        logger.info("初始化数据库")
        return self.db_manager.initialize()

    def collect_historical_data(self):
        """
        收集历史数据
        """
        logger.info("开始收集历史数据")

        # 直接使用data_collection模块的函数
        from .data.data_collection import collect_data as dc_collect_data

        for exchange in self.config["data_collection"]["exchanges"]:
            for symbol in self.config["data_collection"]["symbols"]:
                for timeframe in self.config["data_collection"]["timeframes"]:
                    logger.info(f"收集数据: {exchange} {symbol} {timeframe}")
                    # 计算采集天数
                    start_date = datetime.strptime(
                        self.config["data_collection"]["start_date"], "%Y-%m-%d"
                    )
                    end_date = datetime.strptime(
                        self.config["data_collection"]["end_date"], "%Y-%m-%d"
                    )
                    days = (end_date - start_date).days

                    # 调用数据收集函数
                    df = dc_collect_data(
                        exchange_name=exchange, symbol=symbol, timeframe=timeframe, days=days
                    )

                    # 保存到数据库
                    if df is not None and not df.empty:
                        self.db_manager.insert_trading_data(df, symbol, timeframe)

        logger.info("历史数据收集完成")

    def start_real_time_data(self):
        """
        启动实时数据收集
        """
        logger.info("启动实时数据收集")

        real_time_manager = RealTimeDataManager(self.config)

        for exchange in self.config["real_time"]["exchanges"]:
            for symbol in self.config["real_time"]["symbols"]:
                for timeframe in self.config["real_time"]["timeframes"]:
                    logger.info(f"订阅实时数据: {exchange} {symbol} {timeframe}")
                    real_time_manager.subscribe(
                        exchange=exchange, symbol=symbol, timeframe=timeframe
                    )

        # 启动实时数据管理器
        real_time_manager.start()

        return real_time_manager

    def calculate_all_factors(self):
        """
        计算所有因子值
        """
        logger.info("开始计算所有因子值")

        for symbol in self.config["data_collection"]["symbols"]:
            for timeframe in self.config["data_collection"]["timeframes"]:
                logger.info(f"计算因子: {symbol} {timeframe}")
                self.factor_lib.calculate_all_factors(symbol=symbol, timeframe=timeframe)

        logger.info("所有因子值计算完成")

    def generate_strategies(self, n_strategies=10):
        """
        生成策略
        """
        logger.info(f"开始生成 {n_strategies} 个策略")

        strategies = self.strategy_lib.generate_strategies(n_strategies=n_strategies)

        logger.info(f"策略生成完成，共生成 {len(strategies)} 个策略")
        return strategies

    def backtest_strategy(self, strategy_id):
        """
        回测单个策略
        """
        logger.info(f"开始回测策略: {strategy_id}")

        result = self.backtest_engine.run_backtest(strategy_id=strategy_id)

        logger.info(f"策略回测完成: {strategy_id}")
        return result

    def test_strategy(self, strategy_id):
        """
        测试策略
        """
        logger.info(f"开始测试策略: {strategy_id}")

        # 1. 基本回测
        backtest_result = self.backtest_strategy(strategy_id)

        if not backtest_result:
            logger.error(f"策略回测失败: {strategy_id}")
            return None

        # 2. 蒙特卡洛测试
        monte_carlo_result = self.strategy_testing.monte_carlo_test(strategy_id=strategy_id)

        # 3. 滚动窗口测试
        rolling_result = self.strategy_testing.rolling_window_test(strategy_id=strategy_id)

        # 4. 黑天鹅测试
        black_swan_result = self.strategy_testing.black_swan_test(strategy_id=strategy_id)

        logger.info(f"策略测试完成: {strategy_id}")

        return {
            "backtest": backtest_result,
            "monte_carlo": monte_carlo_result,
            "rolling_window": rolling_result,
            "black_swan": black_swan_result,
        }

    def evaluate_all_factors(self):
        """
        评价所有因子
        """
        logger.info("开始评价所有因子")

        factor_codes = self.factor_lib.list_factors()

        results = self.factor_evaluation.evaluate_all_factors(
            factor_codes=factor_codes,
            symbols=self.config["data_collection"]["symbols"],
            timeframes=self.config["data_collection"]["timeframes"],
            start_time=datetime.strptime(self.config["data_collection"]["start_date"], "%Y-%m-%d"),
            end_time=datetime.strptime(self.config["data_collection"]["end_date"], "%Y-%m-%d"),
        )

        logger.info("因子评价完成")
        return results

    def evaluate_all_strategies(self):
        """
        评价所有策略
        """
        logger.info("开始评价所有策略")

        results = self.strategy_evaluation.evaluate_all_strategies()

        logger.info("策略评价完成")
        return results

    def run_reconciliation(self):
        """
        执行对账操作

        Returns:
            ReconciliationReport: 对账结果报告
        """
        logger.info("开始执行对账")

        # 模拟对账过程（实际实现中应该连接交易所获取真实数据）
        from .execution.reconciliation import (
            DriftType,
            RecommendedAction,
            ReconciliationDiff,
            SnapshotMeta,
        )

        # 模拟一个对账失败的情况，用于测试 BLOCKED 状态
        # 实际实现中应该比较 exchange 和 local 的真实状态
        diffs = [
            ReconciliationDiff(
                category="BALANCE",
                key="balance_USDT",
                exchange_value=1000.0,
                local_value=950.0,
                field="total",
                threshold=0.01,
            )
        ]

        report = ReconciliationReport(
            ok=False,  # 对账失败
            drift_type=DriftType.BALANCE,
            diffs=diffs,
            exchange_snapshot_meta=SnapshotMeta(
                timestamp=int(datetime.now().timestamp() * 1000),
                symbols=self.config["data_collection"]["symbols"],
                source="exchange",
            ),
            local_snapshot_meta=SnapshotMeta(
                timestamp=int(datetime.now().timestamp() * 1000),
                symbols=self.config["data_collection"]["symbols"],
                source="local",
            ),
            recommended_action=RecommendedAction.BLOCK,
            summary="账户余额不一致，检测到50 USDT差异",
        )

        logger.info(f"对账完成: ok={report.ok}, action={report.recommended_action}")
        return report

    def run_full_workflow(self):
        """
        运行完整工作流
        流水线：Data → Features → MarketBelief → w → RiskBudget → Strategy → Execution → RiskCircuit → Logs
        """
        logger.info("开始运行完整工作流")

        try:
            # 0. 执行对账，检查执行就绪状态
            reconciliation_report = self.run_reconciliation()
            self.readiness.update_reconciliation_status(reconciliation_report)

            # 检查是否可以继续执行
            if self.readiness.is_blocked():
                logger.error("系统处于 BLOCKED 状态，禁止执行工作流")
                self.readiness.write_to_last_run()
                return False

            # 1. 初始化数据库
            if not self.initialize_database():
                logger.error("数据库初始化失败")
                return False

            # 2. 收集历史数据 (Data)
            self.collect_historical_data()

            # 3. 计算所有因子 (Features)
            self.calculate_all_factors()

            # 4. 计算市场信念 (MarketBelief) 并转换为权重
            for symbol in self.config["data_collection"]["symbols"]:
                for timeframe in self.config["data_collection"]["timeframes"]:
                    logger.info(f"计算市场信念: {symbol} {timeframe}")
                    belief, w, risk_budget = self.calculate_market_belief(symbol, timeframe)
                    logger.info(
                        f"  信念: {belief.direction} | 权重 w: {w:.4f} | 风险预算: {risk_budget:.6f}"
                    )

            # 5. 生成策略 (Strategy)
            self.generate_strategies(n_strategies=10)

            # 6. 评价因子
            self.evaluate_all_factors()

            # 7. 评价策略
            self.evaluate_all_strategies()

            logger.info("完整工作流运行完成")

            # 生成DRILL报告和监控摘要
            self.drill_manager.generate_drill_report()
            self.drill_manager.generate_live_snapshot()

            # 写入执行就绪状态到报告
            self.readiness.write_to_last_run()

            return True

        except Exception as e:
            logger.error(f"完整工作流运行失败: {e}")
            # 写入执行就绪状态到报告
            self.readiness.write_to_last_run()
            return False

    def get_top_strategies(self, top_n=5):
        """
        获取排名靠前的策略
        """
        logger.info(f"获取前 {top_n} 名策略")

        return self.strategy_evaluation.get_strategy_ranking(top_n=top_n)

    def get_top_factors(self, symbol, timeframe, top_n=5):
        """
        获取排名靠前的因子
        """
        logger.info(f"获取 {symbol} {timeframe} 前 {top_n} 名因子")

        return self.factor_evaluation.get_factor_ranking(
            symbol=symbol,
            timeframe=timeframe,
            start_time=datetime.strptime(self.config["data_collection"]["start_date"], "%Y-%m-%d"),
            end_time=datetime.strptime(self.config["data_collection"]["end_date"], "%Y-%m-%d"),
            top_n=top_n,
        )

    def calculate_risk_budget(self, w):
        """
        计算风险预算
        公式：risk_budget = base_risk * w^2

        Args:
            w: 连续权重 ∈ [0, 1]

        Returns:
            float: 风险预算
        """
        base_risk = self.config["risk"]["base_risk"]
        return base_risk * (w**2)

    def calculate_market_belief(self, symbol, timeframe):
        """
        计算市场信念并转换为权重

        Args:
            symbol: 交易对
            timeframe: 时间周期

        Returns:
            tuple: (belief, w, risk_budget)
        """
        # 获取所有因子代码
        factor_codes = self.factor_lib.factors.keys()

        # 获取当前时间
        end_time = datetime.now()
        start_time = end_time - pd.Timedelta(days=30)  # 获取最近30天数据

        # 收集所有因子数据
        factors = {}
        for factor_code in list(factor_codes)[:5]:  # 只使用前5个因子作为示例
            df = self.factor_lib.get_factor_values(
                factor_code=factor_code,
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
            )
            if not df.empty:
                # 使用最新值
                factors[factor_code] = df.iloc[-1][factor_code]

        # 计算市场信念
        belief = compute_market_belief(factors)

        # 压缩为权重 w
        w = compress_belief_to_weight(belief)

        # 计算风险预算
        risk_budget = self.calculate_risk_budget(w)

        return belief, w, risk_budget

    # ==================== 数据下载模块 ====================
    
    def is_data_downloader_available(self):
        """
        检查数据下载器是否可用
        
        Returns:
            bool: 数据下载器是否可用
        """
        return DATA_DOWNLOADER_AVAILABLE and self.data_downloader is not None
    
    def download_okx_candles(self, symbol: str, timeframe: str, days: int = 7, limit: int = 100, 
                             enable_incremental: bool = True, enable_deduplication: bool = True) -> pd.DataFrame:
        """
        下载OKX K线数据（作为交易系统的子项）
        
        Args:
            symbol: 交易对，如 'BTC-USDT'
            timeframe: 时间间隔，如 '1h', '1d', '5m'
            days: 下载天数（如果启用增量下载，此参数为最大天数）
            limit: 每次请求限制
            enable_incremental: 是否启用增量下载
            enable_deduplication: 是否启用去重
            
        Returns:
            pd.DataFrame: K线数据（已统一格式，已去重）
        """
        if not self.is_data_downloader_available():
            logger.error("数据下载器不可用")
            return pd.DataFrame()
        
        logger.info(f"通过交易系统下载OKX K线数据: {symbol} {timeframe} {days}天")
        return self.data_downloader.download_okx_candles(
            symbol=symbol, 
            timeframe=timeframe, 
            days=days, 
            limit=limit, 
            enable_incremental=enable_incremental, 
            enable_deduplication=enable_deduplication
        )
    
    def download_coingecko_data(self, asset: str, metric: str, days: int = 7) -> pd.DataFrame:
        """
        从CoinGecko下载数据（作为交易系统的子项）
        
        Args:
            asset: 资产名称，如 'bitcoin', 'ethereum'
            metric: 指标名称，'price', 'market_cap', 'volume'
            days: 下载天数
            
        Returns:
            pd.DataFrame: 数据
        """
        if not self.is_data_downloader_available():
            logger.error("数据下载器不可用")
            return pd.DataFrame()
        
        logger.info(f"通过交易系统下载CoinGecko数据: {asset} {metric} {days}天")
        return self.data_downloader.download_coingecko_data(
            asset=asset, 
            metric=metric, 
            days=days
        )
    
    def download_freqtrade_ticker(self) -> dict:
        """
        从Freqtrade获取24小时行情数据（作为交易系统的子项）
        
        Returns:
            dict: 行情数据
        """
        if not self.is_data_downloader_available():
            logger.error("数据下载器不可用")
            return {}
        
        logger.info("通过交易系统获取Freqtrade 24小时行情数据")
        return self.data_downloader.download_freqtrade_ticker()
    
    def download_freqtrade_trades(self) -> list:
        """
        从Freqtrade获取当前持仓数据（作为交易系统的子项）
        
        Returns:
            list: 持仓数据
        """
        if not self.is_data_downloader_available():
            logger.error("数据下载器不可用")
            return []
        
        logger.info("通过交易系统获取Freqtrade当前持仓数据")
        return self.data_downloader.download_freqtrade_trades()
    
    def download_all_sources(self, symbols: list = None, days: int = 7) -> dict:
        """
        下载所有数据源的数据（作为交易系统的子项）
        
        Args:
            symbols: 交易对列表，如 ['BTC-USDT', 'ETH-USDT']
            days: 下载天数
            
        Returns:
            dict: 各数据源的数据
        """
        if not self.is_data_downloader_available():
            logger.error("数据下载器不可用")
            return {}
        
        logger.info(f"通过交易系统下载所有数据源数据: {symbols} {days}天")
        return self.data_downloader.download_all_sources(
            symbols=symbols, 
            days=days
        )
    
    def save_data_to_database(self, data: dict):
        """
        保存数据到数据库（作为交易系统的子项）
        
        Args:
            data: 要保存的数据字典
        """
        if not self.is_data_downloader_available():
            logger.error("数据下载器不可用")
            return
        
        logger.info("通过交易系统保存数据到数据库")
        self.data_downloader.save_to_database(data)
    
    def download_market_data(self, symbols: list, timeframes: list, days: int = 7, 
                             enable_incremental: bool = True) -> dict:
        """
        统一的市场数据下载入口（作为交易系统的子项）
        
        Args:
            symbols: 交易对列表，如 ['BTC-USDT', 'ETH-USDT']
            timeframes: 时间周期列表，如 ['1h', '1d']
            days: 下载天数
            enable_incremental: 是否启用增量下载
            
        Returns:
            dict: 下载的数据，格式为 {"symbol_timeframe": dataframe}
        """
        if not self.is_data_downloader_available():
            logger.error("数据下载器不可用")
            return {}
        
        logger.info(f"通过交易系统统一下载市场数据: {symbols} {timeframes} {days}天")
        results = {}
        
        for symbol in symbols:
            for timeframe in timeframes:
                key = f"{symbol}_{timeframe}"
                df = self.download_okx_candles(
                    symbol=symbol, 
                    timeframe=timeframe, 
                    days=days, 
                    enable_incremental=enable_incremental
                )
                results[key] = df
        
        return results
    
    # ==================== 系统关闭 ====================
    
    def close(self):
        """
        关闭系统
        """
        logger.info("关闭量化交易系统")

        # 关闭各个模块
        self.factor_lib.close()
        self.strategy_evaluation.close()
        self.factor_evaluation.close()
        self.db_manager.disconnect()

        logger.info("量化交易系统已关闭")


def main():
    """
    主函数
    """
    logger.info("启动量化交易系统")

    # 创建系统实例
    system = QuantTradingSystem()

    try:
        # 运行完整工作流
        system.run_full_workflow()

        # 获取并打印排名靠前的策略
        top_strategies = system.get_top_strategies(top_n=3)
        logger.info("\n=== 排名靠前的策略 ===")
        for i, strategy in enumerate(top_strategies):
            logger.info(
                f"\n排名 {i + 1}: 策略 {strategy['strategy_name']} (ID: {strategy['strategy_id']})"
            )
            logger.info(f"  总分: {strategy['total_score']}")
            logger.info(
                f"  年化收益率: {strategy['backtest_results']['metrics'].get('annual_return', 0):.4f}"
            )
            logger.info(
                f"  最大回撤: {strategy['backtest_results']['metrics'].get('max_drawdown', 0):.4f}"
            )
            logger.info(
                f"  夏普比率: {strategy['backtest_results']['metrics'].get('sharpe_ratio', 0):.4f}"
            )

        # 获取并打印排名靠前的因子
        top_factors = system.get_top_factors("ETH-USDT", "1h", top_n=3)
        logger.info("\n=== 排名靠前的因子 ===")
        for i, factor in enumerate(top_factors["top_factors"]):
            logger.info(f"\n排名 {i + 1}: 因子 {factor['factor_code']}")
            logger.info(f"  IC: {factor['ic']:.4f}")
            logger.info(f"  显著性: {factor['is_significant']}")
            logger.info(f"  R²: {factor['r_squared']:.4f}")

    except KeyboardInterrupt:
        logger.info("系统被用户中断")
    except Exception as e:
        logger.error(f"系统运行失败: {e}")
    finally:
        # 关闭系统
        system.close()

    logger.info("量化交易系统已退出")


if __name__ == "__main__":
    main()
