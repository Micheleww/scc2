#!/usr/bin/env python3
"""
ETH小时级多因子策略主脚本
整合所有组件，实现完整的多因子策略
"""

import logging
import time
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 导入自定义模块
from auto_factor_generator import AutoFactorGenerator
from data_framework import DataFramework
from dl_factor_generator import DLFactorGenerator
from factor_optimizer import FactorOptimizer

# TODO: P0 Layer Fix - Remove execution/risk dependencies from factors layer
# These modules should be injected from strategy layer, not imported here
# from order_execution import OrderExecution
# from risk_manager import RiskManager
from self_learning_system import SelfLearningSystem


class ETHHourlyMultiFactor:
    """
    ETH小时级多因子策略
    """

    def __init__(
        self,
        data=None,
        symbol="ETH/USDT",
        timeframe="1h",
        live_trading=False,
        config=None,
        order_execution=None,
        risk_manager=None,
        monitor=None,
        signal_bus=None,
    ):
        """
        初始化ETH小时级多因子策略

        Args:
            data: 原始数据
            symbol: 交易对
            timeframe: 时间周期
            live_trading: 是否启用实盘交易
            config: 配置信息，包含API密钥等
            order_execution: 订单执行模块（外部注入，避免factors层依赖execution层）[DEPRECATED: 使用signal_bus]
            risk_manager: 风险管理器（外部注入，避免factors层依赖risk层）[DEPRECATED: 使用signal_bus]
            monitor: 监控器（外部注入）
            signal_bus: 信号总线（推荐使用，实现策略层与执行层解耦）
        """
        self.symbol = symbol
        self.timeframe = timeframe
        self.dl_factor_generator = None
        self.live_trading = live_trading
        self.config = config or {}
        self.use_pretrained_model = self.config.get("strategy", {}).get(
            "use_pretrained_model", False
        )
        self.pretrained_model = None
        self.pretrained_model_data = None

        # 初始化数据框架
        self.data_framework = DataFramework(data, symbol, timeframe)

        # 初始化因子生成器
        if data is not None:
            self.data_framework.preprocess_data()
            self.factor_generator = AutoFactorGenerator(
                self.data_framework.get_base_features(), symbol=symbol, timeframe=timeframe
            )
            # 初始化深度学习因子生成器
            self.dl_factor_generator = DLFactorGenerator(data, seq_length=24, factor_dim=10)
        else:
            self.factor_generator = None

        # 初始化因子优化器
        self.factor_optimizer = FactorOptimizer()

        # 初始化自学习系统
        if data is not None:
            self.self_learning = SelfLearningSystem(
                self.data_framework, self.factor_generator, self.factor_optimizer
            )
        else:
            self.self_learning = None

        # 初始化信号总线（推荐方式，实现策略层与执行层解耦）
        if signal_bus is not None:
            self.signal_bus = signal_bus
            logger.info("使用信号总线模式（策略层与执行层解耦）")
        else:
            # 如果没有提供signal_bus，尝试获取全局实例
            try:
                from src.quantsys.strategy.signal_bus import get_signal_bus

                self.signal_bus = get_signal_bus()
                logger.info("使用全局信号总线实例")
            except ImportError:
                self.signal_bus = None
                logger.warning("信号总线不可用，将使用传统模式（向后兼容）")

        # 初始化实盘相关组件（外部注入，避免factors层依赖execution/risk层）
        # [DEPRECATED: 推荐使用signal_bus，保留此部分用于向后兼容]
        if live_trading:
            logger.info("启用实盘交易模式")
            # TODO: P0 Layer Fix - Use injected dependencies instead of direct imports
            # These components should be injected from strategy layer
            if order_execution is None or risk_manager is None or monitor is None:
                logger.warning("实盘交易模式需要注入 order_execution, risk_manager, monitor")
                logger.warning("当前为向后兼容，使用 TODO stub 模式")
                # TODO stub: 实际应该从上层注入，这里保留为兼容性
                # from order_execution import OrderExecution
                # from risk_manager import RiskManager
                # self.order_execution = OrderExecution(self.config.get('exchange', {}))
                # self.risk_manager = RiskManager(self.config.get('risk', {}))
                # self.monitor = StrategyMonitor(self.config.get('monitor', {}))
                self.order_execution = None
                self.risk_manager = None
                self.monitor = None
            else:
                self.order_execution = order_execution
                self.risk_manager = risk_manager
                self.monitor = monitor
        else:
            self.order_execution = None
            self.risk_manager = None
            self.monitor = None

        # 加载预训练模型（如果配置了的话）
        if self.use_pretrained_model:
            self.load_pretrained_model()

        logger.info("ETH小时级多因子策略初始化完成")

    def load_pretrained_model(self, model_path=None):
        """
        加载预训练模型

        Args:
            model_path: 模型路径，如果不提供则从配置或最佳模型路径文件中读取

        Returns:
            bool: 是否加载成功
        """
        import json
        import pickle

        logger.info("开始加载预训练模型")

        # 获取模型路径
        if model_path is None:
            # 从配置中获取
            model_path = self.config.get("strategy", {}).get("model_path")

            # 如果配置中没有，尝试从best_model_path.json中读取
            if not model_path:
                try:
                    with open("best_model_path.json") as f:
                        model_path = json.load(f)["model_path"]
                except Exception as e:
                    logger.error(f"无法读取最佳模型路径: {e}")
                    return False

        try:
            # 加载模型
            with open(model_path, "rb") as f:
                self.pretrained_model_data = pickle.load(f)

            self.pretrained_model = self.pretrained_model_data["model"]

            # 加载scaler
            if "scaler" in self.pretrained_model_data:
                self.factor_optimizer.scaler = self.pretrained_model_data["scaler"]
                logger.info("成功加载预训练模型的scaler")

            logger.info(f"成功加载预训练模型: {model_path}")
            logger.info(f"模型类型: {self.pretrained_model_data['model_type']}")
            logger.info(f"模型训练日期: {self.pretrained_model_data['train_date']}")
            logger.info(f"最佳因子数量: {len(self.pretrained_model_data['best_factors'].columns)}")

            return True
        except Exception as e:
            logger.error(f"加载预训练模型失败: {e}")
            return False

    def load_data(self, data):
        """
        加载数据

        Args:
            data: 原始数据
        """
        # 加载数据到数据框架
        self.data_framework.load_data(data)

        # 预处理数据
        self.data_framework.preprocess_data()

        # 生成标签
        self.data_framework.generate_labels(horizon=4)

        # 初始化因子生成器
        self.factor_generator = AutoFactorGenerator(
            self.data_framework.get_base_features(), symbol=self.symbol, timeframe=self.timeframe
        )

        # 初始化深度学习因子生成器
        self.dl_factor_generator = DLFactorGenerator(data, seq_length=24, factor_dim=10)

        # 初始化自学习系统
        self.self_learning = SelfLearningSystem(
            self.data_framework, self.factor_generator, self.factor_optimizer
        )

        logger.info("数据加载和预处理完成")

    def create_test_data(self, n_samples=365 * 24) -> pd.DataFrame:
        """
        创建测试数据，支持不同时间周期

        Args:
            n_samples: 样本数量

        Returns:
            test_data: 测试数据
        """
        logger.info(f"创建 {n_samples} 个样本的测试数据，时间周期: {self.timeframe}")

        # 根据时间周期设置freq参数
        if self.timeframe == "1h":
            freq = "h"
            price_volatility = 0.02  # 小时级波动率
        elif self.timeframe == "30m":
            freq = "30min"
            price_volatility = 0.01  # 30分钟级波动率
        elif self.timeframe == "15m":
            freq = "15min"
            price_volatility = 0.008  # 15分钟级波动率
        elif self.timeframe == "5m":
            freq = "5min"
            price_volatility = 0.005  # 5分钟级波动率
        elif self.timeframe == "1m":
            freq = "1min"
            price_volatility = 0.003  # 1分钟级波动率
        else:
            freq = "h"  # 默认小时级
            price_volatility = 0.02

        # 创建日期范围
        dates = pd.date_range(start="2023-01-01", periods=n_samples, freq=freq)

        # 创建随机价格数据
        np.random.seed(42)
        price = 1000.0
        prices = []
        for _ in range(n_samples):
            change = np.random.normal(0, price_volatility, 1)[0]
            price = price * (1 + change)
            prices.append(price)

        # 创建数据框
        test_data = pd.DataFrame(
            {
                "timestamp": dates,
                "open": [p * (1 + np.random.normal(0, 0.005)) for p in prices],
                "high": [p * (1 + np.random.normal(0.01, 0.005)) for p in prices],
                "low": [p * (1 - np.random.normal(0.01, 0.005)) for p in prices],
                "close": prices,
                "volume": [np.random.normal(1000000, 500000) for _ in range(n_samples)],
                "amount": [np.random.normal(1000000000, 500000000) for _ in range(n_samples)],
            }
        )

        # 设置索引
        test_data.set_index("timestamp", inplace=True)

        logger.info(f"测试数据创建完成，形状: {test_data.shape}")

        return test_data

    def generate_dl_factors(self, epochs: int = 20, batch_size: int = 32) -> pd.DataFrame:
        """
        生成深度学习因子

        Args:
            epochs: 训练轮数
            batch_size: 批次大小

        Returns:
            dl_factors: 深度学习生成的因子矩阵
        """
        if self.dl_factor_generator is None:
            logger.error("深度学习因子生成器未初始化")
            return pd.DataFrame()

        logger.info("开始生成深度学习因子")

        # 运行完整的深度学习因子生成流程
        dl_factors = self.dl_factor_generator.run_full_dl_pipeline(
            epochs=epochs, batch_size=batch_size
        )

        logger.info(f"深度学习因子生成完成，共生成 {dl_factors.shape[1]} 个因子")
        return dl_factors

    def run_factor_generation(
        self, n_factors: int = 100, n_best: int = 20, use_dl_factors: bool = True
    ) -> pd.DataFrame:
        """
        运行因子生成

        Args:
            n_factors: 生成因子的数量
            n_best: 选择最佳因子的数量
            use_dl_factors: 是否使用深度学习生成的因子

        Returns:
            best_factors: 最佳因子矩阵
        """
        logger.info("开始运行因子生成")

        # 生成传统最佳因子
        best_factors = self.factor_generator.generate_best_factors(
            n_factors=n_factors, n_best=n_best, labels=self.data_framework.labels
        )

        # 生成深度学习因子
        if use_dl_factors and self.dl_factor_generator is not None:
            dl_factors = self.generate_dl_factors(epochs=20, batch_size=32)

            # 将深度学习因子与传统因子合并
            if not dl_factors.empty:
                # 对齐索引
                common_index = best_factors.index.intersection(dl_factors.index)
                best_factors = best_factors.loc[common_index]
                dl_factors = dl_factors.loc[common_index]

                # 合并因子
                best_factors = pd.concat([best_factors, dl_factors], axis=1)
                logger.info(f"合并传统因子和深度学习因子，总因子数: {best_factors.shape[1]}")

        # 将最佳因子添加到数据框架
        for factor_name in best_factors.columns:
            self.data_framework.add_factor(factor_name, best_factors[factor_name])

        # 清理因子矩阵
        self.data_framework.clean_factor_matrix()

        logger.info(f"因子生成完成，共生成 {len(best_factors.columns)} 个因子")

        return best_factors

    def train_model(self, model_type: str = "ridge", params: dict = None) -> tuple[Any, dict]:
        """
        训练模型

        Args:
            model_type: 模型类型
            params: 模型参数

        Returns:
            tuple: (训练好的模型, 模型评估指标)
        """
        logger.info(f"开始训练 {model_type} 模型")

        # 划分训练集和测试集
        X_train, X_test, y_train, y_test = self.data_framework.split_data()

        # 训练模型
        model = self.factor_optimizer.train_model(X_train, y_train, model_type, params)

        # 评估模型
        metrics = self.factor_optimizer.evaluate_model(X_test, y_test)

        logger.info(f"模型训练完成，IC: {metrics['ic']:.4f}")

        return model, metrics

    def generate_trading_signals(
        self, signal_type: str = "rank", top_pct: float = 0.2, bottom_pct: float = 0.2
    ) -> pd.Series:
        """
        生成交易信号

        Args:
            signal_type: 信号类型
            top_pct: 多头信号的阈值
            bottom_pct: 空头信号的阈值

        Returns:
            signal: 交易信号
        """
        logger.info(f"开始生成交易信号，信号类型: {signal_type}")

        # 获取因子矩阵
        X = self.data_framework.get_factor_matrix()

        # 预测
        predictions = self.factor_optimizer.predict(X)

        # 生成信号
        signal = self.factor_optimizer.generate_trading_signal(
            predictions, signal_type, top_pct, bottom_pct
        )

        logger.info("交易信号生成完成")

        return signal

    def calculate_strategy_performance(self, signal: pd.Series) -> dict:
        """
        计算策略绩效

        Args:
            signal: 交易信号

        Returns:
            metrics: 策略绩效指标
        """
        logger.info("开始计算策略绩效")

        # 根据时间周期动态获取收益率列名
        if self.timeframe == "1h":
            ret_col = "ret_1h"
        elif self.timeframe in ["1m", "5m", "15m", "30m"]:
            ret_col = f"ret_{self.timeframe}"
        else:
            ret_col = "ret_1h"  # 默认值

        # 获取收益率
        returns = self.data_framework.data[ret_col]

        # 计算策略绩效，传递时间周期参数
        metrics = self.factor_optimizer.calculate_strategy_metrics(signal, returns, self.timeframe)

        logger.info(f"策略绩效计算完成，夏普比率: {metrics['sharpe_ratio']:.4f}")

        return metrics

    def run_full_pipeline(
        self,
        n_factors: int = 100,
        n_best: int = 20,
        model_type: str = "ridge",
        params: dict = None,
        signal_type: str = "rank",
        use_dl_factors: bool = True,
    ) -> dict:
        """
        运行完整的策略流程

        Args:
            n_factors: 生成因子的数量
            n_best: 选择最佳因子的数量
            model_type: 模型类型
            params: 模型参数
            signal_type: 信号类型
            use_dl_factors: 是否使用深度学习生成的因子

        Returns:
            results: 策略结果
        """
        logger.info("开始运行完整的策略流程")

        # 运行因子生成
        best_factors = self.run_factor_generation(n_factors, n_best, use_dl_factors)

        # 训练模型
        model, model_metrics = self.train_model(model_type, params)

        # 生成交易信号
        signal = self.generate_trading_signals(signal_type)

        # 计算策略绩效
        metrics = self.calculate_strategy_performance(signal)

        # 整合结果
        results = {
            "best_factors": best_factors,
            "model": model,
            "model_metrics": model_metrics,
            "signal": signal,
            "performance_metrics": metrics,
            "feature_importance": self.factor_optimizer.get_feature_importance(),
        }

        logger.info(f"完整策略流程运行完成，夏普比率: {metrics['sharpe_ratio']:.4f}")

        return results

    def run_self_learning(
        self, n_factors: int = 100, n_best: int = 20, model_type: str = "ridge"
    ) -> dict:
        """
        运行自学习更新

        Args:
            n_factors: 生成因子的数量
            n_best: 选择最佳因子的数量
            model_type: 模型类型

        Returns:
            cycle_results: 自学习周期结果
        """
        logger.info("开始运行自学习更新")

        # 运行自学习周期
        cycle_results = self.self_learning.run_self_learning_cycle(
            n_factors=n_factors, n_best=n_best, model_type=model_type
        )

        logger.info(
            f"自学习更新完成，策略夏普比率: {cycle_results['strategy_metrics']['sharpe_ratio']:.4f}"
        )

        return cycle_results

    def backtest_strategy(self, signal: pd.Series) -> pd.DataFrame:
        """
        回测策略

        Args:
            signal: 交易信号

        Returns:
            backtest_results: 回测结果
        """
        logger.info("开始回测策略")

        # 获取数据
        df = self.data_framework.data.copy()

        # 根据时间周期动态获取收益率列名
        if self.timeframe == "1h":
            ret_col = "ret_1h"
        elif self.timeframe in ["1m", "5m", "15m", "30m"]:
            ret_col = f"ret_{self.timeframe}"
        else:
            ret_col = "ret_1h"  # 默认值

        # 确保收益率列存在
        if ret_col not in df.columns:
            # 如果不存在，计算它
            window = 1  # 单个周期
            df[ret_col] = df["close"] / df["close"].shift(window) - 1

        # 添加交易信号
        df["signal"] = signal

        # 计算策略收益率
        df["strategy_ret"] = df["signal"].shift(1) * df[ret_col]

        # 计算累计收益率
        df["cumulative_ret"] = (1 + df["strategy_ret"]).cumprod()

        # 计算基准收益率
        df["benchmark_ret"] = df[ret_col].cumsum()

        logger.info("策略回测完成")

        return df

    def generate_signal(self, signal: float, current_price: float) -> dict[str, Any]:
        """
        生成交易信号（新方法，推荐使用）
        策略层只生成信号，不直接执行订单

        Args:
            signal: 交易信号值
            current_price: 当前价格

        Returns:
            result: 信号生成结果
        """
        from src.quantsys.strategy.signal_bus import Signal, SignalType

        # 确定信号类型和方向
        if signal > 0.5:
            signal_type = SignalType.ENTER
            side = "buy"
            strength = min(signal, 1.0)
        elif signal < -0.5:
            signal_type = SignalType.EXIT
            side = "sell"
            strength = min(abs(signal), 1.0)
        else:
            signal_type = SignalType.HOLD
            side = ""
            strength = abs(signal)

        # 创建信号对象
        trading_signal = Signal(
            signal_type=signal_type,
            symbol=self.symbol,
            side=side,
            strength=strength,
            stop_loss=current_price * 0.98 if signal_type == SignalType.ENTER else None,  # 2%止损
            take_profit=current_price * 1.05 if signal_type == SignalType.ENTER else None,  # 5%止盈
            strategy_id=self.config.get("strategy_id", "eth_hourly_multi_factor"),
            strategy_version=self.config.get("strategy_version", "v1.0.0"),
            metadata={"current_price": current_price, "signal_value": signal},
        )

        # 发布信号到信号总线
        if self.signal_bus:
            self.signal_bus.publish(trading_signal)
            logger.info(
                f"信号已发布: {trading_signal.signal_id} ({signal_type.value}) for {self.symbol}"
            )
            return {
                "success": True,
                "message": "信号已发布",
                "signal_id": trading_signal.signal_id,
                "signal": trading_signal.to_dict(),
            }
        else:
            logger.warning("信号总线未初始化，无法发布信号")
            return {"success": False, "message": "信号总线未初始化"}

    def execute_trade(
        self,
        signal: float,
        current_price: float,
        balance: float,
        current_position: float,
        total_position: float,
    ) -> dict[str, Any]:
        """
        执行交易（传统方法，向后兼容）

        [DEPRECATED] 推荐使用 generate_signal() 方法，通过信号总线传递信号

        Args:
            signal: 交易信号
            current_price: 当前价格
            balance: 当前余额
            current_position: 当前品种持仓金额
            total_position: 总持仓金额

        Returns:
            result: 交易执行结果
        """
        # 如果信号总线可用，优先使用信号总线模式
        if self.signal_bus:
            logger.info("使用信号总线模式（推荐）")
            return self.generate_signal(signal, current_price)

        # 传统模式（向后兼容）
        if not self.live_trading:
            logger.warning("当前未启用实盘交易模式，无法执行交易")
            return {"success": False, "message": "实盘交易未启用"}

        # TODO: P0 Layer Fix - Check if dependencies are injected
        if self.risk_manager is None or self.order_execution is None or self.monitor is None:
            logger.error("实盘交易依赖未注入，无法执行交易")
            logger.error("请从 strategy 层注入 order_execution, risk_manager, monitor")
            return {"success": False, "message": "依赖未注入"}

        # 检查是否允许交易
        if not self.risk_manager.is_trading_allowed(balance):
            return {"success": False, "message": "风险控制不允许交易"}

        # 获取杠杆设置
        leverage = self.config["strategy"].get("leverage", 10)

        # 检查是否为合约交易
        is_contract = "-SWAP" in self.symbol or "-FUTURES" in self.symbol

        # 根据信号确定交易方向和数量
        if signal > 0.5:
            side = "buy"
            pos_side = "long"
            # 计算目标仓位（根据信号强度）
            base_amount = self.config.get("strategy", {}).get("base_order_amount", 10.0)
            target_amount = signal * base_amount
        elif signal < -0.5:
            side = "sell"
            pos_side = "short"
            # 计算卖出数量（根据信号强度和当前持仓）
            base_amount = self.config.get("strategy", {}).get("base_order_amount", 10.0)
            target_amount = abs(signal) * base_amount
        else:
            # 信号较弱，不执行交易
            logger.info(f"信号较弱 ({signal:.4f})，不执行交易")
            return {"success": False, "message": "信号较弱"}

        # 计算实际交易数量
        if is_contract:
            # 合约交易：使用USDT金额计算合约张数
            # 张数 = 金额 * 杠杆 / 价格
            amount = (target_amount * leverage) / current_price

            # 确保数量是最小交易单位（0.01张）的倍数
            min_lot_size = 0.01
            amount = round(amount / min_lot_size) * min_lot_size

            # 设置杠杆
            logger.info(f"设置 {self.symbol} 杠杆为 {leverage} 倍")
            for pos_side_type in ["long", "short"]:
                set_leverage_result = self.order_execution.set_leverage(
                    self.symbol, leverage, pos_side_type
                )
                if set_leverage_result.get("code") != "0":
                    logger.error(
                        f"设置 {pos_side_type} 方向杠杆失败: {set_leverage_result.get('msg')}"
                    )
                    return {
                        "success": False,
                        "message": f"设置杠杆失败: {set_leverage_result.get('msg')}",
                    }
        else:
            # 现货交易：直接使用金额
            amount = target_amount / current_price

        # 调整订单数量
        adjusted_amount = self.risk_manager.get_adjusted_order_amount(
            self.symbol, side, amount, current_price, balance, current_position, total_position
        )

        if adjusted_amount <= 0:
            logger.info("调整后的订单数量为0，不执行交易")
            return {"success": False, "message": "调整后的订单数量为0"}

        # 检查订单风险
        # 对于合约交易，使用实际保证金金额进行风险检查
        if is_contract:
            check_amount = target_amount  # 实际投入的USDT金额
        else:
            check_amount = adjusted_amount * current_price

        if not self.risk_manager.check_order_risk(
            self.symbol,
            side,
            adjusted_amount,
            current_price,
            balance,
            current_position,
            total_position,
            is_contract=is_contract,
            contract_amount=check_amount,
        ):
            return {"success": False, "message": "订单风险检查未通过"}

        # 执行下单
        try:
            # 构造订单参数
            order_params = {}
            if is_contract:
                # 合约交易额外参数
                order_params = {"tdMode": "cross", "posSide": pos_side, "lever": str(leverage)}

            # 市价单
            result = self.order_execution.place_order(
                symbol=self.symbol,
                side=side,
                order_type="market",
                amount=adjusted_amount,
                params=order_params,
            )

            if result.get("code") == "0":
                order_id = result["data"][0]["ordId"]
                logger.info(f"订单下单成功: {order_id}")

                # 记录订单
                self.monitor.log_order(
                    order_id=order_id,
                    timestamp=datetime.now(),
                    symbol=self.symbol,
                    side=side,
                    order_type="market",
                    amount=adjusted_amount,
                    price=current_price,
                    status="filled",
                )

                # 更新监控数据
                new_position = current_position + (
                    adjusted_amount * current_price
                    if side == "buy"
                    else -adjusted_amount * current_price
                )
                self.monitor.update_position(balance, new_position)

                return {
                    "success": True,
                    "order_id": order_id,
                    "side": side,
                    "amount": adjusted_amount,
                    "price": current_price,
                    "position_side": pos_side,
                    "leverage": leverage,
                }
            else:
                logger.error(f"订单下单失败: {result.get('msg')}")
                return {"success": False, "message": result.get("msg")}
        except Exception as e:
            logger.error(f"执行交易时出错: {e}")
            return {"success": False, "message": str(e)}

    def run_live_strategy(self, update_interval: int = 3600):
        """
        运行实盘策略

        Args:
            update_interval: 数据更新间隔（秒）
        """
        if not self.live_trading:
            logger.error("当前未启用实盘交易模式，请在初始化时设置live_trading=True")
            return

        # TODO: P0 Layer Fix - Check if dependencies are injected
        if self.risk_manager is None or self.order_execution is None or self.monitor is None:
            logger.error("实盘交易依赖未注入，无法运行实盘策略")
            logger.error("请从 strategy 层注入 order_execution, risk_manager, monitor")
            return

        logger.info("开始运行实盘策略")

        try:
            while True:
                # 获取最新数据
                logger.info("获取最新数据...")
                # 这里需要实现从实时数据管理器获取最新数据的逻辑
                # 暂时使用模拟数据

                # 预处理数据
                self.data_framework.preprocess_data()

                # 检查是否已经加载了模型（静态策略）
                if self.factor_optimizer.model is not None:
                    logger.info("使用已加载的静态模型，跳过模型训练，但需要生成因子")

                    # 生成因子
                    logger.info("生成因子...")
                    # 使用自学习系统生成因子
                    self.self_learning.run()

                    # 生成信号
                    logger.info("生成交易信号...")
                    signal = self.generate_trading_signals()
                    logger.info(f"生成的交易信号: {signal.iloc[-1]}")
                # 检查是否使用预训练模型
                elif self.use_pretrained_model and self.pretrained_model:
                    logger.info("使用预训练模型，跳过模型训练，但仍需生成因子")

                    # 生成因子（使用与预训练模型相同的配置）
                    logger.info("生成因子...")
                    use_dl_factors = self.config.get("strategy", {}).get("use_dl_factors", True)
                    best_factors = self.run_factor_generation(
                        n_factors=self.config.get("strategy", {}).get("n_factors", 50),
                        n_best=self.config.get("strategy", {}).get("n_best", 15),
                        use_dl_factors=use_dl_factors,
                    )

                    # 将预训练模型和scaler设置到因子优化器中
                    self.factor_optimizer.model = self.pretrained_model
                    # 直接生成信号
                    logger.info("生成交易信号...")
                    # 使用预训练模型的因子配置
                    signal = self.generate_trading_signals()
                    logger.info(f"生成的交易信号: {signal.iloc[-1]}")
                else:
                    # 生成因子
                    logger.info("生成因子...")
                    use_dl_factors = self.config.get("strategy", {}).get("use_dl_factors", False)
                    best_factors = self.run_factor_generation(
                        n_factors=self.config.get("strategy", {}).get("n_factors", 50),
                        n_best=self.config.get("strategy", {}).get("n_best", 15),
                        use_dl_factors=use_dl_factors,
                    )

                    # 训练模型
                    logger.info("训练模型...")
                    model_type = self.config.get("strategy", {}).get("model_type", "ridge")
                    model, metrics = self.train_model(model_type=model_type)

                    # 生成信号
                    logger.info("生成交易信号...")
                    signal = self.generate_trading_signals(
                        signal_type=self.config.get("strategy", {}).get("signal_type", "rank")
                    )

                # 记录信号
                self.monitor.log_signal(
                    timestamp=datetime.now(),
                    symbol=self.symbol,
                    signal=signal.iloc[-1],
                    signal_type="rank",
                )

                # 获取账户信息
                balance = self.order_execution.get_balance()
                positions = self.order_execution.get_positions()

                # 简化处理，获取当前价格和持仓
                current_price = self.data_framework.data["close"].iloc[-1]
                current_position = 0.0  # 假设当前无持仓
                total_position = 0.0  # 假设总持仓为0

                # 执行交易
                logger.info("执行交易...")
                trade_result = self.execute_trade(
                    signal=signal.iloc[-1],
                    current_price=current_price,
                    balance=balance.get("data", [{}])[0].get("totalEq", 0.0),
                    current_position=current_position,
                    total_position=total_position,
                )

                # 打印策略摘要
                self.monitor.print_strategy_summary()

                # 检查告警条件
                alerts = self.monitor.check_alert_conditions()
                if alerts:
                    for alert in alerts:
                        logger.warning(f"告警: {alert}")

                # 等待下一个周期
                logger.info(f"等待 {update_interval} 秒...")
                time.sleep(update_interval)

        except KeyboardInterrupt:
            logger.info("正在停止实盘策略...")
        except Exception as e:
            logger.error(f"实盘策略运行出错: {e}")
        finally:
            # 保存历史数据
            self.monitor.save_trade_history(
                f"trade_history_{datetime.now().strftime('%Y%m%d')}.json"
            )
            self.monitor.save_signal_history(
                f"signal_history_{datetime.now().strftime('%Y%m%d')}.json"
            )
            self.monitor.save_order_history(
                f"order_history_{datetime.now().strftime('%Y%m%d')}.json"
            )

            logger.info("实盘策略已停止")

    def get_live_status(self) -> dict[str, Any]:
        """
        获取实盘运行状态

        Returns:
            status: 实盘运行状态
        """
        if not self.live_trading:
            return {"status": "not_running"}

        # TODO: P0 Layer Fix - Check if dependencies are injected
        if self.risk_manager is None or self.order_execution is None or self.monitor is None:
            return {"status": "error", "message": "依赖未注入"}

        return {
            "status": "running",
            "strategy_stats": self.monitor.get_strategy_status(),
            "risk_status": self.risk_manager.get_risk_status(),
            "alerts": self.monitor.check_alert_conditions(),
        }

    def check_overfitting(
        self, model_type: str = "ridge", params: dict = None, n_simulations: int = 100
    ) -> dict[str, Any]:
        """
        检查模型过拟合情况

        Args:
            model_type: 模型类型
            params: 模型参数
            n_simulations: 蒙特卡洛模拟次数

        Returns:
            overfitting_results: 过拟合检测结果
        """
        logger.info("=== 开始检查模型过拟合情况 ===")

        # 获取因子矩阵和标签
        X = self.data_framework.get_factor_matrix()
        y = self.data_framework.labels

        # 确保数据对齐
        common_index = X.index.intersection(y.index)
        X = X.loc[common_index]
        y = y.loc[common_index]

        # 使用蒙特卡洛方法检测过拟合
        overfitting_results = self.factor_optimizer.monte_carlo_overfitting_test(
            X, y, model_type, params, n_simulations
        )

        # 添加额外的检测指标
        overfitting_results["factor_count"] = X.shape[1]
        overfitting_results["sample_count"] = X.shape[0]
        overfitting_results["model_type"] = model_type

        # 打印检测结果
        logger.info("\n=== 过拟合检测结果 ===")
        logger.info(f"模型类型: {model_type}")
        logger.info(f"真实IC: {overfitting_results['real_ic']:.4f}")
        logger.info(f"模拟平均IC: {overfitting_results['mean_simulated_ic']:.4f}")
        logger.info(f"模拟IC标准差: {overfitting_results['std_simulated_ic']:.4f}")
        logger.info(f"p值: {overfitting_results['p_value']:.4f}")
        logger.info(f"Z值: {overfitting_results['z_score']:.4f}")
        logger.info(f"过拟合分数: {overfitting_results['overfitting_score']:.4f}")
        logger.info(f"因子数量: {overfitting_results['factor_count']}")
        logger.info(f"样本数量: {overfitting_results['sample_count']}")

        # 解释结果
        if overfitting_results["p_value"] < 0.05:
            logger.info("结论: 模型未显著过拟合 (p值 < 0.05)")
        else:
            logger.info("结论: 模型可能存在过拟合风险 (p值 >= 0.05)")

        if abs(overfitting_results["overfitting_score"]) < 0.02:
            logger.info("因子表现稳定，过拟合风险较低")
        elif overfitting_results["overfitting_score"] > 0.05:
            logger.info("因子表现优异，但可能存在一定过拟合风险")
        else:
            logger.info("因子表现一般，过拟合风险较低")

        return overfitting_results


