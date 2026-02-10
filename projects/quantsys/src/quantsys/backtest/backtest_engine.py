import importlib.util
import itertools
import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from ..common.risk_manager import RiskManager
from ..data.database_manager import DatabaseManager
from ..factors.factor_library import FactorLibrary
from ..models.cost_model import TradeCostModel
from ..models.fill_model import FillModel
from ..models.liquidation_model import LiquidationModel
from ..models.margin_model import MarginModel

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FutureLeakError(RuntimeError):
    pass


class BacktestEngine:
    """
    策略回测引擎，负责执行策略回测，生成回测报告
    支持单策略回测、多策略回测、参数优化等功能
    """

    def __init__(self, config=None):
        """
        初始化回测引擎
        """
        self.config = config or {
            "database": {
                "host": "localhost",
                "port": 5432,
                "database": "quant_trading",
                "user": "postgres",
                "password": "135769",
            },
            "backtest": {
                "initial_capital": 10000,
                "commission": 0.001,
                "maker_fee": 0.0002,
                "taker_fee": 0.0005,
                "slippage": 0.001,
                "risk_free_rate": 0.0,
                "max_trades": 10000,
                "max_drawdown_limit": 0.08,
                "risk_per_trade": 0.008,
                "max_leverage": 10,
            },
        }

        # 数据库管理器（可选）
        use_local_data_only = self.config.get("backtest", {}).get("use_local_data_only", False)
        self.db_manager = None if use_local_data_only else DatabaseManager(self.config["database"])

        # 因子库（数据库策略时才需要）
        self.factor_lib = None if use_local_data_only else FactorLibrary(self.config)

        # 回测结果
        self.backtest_results = {}

        # 策略库
        self.strategies = []

        # 风险管理器
        self.risk_manager = RiskManager(self.config.get("risk", {}))
        self.last_data_info = {}
        self.random_seed = self.config.get("backtest", {}).get("random_seed", 42)

        # Margin and liquidation models
        margin_config = self.config.get("backtest", {})
        self.margin_model = MarginModel(
            initial_margin_rate=margin_config.get("initial_margin_rate", 0.05),
            maintenance_margin_rate=margin_config.get("maintenance_margin_rate", 0.02),
            liquidation_ratio=margin_config.get("liquidation_ratio", 0.8),
            max_leverage=margin_config.get("max_leverage", 10.0),
        )
        self.liquidation_model = LiquidationModel(
            liquidation_ratio=margin_config.get("liquidation_ratio", 0.8)
        )

    def load_strategy(self, strategy_id):
        """
        加载策略
        """
        if self.db_manager is None:
            logger.error("数据库未启用，无法加载策略")
            return None
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
                self.strategies.append(strategy)
                logger.info(f"已加载策略: {strategy['name']}")
                return strategy
            return None
        except Exception as e:
            logger.error(f"加载策略失败: {e}")
            return None

    def load_all_strategies(self):
        """
        加载所有策略
        """
        if self.db_manager is None:
            logger.error("数据库未启用，无法加载策略")
            return []
        try:
            # 从数据库获取所有策略
            query = """
                SELECT strategy_id, name, description, factor_ids, parameters
                FROM strategies
            """
            self.db_manager.cursor.execute(query)
            results = self.db_manager.cursor.fetchall()

            for result in results:
                strategy = {
                    "strategy_id": result[0],
                    "name": result[1],
                    "description": result[2],
                    "factor_ids": result[3],
                    "parameters": result[4],
                }
                self.strategies.append(strategy)

            logger.info(f"已加载 {len(self.strategies)} 个策略")
            return self.strategies
        except Exception as e:
            logger.error(f"加载策略失败: {e}")
            return []

    def _load_strategy_from_file(self, strategy_file: str, strategy_class: str | None):
        """
        从本地文件加载策略类
        """
        strategy_path = os.path.abspath(strategy_file)
        if not os.path.exists(strategy_path):
            logger.error(f"策略文件不存在: {strategy_path}")
            return None

        module_name = f"strategy_{os.path.splitext(os.path.basename(strategy_path))[0]}"
        spec = importlib.util.spec_from_file_location(module_name, strategy_path)
        if spec is None or spec.loader is None:
            logger.error(f"无法加载策略模块: {strategy_path}")
            return None

        module = importlib.util.module_from_spec(spec)
        import sys

        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        if strategy_class:
            strategy_cls = getattr(module, strategy_class, None)
        else:
            strategy_cls = getattr(module, "EthPerpTrendStrategy", None) or getattr(
                module, "EthPerpRangeStrategy", None
            )

        if strategy_cls is None:
            logger.error(
                f"策略类未找到: {strategy_class or 'EthPerpTrendStrategy/EthPerpRangeStrategy'}"
            )
            return None

        return strategy_cls()

    def _load_backtest_data(self, symbol, timeframe, start_time, end_time) -> pd.DataFrame:
        """
        优先从数据库加载数据，失败时尝试读取本地数据文件
        """
        if self.db_manager is not None:
            try:
                df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)
                if df is not None and not df.empty:
                    self.last_data_info = {
                        "source": "database",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "start_time": str(start_time),
                        "end_time": str(end_time),
                        "rows": int(len(df)),
                        "columns": list(df.columns),
                    }
                    return df
            except Exception as e:
                logger.warning(f"从数据库读取数据失败，尝试本地数据: {e}")

        data_path = self.config.get("backtest", {}).get("data_path")
        if not data_path:
            return pd.DataFrame()

        data_abs_path = os.path.abspath(data_path)
        if not os.path.exists(data_abs_path):
            logger.error(f"本地数据文件不存在: {data_abs_path}")
            return pd.DataFrame()

        if data_abs_path.endswith(".feather"):
            df = pd.read_feather(data_abs_path)
        else:
            df = pd.read_csv(data_abs_path)

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
        elif "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)

        if hasattr(df.index, "tz") and df.index.tz is not None:
            df.index = df.index.tz_convert(None)

        if start_time and end_time:
            df = df.loc[start_time:end_time]

        last_modified = None
        try:
            last_modified = datetime.fromtimestamp(os.path.getmtime(data_abs_path)).isoformat()
        except OSError:
            last_modified = None

        self.last_data_info = {
            "source": "file",
            "path": data_abs_path,
            "last_modified": last_modified,
            "rows": int(len(df)),
            "columns": list(df.columns),
            "start_time": str(df.index[0]) if len(df.index) > 0 else None,
            "end_time": str(df.index[-1]) if len(df.index) > 0 else None,
        }

        return df

    def _set_random_seed(self) -> None:
        seed = self.config.get("backtest", {}).get("random_seed", 42)
        self.random_seed = seed
        random.seed(seed)
        np.random.seed(seed)

    def _get_slippage_bps(self, backtest_cfg: dict) -> float:
        if "slippage_bps" in backtest_cfg:
            return float(backtest_cfg.get("slippage_bps", 0.0))
        slippage = float(backtest_cfg.get("slippage", 0.0))
        if slippage <= 0:
            return 0.0
        if slippage < 1:
            return slippage * 10000.0
        return slippage

    def _get_execution_index(self, signal_index: int, total_len: int) -> int | None:
        delay = int(self.config.get("backtest", {}).get("execution_delay_bars", 1))
        if delay < 1:
            raise FutureLeakError("execution_delay_bars must be >= 1 to avoid lookahead")
        exec_index = signal_index + delay
        if exec_index <= signal_index:
            raise FutureLeakError("execution index must be after signal index")
        if exec_index >= total_len:
            return None
        return exec_index

    def _build_models(self, backtest_cfg: dict) -> tuple[FillModel, TradeCostModel]:
        slippage_bps = self._get_slippage_bps(backtest_cfg)
        fill_model = FillModel(slippage_bps=slippage_bps)
        cost_model = TradeCostModel(
            maker_fee=backtest_cfg.get(
                "maker_fee", backtest_cfg.get("fee", backtest_cfg.get("commission", 0.001))
            ),
            taker_fee=backtest_cfg.get(
                "taker_fee", backtest_cfg.get("fee", backtest_cfg.get("commission", 0.001))
            ),
            funding_rate=backtest_cfg.get("funding_rate", 0.0),
            funding_interval_hours=backtest_cfg.get("funding_interval_hours", 8.0),
        )
        return fill_model, cost_model

    def _write_backtest_assumptions(
        self,
        strategy_name: str,
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime,
    ) -> None:
        backtest_cfg = self.config.get("backtest", {})
        report_path = Path(__file__).resolve().parents[3] / "reports" / "backtest_assumptions.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        slippage_bps = self._get_slippage_bps(backtest_cfg)
        data_info = self.last_data_info or {}

        lines = [
            "# Backtest Assumptions",
            "",
            "## Alignment",
            "- signal_time: candle_close",
            f"- execution_time: next_candle_open (execution_delay_bars={backtest_cfg.get('execution_delay_bars', 1)})",
            "",
            "## Fill Model",
            "- market: fill at next open with slippage",
            "- limit: fill if next candle touches limit price",
            "- stop: fill if next candle crosses stop price (market stop)",
            "",
            "## Cost Model",
            f"- maker_fee: {backtest_cfg.get('maker_fee', backtest_cfg.get('fee', backtest_cfg.get('commission', 0.001)))}",
            f"- taker_fee: {backtest_cfg.get('taker_fee', backtest_cfg.get('fee', backtest_cfg.get('commission', 0.001)))}",
            f"- slippage_bps: {slippage_bps}",
            f"- funding_rate: {backtest_cfg.get('funding_rate', 0.0)}",
            f"- funding_interval_hours: {backtest_cfg.get('funding_interval_hours', 8.0)}",
            "",
            "## Reproducibility",
            f"- random_seed: {self.random_seed}",
            "",
            "## Data",
            f"- source: {data_info.get('source')}",
            f"- symbol: {symbol}",
            f"- timeframe: {timeframe}",
            f"- start_time: {start_time}",
            f"- end_time: {end_time}",
            f"- rows: {data_info.get('rows')}",
            f"- path: {data_info.get('path')}",
            f"- last_modified: {data_info.get('last_modified')}",
        ]

        report_path.write_text("\n".join(lines), encoding="utf-8")

    def run_backtest(
        self,
        strategy=None,
        symbol=None,
        timeframe=None,
        start_time=None,
        end_time=None,
        strategy_id=None,
        strategy_file=None,
        strategy_class=None,
    ):
        """
        self._set_random_seed()
        执行回测（支持数据库策略或本地策略文件）
        """
        if strategy_file:
            strategy = self._load_strategy_from_file(strategy_file, strategy_class)
            if strategy is None:
                return None
            strategy_name = getattr(strategy, "name", "local_strategy")
        elif strategy_id is not None:
            strategy = self.load_strategy(strategy_id)
            if not strategy:
                return None
            strategy_name = strategy["name"]
        elif strategy is None:
            logger.error("未提供策略信息")
            return None

        symbol = symbol or self.config["backtest"].get("symbol", "ETH-USDT")
        timeframe = timeframe or self.config["backtest"].get("timeframe", "1h")
        start_time = start_time or datetime.strptime(
            self.config["backtest"].get("start_date", "2025-01-01"), "%Y-%m-%d"
        )
        end_time = end_time or datetime.strptime(
            self.config["backtest"].get("end_date", "2025-12-31"), "%Y-%m-%d"
        )

        logger.info(f"开始回测策略: {strategy_name} - {symbol} {timeframe}")

        # 获取历史数据
        df = self._load_backtest_data(symbol, timeframe, start_time, end_time)
        if df is None or df.empty:
            logger.error(f"未找到交易数据: {symbol} {timeframe}")
            return None

        if hasattr(strategy, "generate_signals"):
            signals = strategy.generate_signals(df)
            params = strategy.get_parameters()
            results = self._execute_backtest(df, signals, params, strategy_name=strategy_name)
            strategy_id = strategy_id if strategy_id is not None else 0
        else:
            # 数据库策略路径
            if self.factor_lib is None:
                logger.error("因子库未初始化，无法执行数据库策略回测")
                return None
            factor_values = {}
            for factor_code in strategy["parameters"]["factors"]:
                factor_df = self.factor_lib.get_factor_values(
                    factor_code, symbol, timeframe, start_time, end_time
                )
                if not factor_df.empty:
                    factor_values[factor_code] = factor_df["value"]
                    df[factor_code] = factor_values[factor_code]
                else:
                    logger.info(f"未找到预计算的因子值: {factor_code}，开始实时计算")
                    if factor_code in self.factor_lib.factors:
                        factor_func = self.factor_lib.factors[factor_code]["func"]
                        factor_values[factor_code] = factor_func(df)
                        df[factor_code] = factor_values[factor_code]
                        logger.info(f"已实时计算因子值: {factor_code}")
                    else:
                        logger.error(f"未知因子: {factor_code}")

            signals = self._generate_signals(df, strategy["parameters"]["signal_config"])
            logger.info(f"生成的信号数量: {len(signals[signals != 0])}")
            logger.info(f"信号分布: {signals.value_counts().to_dict()}")
            results = self._execute_backtest(
                df, signals, strategy["parameters"], strategy_name=strategy_name
            )
            strategy_id = strategy["strategy_id"]

        results["strategy_id"] = strategy_id
        results["strategy_name"] = strategy_name
        results["symbol"] = symbol
        results["timeframe"] = timeframe
        results["start_time"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
        results["end_time"] = end_time.strftime("%Y-%m-%d %H:%M:%S")

        if strategy_id and self.db_manager is not None:
            backtest_id = self.db_manager.insert_backtest_result(
                strategy_id=strategy_id,
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=end_time,
                parameters=results.get("parameters", {}),
                results=results,
            )
            results["backtest_id"] = backtest_id
            self.backtest_results[backtest_id] = results

        logger.info(f"回测完成: {strategy_name} - {symbol} {timeframe}")
        logger.info(f"总利润: {results['total_profit']:.2f} USD")
        logger.info(f"年化收益率: {results['annual_return']:.2%}")
        logger.info(f"夏普比率: {results['sharpe_ratio']:.2f}")
        logger.info(f"最大回撤: {results['max_drawdown']:.2%}")

        self._write_backtest_assumptions(strategy_name, symbol, timeframe, start_time, end_time)

        return results

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
                prev_above = above.shift(1).fillna(False)
                cross_up = above & (~prev_above)
                signals[cross_up] = 1

            elif config["type"] == "cross_down":
                # 因子下穿阈值
                below = factor_values < config["threshold"]
                prev_below = below.shift(1).fillna(False)
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
                prev_above_zero = above_zero.shift(1).fillna(False)
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

    def _execute_backtest(self, df, signals, params, strategy_name="strategy"):
        """
        ????????????
        """
        backtest_cfg = self.config.get("backtest", {})
        maker_fee = backtest_cfg.get(
            "maker_fee", backtest_cfg.get("fee", backtest_cfg.get("commission", 0.001))
        )
        taker_fee = backtest_cfg.get(
            "taker_fee", backtest_cfg.get("fee", backtest_cfg.get("commission", 0.001))
        )

        fill_model, cost_model = self._build_models(backtest_cfg)

        logger.info(f"????????????????????? maker={maker_fee:.6f} taker={taker_fee:.6f}")

        # ?????????????????????
        results = {
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
            "calmar_ratio": 0.0,
            "total_commission": 0.0,
            "total_slippage": 0.0,
            "total_funding": 0.0,
            "trades": [],
            "equity_curve": [],
            "drawdown_curve": [],
            "daily_returns": [],
            "strategy_name": strategy_name,
            "parameters": params,
            "risk_adjustments": [],
        }

        # 初始化保证金和强平模型
        margin_model = self.margin_model
        liquidation_model = self.liquidation_model

        # ?????????????????????
        if isinstance(signals, pd.Series):
            return self._execute_backtest_simple(df, signals, params, results)

        risk_params = params.get("risk_management", {})
        leverage = min(
            risk_params.get("leverage", 1),
            risk_params.get("max_leverage", backtest_cfg.get("max_leverage", 10)),
        )
        risk_per_trade = risk_params.get(
            "risk_per_trade", backtest_cfg.get("risk_per_trade", 0.008)
        )
        cooldown_candles = risk_params.get("cooldown_candles", 0)
        trail_start_mult = risk_params.get("atr_trail_start_mult", 2.5)
        trail_mult = risk_params.get("atr_trail_mult", 1.5)
        max_drawdown_limit = risk_params.get(
            "max_drawdown_limit", backtest_cfg.get("max_drawdown_limit", 0.08)
        )

        order_config = params.get("order_config", {})
        entry_order_type = order_config.get("entry_order_type", "limit")
        exit_order_type = order_config.get("exit_order_type", "limit")
        stop_order_type = order_config.get("stop_order_type", "market")

        initial_capital = backtest_cfg.get("initial_capital", 10000)
        capital = initial_capital
        position = 0
        position_size = 0.0
        entry_price = 0.0
        entry_time = None
        stop_price = None
        cooldown_until = -1
        guard_active = False
        entry_fee = 0.0
        entry_slippage_cost = 0.0

        max_equity = initial_capital

        total_len = len(df)
        for i, (time, row) in enumerate(df.iterrows()):
            exec_index = self._get_execution_index(i, total_len)
            if exec_index is None:
                break

            next_row = df.iloc[exec_index]

            price = float(row["close"])
            atr = float(row.get("atr", np.nan)) if "atr" in row else np.nan

            next_open = float(next_row.get("open", next_row["close"]))
            next_high = float(next_row.get("high", max(next_row["close"], next_open)))
            next_low = float(next_row.get("low", min(next_row["close"], next_open)))

            current_equity = capital + (
                position * position_size * (price - entry_price) if position != 0 else 0
            )
            results["equity_curve"].append(current_equity)

            if current_equity > max_equity:
                max_equity = current_equity
                current_drawdown = 0.0
            else:
                current_drawdown = (max_equity - current_equity) / max_equity
            results["drawdown_curve"].append(current_drawdown)

            if current_drawdown > max_drawdown_limit and not guard_active:
                guard_active = True
                risk_per_trade *= 0.6
                cooldown_candles = max(cooldown_candles, 72)
                results["risk_adjustments"].append(
                    {
                        "time": str(time),
                        "reason": "drawdown_limit",
                        "new_risk_per_trade": risk_per_trade,
                        "new_cooldown_candles": cooldown_candles,
                    }
                )
                logger.warning("??????????????????????????????????????????????????????")

            if position == 0 and i < cooldown_until:
                continue

            enter_long = signals["enter_long"].iloc[i] == 1 if "enter_long" in signals else False
            enter_short = signals["enter_short"].iloc[i] == 1 if "enter_short" in signals else False
            exit_long = signals["exit_long"].iloc[i] == 1 if "exit_long" in signals else False
            exit_short = signals["exit_short"].iloc[i] == 1 if "exit_short" in signals else False
            stop_distance = (
                float(signals["stop_distance"].iloc[i]) if "stop_distance" in signals else 0.0
            )
            taker_entry = signals["taker_entry"].iloc[i] == 1 if "taker_entry" in signals else False
            taker_exit_distance = (
                float(signals["taker_exit_distance"].iloc[i])
                if "taker_exit_distance" in signals
                else 0.0
            )

            # ??????
            if position == 0 and stop_distance > 0:
                if enter_long or enter_short:
                    side = 1 if enter_long else -1
                    self.risk_manager.risk_params["risk_per_trade"] = risk_per_trade
                    self.risk_manager.risk_params["max_leverage"] = leverage
                    position_info = self.risk_manager.calculate_position_size_by_stop(
                        capital, stop_distance, price, leverage
                    )
                    position_size = position_info.get("position_size", 0.0)
                    if position_size <= 0:
                        continue

                    desired_order_type = "market" if taker_entry else entry_order_type
                    fill = fill_model.fill_order(
                        desired_order_type,
                        side,
                        position_size,
                        price,
                        None,
                        next_open,
                        next_high,
                        next_low,
                    )
                    if fill.filled:
                        entry_price = fill.fill_price
                        entry_time = df.index[exec_index]
                        position = side
                        stop_price = (
                            entry_price - stop_distance
                            if position == 1
                            else entry_price + stop_distance
                        )

                        entry_notional = position_size * entry_price
                        entry_slippage_cost = cost_model.slippage_cost(
                            fill.base_price or entry_price, entry_price, position_size
                        )
                        entry_costs = cost_model.calculate(
                            entry_notional,
                            desired_order_type == "market",
                            entry_slippage_cost,
                            0.0,
                            position,
                        )
                        entry_fee = entry_costs.fee
                        capital -= entry_fee
                        results["total_commission"] += entry_fee
                        results["total_slippage"] += entry_costs.slippage_cost

            # ????????????
            if position != 0:
                # ATR????????????
                if (
                    not np.isnan(atr)
                    and atr > 0
                    and abs(price - entry_price) >= atr * trail_start_mult
                ):
                    if position == 1:
                        stop_price = max(stop_price, price - atr * trail_mult)
                    else:
                        stop_price = min(stop_price, price + atr * trail_mult)

                stop_fill = None
                stop_triggered = False
                stop_side = -position
                if stop_price is not None:
                    stop_fill = fill_model.fill_order(
                        stop_order_type,
                        stop_side,
                        position_size,
                        None,
                        stop_price,
                        next_open,
                        next_high,
                        next_low,
                    )
                    stop_triggered = stop_fill.filled

                exit_signal = (position == 1 and exit_long) or (position == -1 and exit_short)
                exit_order_type_used = exit_order_type
                if (
                    exit_signal
                    and taker_exit_distance > 0
                    and abs(price - entry_price) >= taker_exit_distance
                ):
                    exit_order_type_used = "market"

                exit_fill = None
                if stop_triggered:
                    exit_fill = stop_fill
                    exit_order_type_used = stop_order_type
                elif exit_signal:
                    exit_fill = fill_model.fill_order(
                        exit_order_type_used,
                        -position,
                        position_size,
                        price,
                        None,
                        next_open,
                        next_high,
                        next_low,
                    )

                if exit_fill and exit_fill.filled:
                    exit_price = exit_fill.fill_price
                    exit_time = df.index[exec_index]
                    profit = position * position_size * (exit_price - entry_price)
                    capital += profit

                    exit_notional = position_size * exit_price
                    exit_slippage_cost = cost_model.slippage_cost(
                        exit_fill.base_price or exit_price, exit_price, position_size
                    )
                    hours_held = 0.0
                    if entry_time is not None:
                        hours_held = (exit_time - entry_time).total_seconds() / 3600.0

                    exit_costs = cost_model.calculate(
                        exit_notional,
                        exit_order_type_used == "market" or stop_triggered,
                        exit_slippage_cost,
                        hours_held,
                        position,
                    )
                    capital -= exit_costs.fee
                    capital -= exit_costs.funding_cost

                    results["total_commission"] += exit_costs.fee
                    results["total_slippage"] += exit_costs.slippage_cost
                    results["total_funding"] += exit_costs.funding_cost

                    total_slippage = entry_slippage_cost + exit_slippage_cost
                    total_cost = (
                        entry_fee + exit_costs.fee + exit_costs.funding_cost + total_slippage
                    )
                    profit_net = profit - entry_fee - exit_costs.fee - exit_costs.funding_cost

                    trade = {
                        "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S")
                        if entry_time
                        else None,
                        "exit_time": exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "position": position,
                        "position_size": position_size,
                        "profit": profit,
                        "profit_net": profit_net,
                        "profit_pct": (exit_price - entry_price) / entry_price * 100 * position,
                        "commission": entry_fee + exit_costs.fee,
                        "entry_fee": entry_fee,
                        "exit_fee": exit_costs.fee,
                        "slippage": total_slippage,
                        "funding_cost": exit_costs.funding_cost,
                        "total_cost": total_cost,
                        "stop_triggered": stop_triggered,
                        "entry_order_type": "market" if taker_entry else entry_order_type,
                        "exit_order_type": exit_order_type_used,
                    }
                    results["trades"].append(trade)

                    results["total_trades"] += 1
                    if profit_net > 0:
                        results["winning_trades"] += 1
                        results["avg_win"] += profit_net
                    else:
                        results["losing_trades"] += 1
                        results["avg_loss"] += profit_net

                    position = 0
                    position_size = 0.0
                    entry_price = 0.0
                    entry_time = None
                    stop_price = None
                    entry_fee = 0.0
                    entry_slippage_cost = 0.0
                    cooldown_until = i + cooldown_candles

                    if results["total_trades"] > backtest_cfg.get("max_trades", 10000):
                        logger.warning(
                            f"????????????????????????: {backtest_cfg.get('max_trades', 10000)}"
                        )
                        break

        # ??????????????????
        last_close_price = float(df["close"].iloc[-1])
        final_equity = capital + (
            position * position_size * (last_close_price - entry_price) if position != 0 else 0
        )
        results["equity_curve"].append(final_equity)

        self._calculate_backtest_metrics(results, df)
        return results

    def _execute_backtest_simple(self, df, signals, params, results):
        """
        简单回测执行方法，集成保证金和强平逻辑
        """
        backtest_cfg = self.config.get("backtest", {})
        fill_model, cost_model = self._build_models(backtest_cfg)

        # 初始化保证金和强平模型
        margin_model = self.margin_model
        liquidation_model = self.liquidation_model

        initial_capital = backtest_cfg.get("initial_capital", 10000)
        capital = initial_capital
        position_side = 0
        position_qty = 0.0
        entry_price = 0.0
        entry_time = None
        entry_fee = 0.0
        entry_slippage_cost = 0.0
        max_equity = initial_capital

        # 添加杠杆配置
        leverage = params.get("risk_management", {}).get("leverage", 1.0)
        leverage = min(leverage, backtest_cfg.get("max_leverage", 10.0))

        position_size_pct = params.get("risk_management", {}).get("position_size", 1.0)
        position_size_pct = max(0.0, min(1.0, position_size_pct))

        total_len = len(df)
        for i, (time, row) in enumerate(df.iterrows()):
            exec_index = self._get_execution_index(i, total_len)
            if exec_index is None:
                break

            next_row = df.iloc[exec_index]
            price = float(row["close"])

            next_open = float(next_row.get("open", next_row["close"]))
            next_high = float(next_row.get("high", max(next_row["close"], next_open)))
            next_low = float(next_row.get("low", min(next_row["close"], next_open)))

            # 计算当前保证金状态
            margin_state = margin_model.calculate_margin_state(
                initial_capital=initial_capital,
                balance=capital,
                position_qty=position_qty,
                position_side=position_side,
                entry_price=entry_price,
                current_price=price,
            )

            # 检查强平条件
            is_liquidation, liquidation_price = liquidation_model.check_liquidation(margin_state)

            if is_liquidation and position_side != 0:
                # 执行强平
                liquidation_event = liquidation_model.execute_liquidation(margin_state, str(time))
                logger.warning(f"强平触发: {liquidation_event.liquidation_reason}")

                # 记录强平事件
                if "liquidation_events" not in results:
                    results["liquidation_events"] = []
                results["liquidation_events"].append(
                    {
                        "timestamp": liquidation_event.timestamp,
                        "position_qty": liquidation_event.position_qty,
                        "position_side": liquidation_event.position_side,
                        "entry_price": liquidation_event.entry_price,
                        "liquidation_price": liquidation_event.liquidation_price,
                        "equity": liquidation_event.equity,
                        "maintenance_margin": liquidation_event.maintenance_margin,
                        "margin_ratio": liquidation_event.margin_ratio,
                        "liquidation_reason": liquidation_event.liquidation_reason,
                    }
                )

                # 执行强平交易
                fill = fill_model.fill_order(
                    "market",
                    -position_side,
                    position_qty,
                    price,
                    None,
                    next_open,
                    next_high,
                    next_low,
                )

                if fill.filled:
                    exit_price = liquidation_price  # 使用强平价格
                    exit_time = df.index[exec_index]
                    profit = position_side * position_qty * (exit_price - entry_price)
                    capital += profit

                    exit_slippage_cost = cost_model.slippage_cost(
                        fill.base_price or exit_price, exit_price, position_qty
                    )
                    hours_held = 0.0
                    if entry_time is not None:
                        hours_held = (exit_time - entry_time).total_seconds() / 3600.0

                    exit_costs = cost_model.calculate(
                        position_qty * exit_price,
                        True,
                        exit_slippage_cost,
                        hours_held,
                        position_side,
                    )
                    capital -= exit_costs.fee
                    capital -= exit_costs.funding_cost

                    results["total_commission"] += exit_costs.fee
                    results["total_slippage"] += exit_costs.slippage_cost
                    results["total_funding"] += exit_costs.funding_cost

                    total_slippage = entry_slippage_cost + exit_slippage_cost
                    total_cost = (
                        entry_fee + exit_costs.fee + exit_costs.funding_cost + total_slippage
                    )
                    profit_net = profit - entry_fee - exit_costs.fee - exit_costs.funding_cost

                    # 记录强平交易
                    trade = {
                        "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S")
                        if entry_time
                        else None,
                        "exit_time": exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "position": position_qty,
                        "position_side": position_side,
                        "profit": profit,
                        "profit_net": profit_net,
                        "profit_pct": (exit_price - entry_price)
                        / entry_price
                        * 100
                        * position_side,
                        "commission": entry_fee + exit_costs.fee,
                        "entry_fee": entry_fee,
                        "exit_fee": exit_costs.fee,
                        "slippage": total_slippage,
                        "funding_cost": exit_costs.funding_cost,
                        "total_cost": total_cost,
                        "equity_before": margin_state.equity,
                        "equity_after": capital + profit_net,
                        "margin_used": margin_state.margin_used,
                        "liquidation_flag": True,
                        "liquidation_price": exit_price,
                    }
                    results["trades"].append(trade)
                    results["total_trades"] += 1

                    if profit_net > 0:
                        results["winning_trades"] += 1
                        results["avg_win"] += profit_net
                    else:
                        results["losing_trades"] += 1
                        results["avg_loss"] += profit_net

                    # 重置仓位
                    position_side = 0
                    position_qty = 0.0
                    entry_price = 0.0
                    entry_time = None
                    entry_fee = 0.0
                    entry_slippage_cost = 0.0
                continue

            # 记录当前权益和回撤
            results["equity_curve"].append(margin_state.equity)

            if margin_state.equity > max_equity:
                max_equity = margin_state.equity
                current_drawdown = 0
            else:
                current_drawdown = (max_equity - margin_state.equity) / max_equity
            results["drawdown_curve"].append(current_drawdown)

            signal = signals.iloc[i]
            if signal == 1 and position_side == 0:
                # 计算最大允许持仓大小
                max_position_size = margin_model.calculate_max_position_size(
                    balance=capital, price=price, leverage=leverage
                )

                # 计算实际持仓大小（考虑仓位比例）
                position_qty = max_position_size * position_size_pct

                # 检查保证金是否充足
                required_margin = margin_model.calculate_initial_margin(
                    notional_value=position_qty * price
                )

                if not margin_model.is_margin_sufficient(capital, required_margin):
                    logger.warning(
                        f"保证金不足，无法开仓: 可用余额 {capital:.2f}, 所需保证金 {required_margin:.2f}"
                    )
                    continue

                fill = fill_model.fill_order(
                    "market",
                    1,
                    position_qty,
                    price,
                    None,
                    next_open,
                    next_high,
                    next_low,
                )
                if not fill.filled:
                    continue

                entry_price = fill.fill_price
                entry_time = df.index[exec_index]
                position_side = 1

                entry_slippage_cost = cost_model.slippage_cost(
                    fill.base_price or entry_price, entry_price, position_qty
                )
                entry_costs = cost_model.calculate(
                    position_qty * entry_price,
                    True,
                    entry_slippage_cost,
                    0.0,
                    position_side,
                )
                entry_fee = entry_costs.fee
                capital -= entry_fee
                results["total_commission"] += entry_fee
                results["total_slippage"] += entry_costs.slippage_cost

                if results["total_trades"] > backtest_cfg.get(
                    "max_trades", backtest_cfg.get("max_trades", 10000)
                ):
                    logger.warning(
                        f"????????????????????????: {backtest_cfg.get('max_trades', 10000)}"
                    )
                    break

            elif signal == -1 and position_side != 0:
                fill = fill_model.fill_order(
                    "market",
                    -position_side,
                    position_qty,
                    price,
                    None,
                    next_open,
                    next_high,
                    next_low,
                )
                if not fill.filled:
                    continue

                exit_price = fill.fill_price
                exit_time = df.index[exec_index]

                # 计算盈亏和保证金变化
                profit = position_side * position_qty * (exit_price - entry_price)

                # 计算平仓前的保证金状态
                margin_state_before = margin_model.calculate_margin_state(
                    initial_capital=initial_capital,
                    balance=capital,
                    position_qty=position_qty,
                    position_side=position_side,
                    entry_price=entry_price,
                    current_price=price,
                )

                # 计算交易成本
                exit_slippage_cost = cost_model.slippage_cost(
                    fill.base_price or exit_price, exit_price, position_qty
                )
                hours_held = 0.0
                if entry_time is not None:
                    hours_held = (exit_time - entry_time).total_seconds() / 3600.0

                exit_costs = cost_model.calculate(
                    position_qty * exit_price,
                    True,
                    exit_slippage_cost,
                    hours_held,
                    position_side,
                )

                # 更新资金
                capital += profit
                capital -= exit_costs.fee
                capital -= exit_costs.funding_cost

                results["total_commission"] += exit_costs.fee
                results["total_slippage"] += exit_costs.slippage_cost
                results["total_funding"] += exit_costs.funding_cost

                total_slippage = entry_slippage_cost + exit_slippage_cost
                total_cost = entry_fee + exit_costs.fee + exit_costs.funding_cost + total_slippage
                profit_net = profit - entry_fee - exit_costs.fee - exit_costs.funding_cost

                # 计算平仓后的保证金状态
                margin_state_after = margin_model.calculate_margin_state(
                    initial_capital=initial_capital,
                    balance=capital,
                    position_qty=0,
                    position_side=0,
                    entry_price=0,
                    current_price=exit_price,
                )

                # 记录交易，包含可复算字段
                trade = {
                    "entry_time": entry_time.strftime("%Y-%m-%d %H:%M:%S") if entry_time else None,
                    "exit_time": exit_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "position": position_qty,
                    "position_side": position_side,
                    "profit": profit,
                    "profit_net": profit_net,
                    "profit_pct": (exit_price - entry_price) / entry_price * 100 * position_side,
                    "commission": entry_fee + exit_costs.fee,
                    "entry_fee": entry_fee,
                    "exit_fee": exit_costs.fee,
                    "slippage": total_slippage,
                    "funding_cost": exit_costs.funding_cost,
                    "total_cost": total_cost,
                    "equity_before": margin_state_before.equity,
                    "equity_after": margin_state_after.equity,
                    "margin_used": margin_state_before.margin_used,
                    "liquidation_flag": False,
                    "liquidation_price": 0.0,
                }
                results["trades"].append(trade)
                results["total_trades"] += 1

                if profit_net > 0:
                    results["winning_trades"] += 1
                    results["avg_win"] += profit_net
                else:
                    results["losing_trades"] += 1
                    results["avg_loss"] += profit_net

                position_side = 0
                position_qty = 0.0
                entry_price = 0.0
                entry_time = None
                entry_fee = 0.0
                entry_slippage_cost = 0.0

        last_close_price = float(df["close"].iloc[-1])

        # 计算最终保证金状态
        final_margin_state = margin_model.calculate_margin_state(
            initial_capital=initial_capital,
            balance=capital,
            position_qty=position_qty,
            position_side=position_side,
            entry_price=entry_price,
            current_price=last_close_price,
        )

        results["equity_curve"].append(final_margin_state.equity)

        # 添加最终保证金状态到结果
        results["final_margin_state"] = {
            "balance": final_margin_state.balance,
            "equity": final_margin_state.equity,
            "margin_used": final_margin_state.margin_used,
            "available_balance": final_margin_state.available_balance,
            "leverage": final_margin_state.leverage,
            "margin_ratio": final_margin_state.margin_ratio,
        }

        self._calculate_backtest_metrics(results, df)
        return results

    def _calculate_backtest_metrics(self, results, df):
        """
        计算回测指标
        """
        # 计算平均盈亏
        if results["winning_trades"] > 0:
            results["avg_win"] /= results["winning_trades"]

        if results["losing_trades"] > 0:
            results["avg_loss"] /= results["losing_trades"]

        # 计算胜率
        if results["total_trades"] > 0:
            results["win_rate"] = results["winning_trades"] / results["total_trades"]

        # 计算总利润
        results["total_profit"] = (
            results["equity_curve"][-1] - self.config["backtest"]["initial_capital"]
        )
        if self.config["backtest"]["initial_capital"] > 0:
            results["total_return"] = (
                results["total_profit"] / self.config["backtest"]["initial_capital"]
            )
        else:
            results["total_return"] = 0.0

        # 计算最大回撤
        if results["drawdown_curve"]:
            results["max_drawdown"] = max(results["drawdown_curve"])

        # 计算年化收益率
        days = (df.index[-1] - df.index[0]).days
        if days > 0:
            results["annual_return"] = (
                results["equity_curve"][-1] / self.config["backtest"]["initial_capital"]
            ) ** (365 / days) - 1

        # 计算夏普比率
        equity_curve = pd.Series(results["equity_curve"])
        daily_returns = equity_curve.pct_change().dropna()
        results["daily_returns"] = daily_returns.tolist()

        if len(daily_returns) > 0:
            return_mean = daily_returns.mean()
            return_std = daily_returns.std()

            if return_std > 0:
                risk_free_rate = self.config["backtest"].get("risk_free_rate", 0.0)
                results["sharpe_ratio"] = (
                    (return_mean - risk_free_rate / 252) / return_std * np.sqrt(252)
                )

        # 计算索提诺比率
        if len(daily_returns) > 0:
            negative_returns = daily_returns[daily_returns < 0]
            if len(negative_returns) > 0:
                downside_std = negative_returns.std()
                if downside_std > 0:
                    risk_free_rate = self.config["backtest"].get("risk_free_rate", 0.0)
                    results["sortino_ratio"] = (
                        (return_mean - risk_free_rate / 252) / downside_std * np.sqrt(252)
                    )

        # 计算卡尔玛比率
        if results["max_drawdown"] > 0:
            results["calmar_ratio"] = results["annual_return"] / results["max_drawdown"]

        # 计算利润因子
        total_win = results["winning_trades"] * results["avg_win"]
        total_loss = abs(results["losing_trades"] * results["avg_loss"])
        if total_loss > 0:
            results["profit_factor"] = total_win / total_loss

        # 计算平均持仓时间（小时）
        if results["trades"]:
            durations = []
            for trade in results["trades"]:
                try:
                    entry = datetime.strptime(trade["entry_time"], "%Y-%m-%d %H:%M:%S")
                    exit_time = datetime.strptime(trade["exit_time"], "%Y-%m-%d %H:%M:%S")
                    durations.append((exit_time - entry).total_seconds() / 3600.0)
                except Exception:
                    continue
            if durations:
                results["avg_holding_hours"] = sum(durations) / len(durations)
            else:
                results["avg_holding_hours"] = 0.0
        else:
            results["avg_holding_hours"] = 0.0

    def run_batch_backtest(self, symbols, timeframes, start_time, end_time):
        """
        批量回测所有加载的策略
        """
        logger.info(f"开始批量回测，共 {len(self.strategies)} 个策略")

        all_results = []
        for strategy in self.strategies:
            for symbol in symbols:
                for timeframe in timeframes:
                    result = self.run_backtest(strategy, symbol, timeframe, start_time, end_time)
                    if result:
                        all_results.append(result)

        logger.info(f"批量回测完成，共回测 {len(all_results)} 个策略实例")
        return all_results

    def optimize_parameters(self, strategy, symbol, timeframe, start_time, end_time, param_ranges):
        """
        参数优化
        """
        logger.info(f"开始参数优化: {strategy['name']} - {symbol} {timeframe}")

        # 生成参数组合
        param_names = list(param_ranges.keys())
        param_values = list(param_ranges.values())
        param_combinations = list(itertools.product(*param_values))

        logger.info(f"生成了 {len(param_combinations)} 个参数组合")

        # 存储最优结果
        best_result = None
        best_params = None
        best_profit = -np.inf

        # 遍历所有参数组合
        for i, params in enumerate(param_combinations):
            # 更新策略参数
            for name, value in zip(param_names, params):
                # 递归更新参数
                self._update_param(strategy["parameters"], name, value)

            # 执行回测
            result = self.run_backtest(strategy, symbol, timeframe, start_time, end_time)

            # 比较结果
            if result and result["total_profit"] > best_profit:
                best_profit = result["total_profit"]
                best_result = result
                best_params = dict(zip(param_names, params))

            # 显示进度
            if (i + 1) % 10 == 0:
                logger.info(f"参数优化进度: {i + 1}/{len(param_combinations)}")

        logger.info(f"参数优化完成，最优参数: {best_params}")
        logger.info(f"最优总利润: {best_profit:.2f} USD")

        return {
            "best_params": best_params,
            "best_result": best_result,
            "all_results": self.backtest_results,
        }

    def _update_param(self, params, param_path, value):
        """
        递归更新参数
        """
        if "." in param_path:
            # 处理嵌套参数，如 risk_management.position_size
            path_parts = param_path.split(".")
            current = params
            for part in path_parts[:-1]:
                if part not in current:
                    current[part] = {}
                current = current[part]
            current[path_parts[-1]] = value
        else:
            # 处理顶级参数
            params[param_path] = value

    def generate_backtest_report(self, backtest_id, output_path):
        """
        生成回测报告
        """
        if backtest_id not in self.backtest_results:
            logger.error(f"回测结果不存在: {backtest_id}")
            return False

        results = self.backtest_results[backtest_id]

        # 生成报告
        report = {
            "report_generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy": {"id": results["strategy_id"], "name": results["strategy_name"]},
            "backtest_config": {
                "symbol": results["symbol"],
                "timeframe": results["timeframe"],
                "start_time": results["start_time"],
                "end_time": results["end_time"],
                "initial_capital": self.config["backtest"]["initial_capital"],
                "commission": self.config["backtest"].get(
                    "commission", self.config["backtest"].get("fee", 0.001)
                ),
                "maker_fee": self.config["backtest"].get(
                    "maker_fee", self.config["backtest"].get("fee", 0.001)
                ),
                "taker_fee": self.config["backtest"].get(
                    "taker_fee", self.config["backtest"].get("fee", 0.001)
                ),
                "slippage": self.config["backtest"].get("slippage", 0.0),
            },
            "performance_metrics": {
                "total_trades": results["total_trades"],
                "winning_trades": results["winning_trades"],
                "losing_trades": results["losing_trades"],
                "profit_factor": results["profit_factor"],
                "win_rate": results["win_rate"],
                "avg_win": results["avg_win"],
                "avg_loss": results["avg_loss"],
                "max_drawdown": results["max_drawdown"],
                "total_profit": results["total_profit"],
                "annual_return": results["annual_return"],
                "sharpe_ratio": results["sharpe_ratio"],
                "sortino_ratio": results["sortino_ratio"],
                "calmar_ratio": results["calmar_ratio"],
                "total_commission": results["total_commission"],
                "total_slippage": results["total_slippage"],
                "total_funding": results.get("total_funding", 0.0),
            },
            "trades": results["trades"][:50],  # 只显示前50笔交易
            "equity_curve": results["equity_curve"],
            "drawdown_curve": results["drawdown_curve"],
        }

        # 保存报告到JSON文件
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"回测报告已生成: {output_path}")
        return True

    def get_backtest_result(self, backtest_id):
        """
        获取回测结果
        """
        return self.backtest_results.get(backtest_id)

    def get_all_backtest_results(self):
        """
        获取所有回测结果
        """
        return self.backtest_results

    def close(self):
        """
        关闭数据库连接
        """
        if self.factor_lib is not None:
            self.factor_lib.close()
        if self.db_manager is not None:
            self.db_manager.disconnect()


# 示例使用
if __name__ == "__main__":
    # 创建回测引擎实例
    backtest_engine = BacktestEngine()

    try:
        # 加载策略
        strategy = backtest_engine.load_strategy(1)  # 假设策略ID为1

        if strategy:
            # 设置回测参数
            symbol = "ETH-USDT"
            timeframe = "1h"
            start_time = datetime(2025, 1, 1)
            end_time = datetime(2025, 12, 31)

            # 执行回测
            results = backtest_engine.run_backtest(
                strategy, symbol, timeframe, start_time, end_time
            )

            # 生成回测报告
            backtest_engine.generate_backtest_report(results["backtest_id"], "backtest_report.json")

            # 参数优化示例
            # param_ranges = {
            #     'risk_management.stop_loss': [0.01, 0.02, 0.05, 0.1],
            #     'risk_management.take_profit': [0.02, 0.05, 0.1, 0.2],
            #     'risk_management.position_size': [0.1, 0.2, 0.3, 0.5]
            # }
            # optimization_results = backtest_engine.optimize_parameters(strategy, symbol, timeframe, start_time, end_time, param_ranges)

    except Exception as e:
        logger.error(f"回测失败: {e}")
    finally:
        # 关闭连接
        backtest_engine.close()