def main():
    """
    主函数
    """
    logger.info("=== 启动ETH小时级多 因子策略 ===")

    # 创建策略实例
    strategy = ETHHourlyMultiFactor()

    # 创建测试数据
    test_data = strategy.create_test_data(n_samples=365 * 24)

    # 加载数据
    strategy.load_data(test_data)

    # 测试不同模型
    models_to_test = ["ridge", "rf", "gbdt"]
    results_dict = {}

    for model_type in models_to_test:
        logger.info(f"\n=== 测试模型: {model_type} ===")

        # 运行完整的策略流程
        results = strategy.run_full_pipeline(
            n_factors=50,  # 生成50个因子
            n_best=15,  # 选择15个最佳因子
            model_type=model_type,
            signal_type="rank",
        )

        results_dict[model_type] = results

    # 比较不同模型的结果
    logger.info("\n=== 模型比较结果 ===")
    for model_type, results in results_dict.items():
        metrics = results["performance_metrics"]
        logger.info(
            f"{model_type}: 夏普比率={metrics['sharpe_ratio']:.4f}, 最大回撤={metrics['max_drawdown']:.4f}, IC={results['model_metrics']['ic']:.4f}"
        )

    # 选择表现最好的模型
    best_model = max(
        results_dict.items(),
        key=lambda x: x[1]["performance_metrics"]["sharpe_ratio"]
        if not pd.isna(x[1]["performance_metrics"]["sharpe_ratio"])
        else -np.inf,
    )
    logger.info(f"\n=== 最佳模型: {best_model[0]} ===")
    logger.info("最佳模型绩效:")
    best_results = best_model[1]
    for metric_name, metric_value in best_results["performance_metrics"].items():
        logger.info(f"{metric_name}: {metric_value:.4f}")

    logger.info("\n最佳因子:")
    logger.info(list(best_results["best_factors"].columns))

    logger.info("\n=== 特征重要性 ===")
    logger.info(best_results["feature_importance"].head(10))

    logger.info("\n=== ETH小时级多因子策略 运行完成 ===")


if __name__ == "__main__":
    main()
