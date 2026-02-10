import logging
import os
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..common.config_loader import ConfigLoader
from ..data.database_manager import DatabaseManager
from .factor_registry import FactorRegistry, UnregisteredFactorError

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FactorLibrary:
    """
    因子库管理器，用于定义、计算、存储和查询因子
    """

    def __init__(self, config=None):
        """
        初始化因子库管理器
        """
        # 如果没有提供配置，使用配置加载器加载
        if not config:
            config_loader = ConfigLoader()
            config = config_loader.load_config("config")
        
        self.config = config
        
        # 确保数据库配置存在
        if "database" not in self.config:
            self.config["database"] = {
                "host": "localhost",
                "port": 5432,
                "database": "quant_trading",
                "user": "postgres",
                "password": "postgres",
            }

        # 数据库管理器
        self.db_manager = DatabaseManager(self.config["database"])

        registry_path = self.config.get("factor_registry_path")
        if not registry_path:
            registry_path = os.path.join(os.path.dirname(__file__), "factor_registry.json")
        self.factor_registry = FactorRegistry(registry_path)

        # 数据源管理器
        self.data_source_manager = None

        # 数据可用性管理
        from ..data.availability import DataAvailability

        self.availability = DataAvailability()

        # 已定义的因子
        self.factors = {
            # 传统因子 - 价格类
            "ma": {"name": "Moving Average", "type": "price", "func": self.calculate_ma},
            "ema": {
                "name": "Exponential Moving Average",
                "type": "price",
                "func": self.calculate_ema,
            },
            "bb": {"name": "Bollinger Bands", "type": "price", "func": self.calculate_bb},
            "rsi": {"name": "Relative Strength Index", "type": "price", "func": self.calculate_rsi},
            "macd": {
                "name": "Moving Average Convergence Divergence",
                "type": "price",
                "func": self.calculate_macd,
            },
            "stoch": {
                "name": "Stochastic Oscillator",
                "type": "price",
                "func": self.calculate_stoch,
            },
            "atr": {"name": "Average True Range", "type": "price", "func": self.calculate_atr},
            "cci": {"name": "Commodity Channel Index", "type": "price", "func": self.calculate_cci},
            "roc": {"name": "Rate of Change", "type": "price", "func": self.calculate_roc},
            "adx": {
                "name": "Average Directional Index",
                "type": "price",
                "func": self.calculate_adx,
            },
            "std_dev": {
                "name": "Standard Deviation",
                "type": "price",
                "func": self.calculate_std_dev,
            },
            "price_rate_of_change": {
                "name": "Price Rate of Change",
                "type": "price",
                "func": self.calculate_price_rate_of_change,
            },
            "stoch_k": {
                "name": "Stochastic K Value",
                "type": "price",
                "func": self.calculate_stoch_k,
            },
            # 传统因子 - 成交量类
            "vol_ma": {
                "name": "Volume Moving Average",
                "type": "volume",
                "func": self.calculate_vol_ma,
            },
            "obv": {"name": "On-Balance Volume", "type": "volume", "func": self.calculate_obv},
            "vwap": {
                "name": "Volume Weighted Average Price",
                "type": "volume",
                "func": self.calculate_vwap,
            },
            "mfi": {"name": "Money Flow Index", "type": "volume", "func": self.calculate_mfi},
            "volume_rate_of_change": {
                "name": "Volume Rate of Change",
                "type": "volume",
                "func": self.calculate_volume_rate_of_change,
            },
            "vwap_rate_of_change": {
                "name": "VWAP Rate of Change",
                "type": "volume",
                "func": self.calculate_vwap_rate_of_change,
            },
            # 传统因子 - 波动率类
            "volatility": {
                "name": "Volatility",
                "type": "volatility",
                "func": self.calculate_volatility,
            },
            "return_volatility": {
                "name": "Return Volatility",
                "type": "volatility",
                "func": self.calculate_return_volatility,
            },
            "historical_volatility": {
                "name": "Historical Volatility",
                "type": "volatility",
                "func": self.calculate_historical_volatility,
            },
            "realized_volatility": {
                "name": "Realized Volatility",
                "type": "volatility",
                "func": self.calculate_realized_volatility,
            },
            # 传统因子 - 动量类
            "momentum": {"name": "Momentum", "type": "momentum", "func": self.calculate_momentum},
            "williams_r": {
                "name": "Williams %R",
                "type": "momentum",
                "func": self.calculate_williams_r,
            },
            "tsi": {"name": "True Strength Index", "type": "momentum", "func": self.calculate_tsi},
            "rsi_rate_of_change": {
                "name": "RSI Rate of Change",
                "type": "momentum",
                "func": self.calculate_rsi_rate_of_change,
            },
            "roc_momentum": {
                "name": "ROC Momentum",
                "type": "momentum",
                "func": self.calculate_roc_momentum,
            },
            # 传统因子 - 趋势类
            "dmi": {
                "name": "Directional Movement Index",
                "type": "trend",
                "func": self.calculate_dmi,
            },
            "parabolic_sar": {
                "name": "Parabolic SAR",
                "type": "trend",
                "func": self.calculate_parabolic_sar,
            },
            "ichimoku": {
                "name": "Ichimoku Cloud",
                "type": "trend",
                "func": self.calculate_ichimoku,
            },
            "trend_slope": {
                "name": "Trend Slope",
                "type": "trend",
                "func": self.calculate_trend_slope,
            },
            "ma_crossover": {
                "name": "MA Crossover",
                "type": "trend",
                "func": self.calculate_ma_crossover,
            },
            "trend_strength": {
                "name": "Trend Strength",
                "type": "trend",
                "func": self.calculate_trend_strength,
            },
            # 前沿因子 - 链上因子 (On-Chain)
            "mvrv": {
                "name": "Market Value to Realized Value",
                "type": "on_chain",
                "func": self.calculate_mvrv,
            },
            "nupl": {
                "name": "Net Unrealized Profit/Loss",
                "type": "on_chain",
                "func": self.calculate_nupl,
            },
            "sopr": {
                "name": "Spent Output Profit Ratio",
                "type": "on_chain",
                "func": self.calculate_sopr,
            },
            "exchange_net_flow": {
                "name": "Exchange Net Flow",
                "type": "on_chain",
                "func": self.calculate_exchange_net_flow,
            },
            "miner_balance": {
                "name": "Miner Balance",
                "type": "on_chain",
                "func": self.calculate_miner_balance,
            },
            "active_addresses": {
                "name": "Active Addresses",
                "type": "on_chain",
                "func": self.calculate_active_addresses,
            },
            "realized_cap": {
                "name": "Realized Cap",
                "type": "on_chain",
                "func": self.calculate_realized_cap,
            },
            # 前沿因子 - 加密专属因子 (Crypto Exclusive)
            "funding_rate": {
                "name": "Funding Rate",
                "type": "crypto_exclusive",
                "func": self.calculate_funding_rate,
            },
            "open_interest": {
                "name": "Open Interest",
                "type": "crypto_exclusive",
                "func": self.calculate_open_interest,
            },
            "liquidations": {
                "name": "Liquidation Data",
                "type": "crypto_exclusive",
                "func": self.calculate_liquidations,
            },
            "long_short_ratio": {
                "name": "Long/Short Ratio",
                "type": "crypto_exclusive",
                "func": self.calculate_long_short_ratio,
            },
            "stablecoin_premium": {
                "name": "Stablecoin Premium",
                "type": "crypto_exclusive",
                "func": self.calculate_stablecoin_premium,
            },
            # 前沿因子 - 情绪因子 (Sentiment)
            "social_sentiment": {
                "name": "Social Sentiment",
                "type": "sentiment",
                "func": self.calculate_social_sentiment,
            },
            "twitter_mentions": {
                "name": "Twitter Mentions",
                "type": "sentiment",
                "func": self.calculate_twitter_mentions,
            },
            "reddit_activity": {
                "name": "Reddit Activity",
                "type": "sentiment",
                "func": self.calculate_reddit_activity,
            },
            "news_sentiment": {
                "name": "News Sentiment",
                "type": "sentiment",
                "func": self.calculate_news_sentiment,
            },
            # 前沿因子 - 另类数据因子 (Alternative Data)
            "dev_activity": {
                "name": "Development Activity",
                "type": "alternative",
                "func": self.calculate_dev_activity,
            },
            "github_commits": {
                "name": "GitHub Commits",
                "type": "alternative",
                "func": self.calculate_github_commits,
            },
            "community_growth": {
                "name": "Community Growth",
                "type": "alternative",
                "func": self.calculate_community_growth,
            },
            "alt_rank": {"name": "AltRank", "type": "alternative", "func": self.calculate_alt_rank},
            # 前沿因子 - AI/ML因子 (AI/ML)
            "ai_momentum": {
                "name": "AI Momentum",
                "type": "ai_ml",
                "func": self.calculate_ai_momentum,
            },
            "ai_volatility": {
                "name": "AI Volatility",
                "type": "ai_ml",
                "func": self.calculate_ai_volatility,
            },
            "gnn_topology": {
                "name": "GNN Topology Feature",
                "type": "ai_ml",
                "func": self.calculate_gnn_topology,
            },
            "auto_factor": {
                "name": "Auto-Generated Factor",
                "type": "ai_ml",
                "func": self.calculate_auto_factor,
            },
            # 因子生成方法 - 导航文档中提到的因子生成器
            "auto_factor_generator": {
                "name": "Auto Factor Generator",
                "type": "ai_ml",
                "func": self.calculate_auto_factor_generator,
            },
            "layered_factor_generator": {
                "name": "5-Layer Factor Generator",
                "type": "ai_ml",
                "func": self.calculate_layered_factor_generator,
            },
            "dl_factor_generator": {
                "name": "Deep Learning Factor Generator",
                "type": "ai_ml",
                "func": self.calculate_dl_factor_generator,
            },
            "multi_factor_generator": {
                "name": "Multi-Factor Generator",
                "type": "ai_ml",
                "func": self.calculate_multi_factor_generator,
            },
            # Alpha因子 - 重点使用的Alpha因子
            "alpha009": {"name": "Alpha 009", "type": "momentum", "func": self.calculate_alpha009},
            "alpha042": {"name": "Alpha 042", "type": "momentum", "func": self.calculate_alpha042},
            "alpha068": {"name": "Alpha 068", "type": "trend", "func": self.calculate_alpha068},
            "alpha070": {
                "name": "Alpha 070",
                "type": "volatility",
                "func": self.calculate_alpha070,
            },
            "alpha081": {"name": "Alpha 081", "type": "volume", "func": self.calculate_alpha081},
            "alpha095": {
                "name": "Alpha 095",
                "type": "volatility",
                "func": self.calculate_alpha095,
            },
            "alpha097": {
                "name": "Alpha 097",
                "type": "volatility",
                "func": self.calculate_alpha097,
            },
            "alpha100": {
                "name": "Alpha 100",
                "type": "volatility",
                "func": self.calculate_alpha100,
            },
            "alpha120": {"name": "Alpha 120", "type": "momentum", "func": self.calculate_alpha120},
            "alpha125": {"name": "Alpha 125", "type": "trend", "func": self.calculate_alpha125},
            "alpha126": {"name": "Alpha 126", "type": "price", "func": self.calculate_alpha126},
            "alpha132": {"name": "Alpha 132", "type": "volume", "func": self.calculate_alpha132},
            "alpha135": {"name": "Alpha 135", "type": "momentum", "func": self.calculate_alpha135},
            "alpha153": {"name": "Alpha 153", "type": "momentum", "func": self.calculate_alpha153},
            "alpha164": {"name": "Alpha 164", "type": "momentum", "func": self.calculate_alpha164},
            "alpha173": {"name": "Alpha 173", "type": "trend", "func": self.calculate_alpha173},
            "alpha184": {"name": "Alpha 184", "type": "momentum", "func": self.calculate_alpha184},
        }

    def initialize_factors(self):
        """
        初始化因子库，将所有因子插入数据库
        """
        for factor_code, factor_info in self.factors.items():
            self._get_factor_meta(factor_code)
            self.db_manager.insert_factor(
                name=factor_code,
                description=factor_info["name"],
                type=factor_info["type"],
                calculation_method=str(factor_info["func"].__doc__),
            )
        logger.info(f"已初始化 {len(self.factors)} 个因子")

    def register_custom_factor(self, factor_code, factor_name, factor_type, calculation_func):
        """
        注册自定义因子

        Args:
            factor_code: 因子代码
            factor_name: 因子名称
            factor_type: 因子类型
            calculation_func: 计算函数

        Returns:
            bool: 注册是否成功
        """
        self._get_factor_meta(factor_code)

        if factor_code in self.factors:
            logger.warning(f"因子 {factor_code} 已存在")
            return False

        self.factors[factor_code] = {
            "name": factor_name,
            "type": factor_type,
            "func": calculation_func,
        }

        # 插入到数据库
        self.db_manager.insert_factor(
            name=factor_code,
            description=factor_name,
            type=factor_type,
            calculation_method=str(calculation_func.__doc__),
        )

        logger.info(f"已注册自定义因子: {factor_code} - {factor_name}")
        return True

    def create_factor_combination(
        self, combo_code, combo_name, factor_combination, weight_method="equal"
    ):
        self._get_factor_meta(combo_code)
        """
        创建因子组合
        
        Args:
            combo_code: 组合代码
            combo_name: 组合名称
            factor_combination: 因子组合列表，格式为 [(factor_code, weight), ...]
            weight_method: 权重方法，支持 'equal', 'custom'
            
        Returns:
            bool: 创建是否成功
        """
        # 验证所有因子是否存在
        for factor_code, _ in factor_combination:
            self._get_factor_meta(factor_code)
            if factor_code not in self.factors:
                logger.error(f"因子不存在: {factor_code}")
                return False

        # 计算权重
        if weight_method == "equal":
            weight = 1.0 / len(factor_combination)
            factor_combination = [(factor_code, weight) for factor_code, _ in factor_combination]

        # 注册因子组合
        self.factors[combo_code] = {
            "name": combo_name,
            "type": "combination",
            "func": self._calculate_factor_combination,
            "factors": factor_combination,
        }

        # 生成计算方法文档
        doc = f"因子组合: {combo_name}\n因子列表: {[factor_code for factor_code, _ in factor_combination]}\n权重: {[weight for _, weight in factor_combination]}"

        # 插入到数据库
        self.db_manager.insert_factor(
            name=combo_code, description=combo_name, type="combination", calculation_method=doc
        )

        logger.info(f"已创建因子组合: {combo_code} - {combo_name}")
        return True

    def _calculate_factor_combination(self, df, params=None):
        """
        计算因子组合
        """
        # 获取当前因子组合信息
        current_factor = None
        for code, info in self.factors.items():
            if info["func"] == self._calculate_factor_combination:
                current_factor = info
                break

        if not current_factor or "factors" not in current_factor:
            logger.error("未找到因子组合信息")
            return df

        # 计算所有子因子
        factor_values = {}
        for factor_code, weight in current_factor["factors"]:
            if factor_code not in self.factors:
                logger.error(f"因子不存在: {factor_code}")
                continue

            # 计算因子值
            factor_func = self.factors[factor_code]["func"]
            meta = self._get_factor_meta(factor_code)
            leakage = self._detect_future_leakage(factor_code, factor_func, df, params)
            if leakage.get("leakage"):
                raise RuntimeError(f"future leakage detected: {factor_code} - {leakage}")
            factor_df = factor_func(df.copy(), params)
            series = self._extract_factor_series(factor_code, factor_df)
            series = self._apply_availability_lag(series, meta.availability_lag)
            factor_values[factor_code] = series * weight

        # 合并因子值
        if factor_values:
            combo_name = list(self.factors.keys())[
                list(self.factors.values()).index(current_factor)
            ]
            meta = self._get_factor_meta(combo_name)
            combo_series = sum(factor_values.values())
            combo_series = self._apply_availability_lag(combo_series, meta.availability_lag)
            df[combo_name] = combo_series

        return df

    def set_data_source_manager(self, data_source_manager):
        """
        设置数据源管理器

        Args:
            data_source_manager: 数据源管理器实例
        """
        self.data_source_manager = data_source_manager
        logger.info("已设置数据源管理器")

    def _get_factor_meta(self, factor_code):
        try:
            return self.factor_registry.get_meta(factor_code)
        except UnregisteredFactorError as exc:
            logger.error(str(exc))
            raise

    def _extract_factor_series(self, factor_code, factor_values):
        if isinstance(factor_values, pd.Series):
            series = factor_values
        elif isinstance(factor_values, pd.DataFrame):
            if factor_code in factor_values.columns:
                series = factor_values[factor_code]
            elif len(factor_values.columns) == 1:
                series = factor_values.iloc[:, 0]
            else:
                raise ValueError(f"factor output missing column: {factor_code}")
        else:
            raise ValueError("unsupported factor output type")
        series.name = factor_code
        return series

    def _apply_availability_lag(self, series: pd.Series, availability_lag: int) -> pd.Series:
        if availability_lag < 0:
            raise ValueError("availability_lag must be >= 0")
        if availability_lag == 0:
            return series
        return series.shift(availability_lag)

    def _detect_future_leakage(
        self, factor_code: str, factor_func, df: pd.DataFrame, params=None
    ) -> dict:
        check_window = int(self.config.get("factor_leakage_check_window", 5))
        tolerance = float(self.config.get("factor_leakage_tolerance", 1e-9))
        if check_window <= 0 or len(df) <= check_window:
            return {"leakage": False, "reason": "insufficient_data"}

        full_values = (
            factor_func(df.copy(), params) if params is not None else factor_func(df.copy())
        )
        full_series = self._extract_factor_series(factor_code, full_values)

        truncated_df = df.iloc[:-check_window]
        trunc_values = (
            factor_func(truncated_df.copy(), params)
            if params is not None
            else factor_func(truncated_df.copy())
        )
        trunc_series = self._extract_factor_series(factor_code, trunc_values)

        common_index = trunc_series.index.intersection(full_series.index)
        if common_index.empty:
            return {"leakage": False, "reason": "no_overlap"}

        diff = (full_series.loc[common_index] - trunc_series.loc[common_index]).abs()
        max_diff = diff.max(skipna=True)
        if pd.isna(max_diff):
            return {"leakage": False, "reason": "no_valid_values"}
        if max_diff > tolerance:
            return {"leakage": True, "reason": "future_dependency", "max_diff": float(max_diff)}
        future_close = df["close"].shift(-1)
        aligned = pd.concat([full_series, future_close], axis=1).dropna()
        if not aligned.empty:
            mean_abs = float((aligned.iloc[:, 0] - aligned.iloc[:, 1]).abs().mean())
            if mean_abs <= tolerance:
                return {"leakage": True, "reason": "future_shift_match", "mean_abs_diff": mean_abs}
        return {"leakage": False, "reason": "ok", "max_diff": float(max_diff)}

    def calculate_factors(self, symbol, timeframe, factors=None, limit=365):
        """
        计算指定交易对和时间周期的因子值
        """
        # 获取交易数据
        end_time = datetime.now()
        start_time = end_time - pd.Timedelta(days=limit)
        df = self.db_manager.get_trading_data(symbol, timeframe, start_time, end_time)

        if df.empty:
            logger.warning(f"未找到交易数据: {symbol} {timeframe}")
            return

        # 选择要计算的因子
        factors_to_calculate = factors if factors else list(self.factors.keys())

        logger.info(f"开始计算因子: {symbol} {timeframe} - 因子数量: {len(factors_to_calculate)}")

        # 计算每个因子
        for factor_code in factors_to_calculate:
            if factor_code in self.factors:
                try:
                    logger.debug(f"正在计算因子: {factor_code}")
                    factor_func = self.factors[factor_code]["func"]
                    meta = self._get_factor_meta(factor_code)
                    leakage = self._detect_future_leakage(factor_code, factor_func, df)
                    if leakage.get("leakage"):
                        raise RuntimeError(f"future leakage detected: {factor_code} - {leakage}")

                    # 计算因子值
                    factor_values = factor_func(df)
                    factor_values = self._extract_factor_series(factor_code, factor_values)
                    factor_values = self._apply_availability_lag(
                        factor_values, meta.availability_lag
                    )

                    # 获取因子ID
                    factor_id = self.db_manager.get_factor_id(factor_code)
                    if not factor_id:
                        factor_id = self.db_manager.insert_factor(
                            name=factor_code,
                            description=self.factors[factor_code]["name"],
                            type=self.factors[factor_code]["type"],
                            calculation_method=str(factor_func.__doc__),
                        )

                    # 存储因子值
                    self._store_factor_values(symbol, timeframe, factor_id, factor_values)

                    logger.info(f"因子计算完成: {factor_code} - {symbol} {timeframe}")

                except Exception as e:
                    logger.error(f"计算因子失败: {factor_code} - {symbol} {timeframe}: {e}")
            else:
                logger.error(f"未知因子: {factor_code}")

    def _store_factor_values(self, symbol, timeframe, factor_id, factor_values):
        """
        存储因子值到数据库
        """
        for timestamp, value in factor_values.items():
            if not np.isnan(value):
                self.db_manager.insert_factor_value(timestamp, symbol, timeframe, factor_id, value)

    def get_factor_values(self, factor_code, symbol, timeframe, start_time, end_time):
        meta = self._get_factor_meta(factor_code)
        """
        获取指定因子值
        """
        # 获取因子ID
        factor_id = self.db_manager.get_factor_id(factor_code)
        if not factor_id:
            logger.error(f"未知因子: {factor_code}")
            return pd.DataFrame()

        # 获取因子值
        df = self.db_manager.get_factor_value(factor_id, symbol, timeframe, start_time, end_time)
        df.attrs["factor_meta"] = meta.__dict__
        return df

    # 价格类因子计算方法
    def calculate_ma(self, df, window=20):
        """
        计算移动平均线
        """
        return df["close"].rolling(window=window).mean()

    def calculate_ema(self, df, window=20):
        """
        计算指数移动平均线
        """
        return df["close"].ewm(span=window, adjust=False).mean()

    def calculate_bb(self, df, window=20, std=2):
        """
        计算布林带
        返回中间带、上带和下带
        """
        ma = df["close"].rolling(window=window).mean()
        std_dev = df["close"].rolling(window=window).std()
        upper_band = ma + (std_dev * std)
        lower_band = ma - (std_dev * std)

        # 计算布林带宽度和百分比
        bb_width = (upper_band - lower_band) / ma
        bb_pct = (df["close"] - lower_band) / (upper_band - lower_band)

        return bb_pct

    def calculate_rsi(self, df, window=14):
        """
        计算相对强弱指数
        """
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def calculate_macd(self, df, fast=12, slow=26, signal=9):
        """
        计算MACD指标
        返回MACD信号线
        """
        ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
        ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        macd_histogram = macd_line - signal_line

        return macd_histogram

    def calculate_stoch(self, df, k_window=14, d_window=3):
        """
        计算随机振荡器
        返回%D值
        """
        low_min = df["low"].rolling(window=k_window).min()
        high_max = df["high"].rolling(window=k_window).max()
        k_value = ((df["close"] - low_min) / (high_max - low_min)) * 100
        d_value = k_value.rolling(window=d_window).mean()

        return d_value

    def calculate_stoch_k(self, df, window=14):
        """
        计算随机振荡器K值
        """
        low_min = df["low"].rolling(window=window).min()
        high_max = df["high"].rolling(window=window).max()
        k_value = ((df["close"] - low_min) / (high_max - low_min)) * 100

        return k_value

    def calculate_std_dev(self, df, window=20):
        """
        计算标准差
        """
        return df["close"].rolling(window=window).std()

    def calculate_price_rate_of_change(self, df, window=12):
        """
        计算价格变化率
        """
        return ((df["close"] / df["close"].shift(window)) - 1) * 100

    def calculate_atr(self, df, window=14):
        """
        计算平均真实范围
        """
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=window).mean()

        return atr

    def calculate_cci(self, df, window=20):
        """
        计算商品通道指数
        """
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        sma = typical_price.rolling(window=window).mean()
        mad = typical_price.rolling(window=window).apply(lambda x: np.mean(np.abs(x - x.mean())))
        cci = (typical_price - sma) / (0.015 * mad)

        return cci

    def calculate_roc(self, df, window=14):
        """
        计算变化率
        """
        roc = ((df["close"] - df["close"].shift(window)) / df["close"].shift(window)) * 100

        return roc

    def calculate_adx(self, df, window=14):
        """
        计算平均方向指数
        """
        # 计算真实波动幅度
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        # 计算上涨和下跌幅度
        up_move = df["high"] - df["high"].shift()
        down_move = df["low"].shift() - df["low"]

        # 计算+DM和-DM
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)

        # 计算平滑的+DM、-DM和TR
        smoothed_plus_dm = plus_dm.rolling(window=window).mean()
        smoothed_minus_dm = minus_dm.rolling(window=window).mean()
        smoothed_tr = true_range.rolling(window=window).mean()

        # 计算+DI和-DI
        plus_di = (smoothed_plus_dm / smoothed_tr) * 100
        minus_di = (smoothed_minus_dm / smoothed_tr) * 100

        # 计算DX
        dx = (np.abs(plus_di - minus_di) / (plus_di + minus_di)) * 100

        # 计算ADX
        adx = dx.rolling(window=window).mean()

        return adx

    # 成交量类因子计算方法
    def calculate_vol_ma(self, df, window=20):
        """
        计算成交量移动平均线
        """
        return df["volume"].rolling(window=window).mean()

    def calculate_obv(self, df):
        """
        计算成交量净额
        """
        obv = pd.Series(0, index=df.index)
        for i in range(1, len(df)):
            if df["close"].iloc[i] > df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] + df["volume"].iloc[i]
            elif df["close"].iloc[i] < df["close"].iloc[i - 1]:
                obv.iloc[i] = obv.iloc[i - 1] - df["volume"].iloc[i]
            else:
                obv.iloc[i] = obv.iloc[i - 1]

        return obv

    def calculate_vwap(self, df):
        """
        计算成交量加权平均价格
        """
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        vwap = (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()

        return vwap

    def calculate_mfi(self, df, window=14):
        """
        计算资金流量指数
        """
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        money_flow = typical_price * df["volume"]

        positive_flow = money_flow.where(typical_price > typical_price.shift(), 0)
        negative_flow = money_flow.where(typical_price < typical_price.shift(), 0)

        positive_mf = positive_flow.rolling(window=window).sum()
        negative_mf = negative_flow.rolling(window=window).sum()

        mfi = 100 - (100 / (1 + (positive_mf / negative_mf)))

        return mfi

    def calculate_volume_rate_of_change(self, df, window=12):
        """
        计算成交量变化率
        """
        return ((df["volume"] / df["volume"].shift(window)) - 1) * 100

    def calculate_vwap_rate_of_change(self, df, window=12):
        """
        计算VWAP变化率
        """
        vwap = self.calculate_vwap(df)
        return ((vwap / vwap.shift(window)) - 1) * 100

    # 波动率类因子计算方法
    def calculate_volatility(self, df, window=20):
        """
        计算波动率
        """
        returns = df["close"].pct_change()
        volatility = returns.rolling(window=window).std() * np.sqrt(252)

        return volatility

    def calculate_return_volatility(self, df, window=20):
        """
        计算收益波动率
        """
        returns = df["close"].pct_change()
        volatility = returns.rolling(window=window).std()

        return volatility

    def calculate_historical_volatility(self, df, window=30):
        """
        计算历史波动率
        """
        returns = df["close"].pct_change()
        # 年化波动率，假设每年252个交易日
        historical_vol = returns.rolling(window=window).std() * np.sqrt(252)

        return historical_vol

    def calculate_realized_volatility(self, df, window=20):
        """
        计算已实现波动率
        """
        returns = df["close"].pct_change()
        realized_vol = returns.rolling(window=window).std()

        return realized_vol

    # 动量类因子计算方法
    def calculate_momentum(self, df, window=14):
        """
        计算动量
        """
        momentum = df["close"] - df["close"].shift(window)

        return momentum

    def calculate_williams_r(self, df, window=14):
        """
        计算威廉姆斯%R
        """
        highest_high = df["high"].rolling(window=window).max()
        lowest_low = df["low"].rolling(window=window).min()
        williams_r = ((highest_high - df["close"]) / (highest_high - lowest_low)) * -100

        return williams_r

    def calculate_tsi(self, df, r=25, s=13):
        """
        计算真实强度指数
        """
        pc = df["close"].diff()
        m = pc.ewm(span=r, adjust=False).mean()
        dm = np.abs(pc).ewm(span=r, adjust=False).mean()
        m = m.ewm(span=s, adjust=False).mean()
        dm = dm.ewm(span=s, adjust=False).mean()
        tsi = (m / dm) * 100

        return tsi

    def calculate_rsi_rate_of_change(self, df, rsi_window=14, roc_window=12):
        """
        计算RSI变化率
        """
        rsi = self.calculate_rsi(df, window=rsi_window)
        return rsi.diff(periods=roc_window)

    def calculate_roc_momentum(self, df, roc_window=12, momentum_window=14):
        """
        计算ROC动量
        """
        roc = self.calculate_roc(df, window=roc_window)
        return roc.rolling(window=momentum_window).mean()

    # 趋势类因子计算方法
    def calculate_dmi(self, df, window=14):
        """
        计算方向运动指数
        返回+DI和-DI的差值
        """
        # 计算上涨和下跌幅度
        up_move = df["high"] - df["high"].shift()
        down_move = df["low"].shift() - df["low"]

        # 计算+DM和-DM
        plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0)
        minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0)

        # 计算真实波动幅度
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        # 计算+DI和-DI
        smoothed_true_range = true_range.rolling(window=window).mean()
        smoothed_plus_dm = plus_dm.rolling(window=window).mean()
        smoothed_minus_dm = minus_dm.rolling(window=window).mean()

        plus_di = (smoothed_plus_dm / smoothed_true_range) * 100
        minus_di = (smoothed_minus_dm / smoothed_true_range) * 100

        return plus_di - minus_di

    def calculate_parabolic_sar(self, df, af=0.02, af_max=0.2):
        """
        计算抛物线转向指标
        """
        sar = df["close"].copy()
        ep = df["close"].copy()
        trend = pd.Series(1, index=df.index)
        af = pd.Series(af, index=df.index)

        for i in range(1, len(df)):
            if trend.iloc[i - 1] == 1:
                sar.iloc[i] = sar.iloc[i - 1] + af.iloc[i - 1] * (ep.iloc[i - 1] - sar.iloc[i - 1])

                if df["low"].iloc[i] < sar.iloc[i]:
                    trend.iloc[i] = -1
                    sar.iloc[i] = ep.iloc[i - 1]
                    ep.iloc[i] = df["low"].iloc[i]
                    af.iloc[i] = af.iloc[0]
                else:
                    trend.iloc[i] = 1
                    if df["high"].iloc[i] > ep.iloc[i - 1]:
                        ep.iloc[i] = df["high"].iloc[i]
                        af.iloc[i] = min(af.iloc[i - 1] + af.iloc[0], af_max)
                    else:
                        ep.iloc[i] = ep.iloc[i - 1]
                        af.iloc[i] = af.iloc[i - 1]
            else:
                sar.iloc[i] = sar.iloc[i - 1] + af.iloc[i - 1] * (ep.iloc[i - 1] - sar.iloc[i - 1])

                if df["high"].iloc[i] > sar.iloc[i]:
                    trend.iloc[i] = 1
                    sar.iloc[i] = ep.iloc[i - 1]
                    ep.iloc[i] = df["high"].iloc[i]
                    af.iloc[i] = af.iloc[0]
                else:
                    trend.iloc[i] = -1
                    if df["low"].iloc[i] < ep.iloc[i - 1]:
                        ep.iloc[i] = df["low"].iloc[i]
                        af.iloc[i] = min(af.iloc[i - 1] + af.iloc[0], af_max)
                    else:
                        ep.iloc[i] = ep.iloc[i - 1]
                        af.iloc[i] = af.iloc[i - 1]

        return sar

    def calculate_ichimoku(self, df):
        """
        计算一目均衡表
        返回云区厚度
        """
        # 转换线 (Tenkan-sen)
        tenkan_sen = (df["high"].rolling(window=9).max() + df["low"].rolling(window=9).min()) / 2

        # 基准线 (Kijun-sen)
        kijun_sen = (df["high"].rolling(window=26).max() + df["low"].rolling(window=26).min()) / 2

        # 延迟线 (Chikou Span)
        chikou_span = df["close"].shift(-26)

        # 先行上限1 (Senkou Span A)
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)

        # 先行上限2 (Senkou Span B)
        senkou_span_b = (
            (df["high"].rolling(window=52).max() + df["low"].rolling(window=52).min()) / 2
        ).shift(26)

        # 云区厚度
        cloud_thickness = np.abs(senkou_span_a - senkou_span_b)

        return cloud_thickness

    def calculate_trend_slope(self, df, window=20):
        """
        计算趋势斜率
        """
        import numpy as np

        def get_slope(x):
            if len(x) < 2:
                return 0
            idx = np.arange(len(x))
            slope, _ = np.polyfit(idx, x, 1)
            return slope

        return df["close"].rolling(window=window).apply(get_slope)

    def calculate_ma_crossover(self, df, fast_window=12, slow_window=26):
        """
        计算均线交叉信号
        """
        fast_ma = df["close"].rolling(window=fast_window).mean()
        slow_ma = df["close"].rolling(window=slow_window).mean()

        # 金叉为正，死叉为负
        crossover = fast_ma - slow_ma

        return crossover

    def calculate_trend_strength(self, df, window=20):
        """
        计算趋势强度
        """
        ma = df["close"].rolling(window=window).mean()

        # 计算价格与均线的相对距离，反映趋势强度
        trend_strength = (df["close"] - ma) / ma * 100

        return trend_strength

    def calculate_all_factors(self, symbol, timeframe, limit=365):
        """
        计算所有因子
        """
        self.calculate_factors(symbol, timeframe, limit=limit)

    def get_factor_info(self, factor_code):
        """
        获取因子信息
        """
        if factor_code in self.factors:
            return self.factors[factor_code]
        return None

    def list_factors(self):
        """
        列出所有已定义的因子
        """
        return list(self.factors.keys())

    def list_factors_by_type(self, factor_type):
        """
        按类型列出因子
        """
        return [code for code, info in self.factors.items() if info["type"] == factor_type]

    def visualize_factor_distribution(
        self, factor_code, symbol, timeframe, start_time, end_time, output_path=None
    ):
        """
        可视化因子值分布

        Args:
            factor_code: 因子代码
            symbol: 交易对
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            output_path: 输出HTML路径，默认None

        Returns:
            Plotly图表对象
        """
        logger.info(f"可视化因子分布: {factor_code} {symbol} {timeframe}")

        # 获取因子值
        factor_df = self.get_factor_values(factor_code, symbol, timeframe, start_time, end_time)
        if factor_df.empty:
            logger.error(f"未找到因子值: {factor_code}")
            return None

        # 获取因子类型和名称
        factor_info = self.factors.get(factor_code, {})
        factor_name = factor_info.get("name", factor_code)
        factor_type = factor_info.get("type", "price")

        # 设置因子类型对应的颜色主题
        color_theme = {
            "price": "#636EFA",  # 蓝色 - 价格类因子
            "volume": "#EF553B",  # 红色 - 成交量类因子
            "volatility": "#00CC96",  # 绿色 - 波动率类因子
            "momentum": "#AB63FA",  # 紫色 - 动量类因子
            "trend": "#FFA15A",  # 橙色 - 趋势类因子
            "on_chain": "#FF6692",  # 粉色 - 链上因子
            "crypto_exclusive": "#B6E880",  # 浅绿色 - 加密专属因子
            "sentiment": "#FF97FF",  # 浅紫色 - 情绪因子
            "alternative": "#19D3F3",  # 青色 - 另类数据因子
            "ai_ml": "#FF6B6B",  # 珊瑚色 - AI/ML因子
        }

        # 生成分布图表
        fig = px.histogram(
            factor_df,
            x="value",
            nbinsx=50,
            title=f"{factor_name} ({factor_code}) 因子值分布 ({symbol} {timeframe})",
            color_discrete_sequence=[color_theme.get(factor_type, "#636EFA")],
            hover_data=["timestamp"],
        )

        # 添加统计信息
        mean_val = factor_df["value"].mean()
        median_val = factor_df["value"].median()
        std_val = factor_df["value"].std()
        min_val = factor_df["value"].min()
        max_val = factor_df["value"].max()

        # 添加统计参考线
        fig.add_vline(
            x=mean_val, line_dash="dash", line_color="red", annotation_text=f"均值: {mean_val:.4f}"
        )
        fig.add_vline(
            x=median_val,
            line_dash="dash",
            line_color="green",
            annotation_text=f"中位数: {median_val:.4f}",
        )

        # 更新布局
        fig.update_layout(
            xaxis_title="因子值",
            yaxis_title="频数",
            template="plotly_white",
            title_x=0.5,
            title_font=dict(size=16),
        )

        # 保存图表
        if output_path:
            fig.write_html(output_path)
            logger.info(f"因子分布图表已保存到: {output_path}")

        return fig

    def visualize_factor_correlation(
        self, factor_codes, symbol, timeframe, start_time, end_time, output_path=None
    ):
        """
        可视化因子相关性矩阵

        Args:
            factor_codes: 因子代码列表
            symbol: 交易对
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            output_path: 输出HTML路径，默认None

        Returns:
            Plotly图表对象
        """
        logger.info(f"可视化因子相关性: {symbol} {timeframe}")

        # 获取所有因子值
        factor_data = {}
        valid_factor_codes = []

        for factor_code in factor_codes:
            factor_df = self.get_factor_values(factor_code, symbol, timeframe, start_time, end_time)
            if not factor_df.empty:
                factor_data[factor_code] = factor_df["value"]
                valid_factor_codes.append(factor_code)

        if not factor_data:
            logger.error("未找到因子值数据")
            return None

        # 创建因子数据框
        factor_df = pd.DataFrame(factor_data)

        # 计算相关性矩阵
        corr_matrix = factor_df.corr()

        # 获取因子名称映射
        factor_name_map = {
            code: self.factors.get(code, {}).get("name", code) for code in valid_factor_codes
        }

        # 重命名相关性矩阵的行和列
        corr_matrix = corr_matrix.rename(index=factor_name_map, columns=factor_name_map)

        # 生成相关性热力图
        fig = px.imshow(
            corr_matrix,
            text_auto=".2f",
            aspect="auto",
            title=f"因子相关性矩阵 ({symbol} {timeframe})",
            color_continuous_scale="RdBu_r",
            zmin=-1,
            zmax=1,
            labels=dict(color="相关性系数"),
        )

        # 更新布局
        fig.update_layout(
            template="plotly_white",
            title_x=0.5,
            title_font=dict(size=16),
            xaxis_title="因子",
            yaxis_title="因子",
            xaxis_tickangle=45,
            xaxis_nticks=len(valid_factor_codes),
            yaxis_nticks=len(valid_factor_codes),
            coloraxis_colorbar=dict(
                title="相关性", thicknessmode="pixels", thickness=20, lenmode="pixels", len=300
            ),
        )

        # 保存图表
        if output_path:
            fig.write_html(output_path)
            logger.info(f"因子相关性图表已保存到: {output_path}")

        return fig

    def visualize_factor_performance(
        self, factor_codes, symbols, timeframes, start_time, end_time, output_path=None
    ):
        """
        可视化因子在不同交易对和时间周期上的表现

        Args:
            factor_codes: 因子代码列表
            symbols: 交易对列表
            timeframes: 时间周期列表
            start_time: 开始时间
            end_time: 结束时间
            output_path: 输出HTML路径，默认None

        Returns:
            Plotly图表对象
        """
        logger.info(f"可视化因子表现: {symbols} {timeframes}")

        # 准备数据
        performance_data = []

        for symbol in symbols:
            for timeframe in timeframes:
                for factor_code in factor_codes:
                    factor_df = self.get_factor_values(
                        factor_code, symbol, timeframe, start_time, end_time
                    )
                    if not factor_df.empty:
                        # 计算因子基本统计指标
                        stats = {
                            "factor_code": factor_code,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "mean": factor_df["value"].mean(),
                            "std": factor_df["value"].std(),
                            "min": factor_df["value"].min(),
                            "max": factor_df["value"].max(),
                            "count": len(factor_df),
                        }
                        performance_data.append(stats)

        if not performance_data:
            logger.error("未找到因子表现数据")
            return None

        # 创建数据框
        df = pd.DataFrame(performance_data)

        # 生成热力图
        fig = px.density_heatmap(
            df,
            x="timeframe",
            y="symbol",
            z="mean",
            facet_col="factor_code",
            title="因子表现热力图 (平均值)",
            color_continuous_scale="Viridis",
            labels={"mean": "因子平均值"},
        )
        fig.update_layout(template="plotly_white")

        # 保存图表
        if output_path:
            fig.write_html(output_path)
            logger.info(f"因子表现图表已保存到: {output_path}")

        return fig

    def generate_factor_visualization_report(
        self,
        factor_codes,
        symbols,
        timeframes,
        start_time,
        end_time,
        output_path="factor_visualization_report.html",
    ):
        """
        生成完整的因子可视化报告

        Args:
            factor_codes: 因子代码列表
            symbols: 交易对列表
            timeframes: 时间周期列表
            start_time: 开始时间
            end_time: 结束时间
            output_path: 输出HTML路径

        Returns:
            输出文件路径
        """
        logger.info(f"生成因子可视化报告: {output_path}")

        # 创建子图
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                f"因子分布 ({factor_codes[0]} {symbols[0]} {timeframes[0]})",
                f"因子相关性 ({symbols[0]} {timeframes[0]})",
                "因子表现热力图",
                "因子统计摘要",
            ),
            vertical_spacing=0.15,
            horizontal_spacing=0.1,
        )

        # 1. 添加因子分布图表
        dist_fig = self.visualize_factor_distribution(
            factor_codes[0], symbols[0], timeframes[0], start_time, end_time
        )
        if dist_fig:
            for trace in dist_fig.data:
                fig.add_trace(trace, row=1, col=1)
            fig.update_xaxes(title_text="因子值", row=1, col=1)
            fig.update_yaxes(title_text="频数", row=1, col=1)

        # 2. 添加因子相关性图表
        corr_fig = self.visualize_factor_correlation(
            factor_codes, symbols[0], timeframes[0], start_time, end_time
        )
        if corr_fig:
            # 相关性热力图需要特殊处理
            corr_data = px.imshow(
                corr_fig.data[0].z,
                text_auto=True,
                aspect="auto",
                color_continuous_scale="RdBu_r",
                zmin=-1,
                zmax=1,
            )
            for trace in corr_data.data:
                fig.add_trace(trace, row=1, col=2)

        # 3. 添加因子表现热力图
        perf_fig = self.visualize_factor_performance(
            factor_codes, symbols, timeframes, start_time, end_time
        )
        if perf_fig:
            # 热力图需要特殊处理
            for trace in perf_fig.data:
                fig.add_trace(trace, row=2, col=1)
            fig.update_xaxes(title_text="时间周期", row=2, col=1)
            fig.update_yaxes(title_text="交易对", row=2, col=1)

        # 4. 添加因子统计摘要
        # 准备统计数据
        stats_data = []
        for symbol in symbols:
            for timeframe in timeframes:
                for factor_code in factor_codes:
                    factor_df = self.get_factor_values(
                        factor_code, symbol, timeframe, start_time, end_time
                    )
                    if not factor_df.empty:
                        stats = {
                            "Factor": factor_code,
                            "Symbol": symbol,
                            "Timeframe": timeframe,
                            "Mean": factor_df["value"].mean(),
                            "Std": factor_df["value"].std(),
                            "Min": factor_df["value"].min(),
                            "Max": factor_df["value"].max(),
                        }
                        stats_data.append(stats)

        if stats_data:
            stats_df = pd.DataFrame(stats_data)
            # 使用表格展示统计摘要
            table_trace = go.Table(
                header=dict(
                    values=list(stats_df.columns), fill_color="paleturquoise", align="left"
                ),
                cells=dict(
                    values=[stats_df[col] for col in stats_df.columns],
                    fill_color="lavender",
                    align="left",
                ),
            )
            fig.add_trace(table_trace, row=2, col=2)

        # 更新布局
        fig.update_layout(
            height=1000, width=1200, title_text="因子可视化报告", template="plotly_white"
        )

        # 保存报告
        fig.write_html(output_path)
        logger.info(f"因子可视化报告已保存到: {output_path}")

        return output_path

    # 前沿因子计算方法

    # 链上因子 (On-Chain)
    def calculate_mvrv(self, df, params=None):
        """
        计算市场价值与实现价值比率 (Market Value to Realized Value)
        公式: MVRV = 市场总值 / 实现总值
        """
        params = params or {"window": 30}
        # 简化实现：使用价格趋势模拟
        df["mvrv"] = (df["close"] / df["close"].rolling(window=params["window"]).mean()) * 100
        return df

    def calculate_nupl(self, df, params=None):
        """
        计算净未实现盈亏 (Net Unrealized Profit/Loss)
        公式: NUPL = (市场总值 - 实现总值) / 市场总值
        """
        params = params or {"window": 30}
        # 简化实现：基于价格变化率
        df["price_change"] = df["close"].pct_change()
        df["nupl"] = df["price_change"].rolling(window=params["window"]).mean()
        return df

    def calculate_sopr(self, df, params=None):
        """
        计算已花费输出利润比率 (Spent Output Profit Ratio)
        公式: SOPR = 已花费输出的实现价值 / 创建时的价值
        """
        params = params or {"window": 14}
        # 简化实现：使用价格动量模拟
        df["sopr"] = df["close"] / df["close"].shift(params["window"])
        return df

    def calculate_exchange_net_flow(self, df, params=None):
        """
        计算交易所净流量
        公式: 流入交易所的资金 - 流出交易所的资金
        """
        params = params or {"window": 7}
        # 简化实现：使用成交量变化模拟
        df["volume_change"] = df["volume"].pct_change()
        df["exchange_net_flow"] = df["volume_change"].rolling(window=params["window"]).sum()
        return df

    def calculate_miner_balance(self, df, params=None):
        """
        计算矿工余额
        """
        params = params or {"window": 30}
        # 简化实现：使用价格趋势模拟矿工行为
        df["miner_balance"] = (
            df["close"].rolling(window=params["window"]).apply(lambda x: x[-1] / x[0] - 1) * 100
        )
        return df

    def calculate_active_addresses(self, df, params=None):
        """
        计算活跃地址数量
        """
        params = params or {"window": 7}
        # 简化实现：使用成交量活跃度模拟
        df["active_addresses"] = (
            df["volume"].rolling(window=params["window"]).mean() / df["volume"].mean()
        )
        return df

    def calculate_realized_cap(self, df, params=None):
        """
        计算实现市值 (Realized Cap)
        """
        params = params or {"window": 365}
        # 简化实现：基于累计价格
        df["realized_cap"] = df["close"].cumsum() / len(df)
        return df

    # 加密专属因子 (Crypto Exclusive)
    def calculate_funding_rate(self, df, params=None):
        """
        计算资金费率
        """
        params = params or {"window": 8}
        # 简化实现：使用价格波动模拟
        df["funding_rate"] = df["close"].pct_change().rolling(window=params["window"]).mean() * 100
        return df

    def calculate_open_interest(self, df, params=None):
        """
        计算未平仓量
        """
        params = params or {"window": 24}
        # 简化实现：使用成交量趋势模拟
        df["open_interest"] = df["volume"].rolling(window=params["window"]).sum()
        return df

    def calculate_liquidations(self, df, params=None):
        """
        计算爆仓数据
        """
        params = params or {"threshold": 0.05}
        # 简化实现：检测大幅价格波动
        df["liquidations"] = (
            df["close"].pct_change().apply(lambda x: abs(x) > params["threshold"]).astype(int)
        )
        return df

    def calculate_long_short_ratio(self, df, params=None):
        """
        计算多空比率
        """
        params = params or {"window": 14}
        # 简化实现：基于价格动量
        df["long_short_ratio"] = (
            1 + df["close"].pct_change().rolling(window=params["window"]).mean()
        ) * 100
        return df

    def calculate_stablecoin_premium(self, df, params=None):
        """
        计算稳定币溢价
        """
        params = params or {"window": 7}
        # 简化实现：使用波动率模拟
        df["stablecoin_premium"] = (
            df["close"].rolling(window=params["window"]).std() / df["close"].mean() * 100
        )
        return df

    # 情绪因子 (Sentiment)
    def calculate_social_sentiment(self, df, params=None):
        """
        计算社交情绪
        """
        params = params or {"window": 7}
        # 简化实现：基于价格变化模拟情绪
        df["social_sentiment"] = (
            df["close"]
            .pct_change()
            .rolling(window=params["window"])
            .apply(lambda x: (x - x.min()) / (x.max() - x.min()) * 100)
            if x.max() != x.min()
            else 50
        )
        return df

    def calculate_twitter_mentions(self, df, params=None):
        """
        计算Twitter提及量
        """
        params = params or {"window": 30}
        # 简化实现：使用成交量变化模拟
        df["twitter_mentions"] = df["volume"].pct_change().rolling(window=params["window"]).sum()
        return df

    def calculate_reddit_activity(self, df, params=None):
        """
        计算Reddit活跃度
        """
        params = params or {"window": 7}
        # 简化实现：使用价格波动模拟
        df["reddit_activity"] = (
            df["close"].pct_change().rolling(window=params["window"]).std() * 100
        )
        return df

    def calculate_news_sentiment(self, df, params=None):
        """
        计算新闻情绪
        """
        params = params or {"window": 3}
        # 简化实现：基于价格变化率
        df["news_sentiment"] = (
            df["close"].pct_change().rolling(window=params["window"]).mean() * 100
        )
        return df

    # 另类数据因子 (Alternative Data)
    def calculate_dev_activity(self, df, params=None):
        """
        计算开发活跃度
        """
        params = params or {"window": 30}
        # 简化实现：使用价格趋势模拟
        df["dev_activity"] = (
            df["close"].rolling(window=params["window"]).apply(lambda x: x[-1] / x[0] - 1) * 100
        )
        return df

    def calculate_github_commits(self, df, params=None):
        """
        计算GitHub提交量
        """
        params = params or {"window": 14}
        # 简化实现：使用波动率模拟
        df["github_commits"] = df["close"].rolling(window=params["window"]).std()
        return df

    def calculate_community_growth(self, df, params=None):
        """
        计算社区增长
        """
        params = params or {"window": 30}
        # 简化实现：使用成交量增长模拟
        df["community_growth"] = (
            df["volume"].pct_change().rolling(window=params["window"]).mean() * 100
        )
        return df

    def calculate_alt_rank(self, df, params=None):
        """
        计算AltRank (市值+社交热度复合排名)
        """
        params = params or {"window": 30}
        # 简化实现：基于价格和成交量的复合指标
        df["alt_rank"] = (
            df["close"].rolling(window=params["window"]).mean()
            * df["volume"].rolling(window=params["window"]).mean()
        ) / 1e9
        return df

    # AI/ML因子 (AI/ML)
    def calculate_ai_momentum(self, df, params=None):
        """
        计算AI动量因子
        使用LSTM神经网络预测价格动量
        """
        params = params or {"window": 20, "n_steps": 10}
        window = params["window"]
        n_steps = params["n_steps"]

        try:
            # 导入必要的深度学习库
            import torch
            import torch.nn as nn

            # 准备数据
            def create_sequences(data, seq_length):
                xs, ys = [], []
                for i in range(len(data) - seq_length):
                    x = data[i : i + seq_length]
                    y = data[i + seq_length]
                    xs.append(x)
                    ys.append(y)
                return np.array(xs), np.array(ys)

            # 计算价格变化率
            returns = df["close"].pct_change().dropna().values

            if len(returns) < n_steps + 1:
                df["ai_momentum"] = 0
                return df

            # 创建序列数据
            X, y = create_sequences(returns, n_steps)
            X = torch.FloatTensor(X).unsqueeze(2)
            y = torch.FloatTensor(y)

            # 定义LSTM模型
            class LSTMModel(nn.Module):
                def __init__(self, input_size=1, hidden_size=64, num_layers=2, output_size=1):
                    super(LSTMModel, self).__init__()
                    self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
                    self.fc = nn.Linear(hidden_size, output_size)

                def forward(self, x):
                    _, (hidden, _) = self.lstm(x)
                    out = self.fc(hidden[-1])
                    return out

            # 初始化和训练模型
            model = LSTMModel()
            criterion = nn.MSELoss()
            optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

            # 简单训练（仅用于演示，实际应用需要更复杂的训练逻辑）
            for epoch in range(10):
                outputs = model(X)
                loss = criterion(outputs, y.view(-1, 1))
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            # 预测动量
            with torch.no_grad():
                predictions = model(X)

            # 将预测结果添加到数据框
            df["ai_momentum"] = 0
            if len(predictions) > 0:
                df.iloc[n_steps + 1 :, df.columns.get_loc("ai_momentum")] = (
                    predictions.numpy().flatten()
                )

        except Exception as e:
            logger.error(f"AI动量因子计算失败: {e}")
            # 回退到简化实现
            df["ai_momentum"] = (
                df["close"]
                .rolling(window=window)
                .apply(lambda x: (x[-1] - x.mean()) / x.std() if x.std() != 0 else 0)
            )

        return df

    def calculate_ai_volatility(self, df, params=None):
        """
        计算AI波动率因子
        使用GARCH模型预测波动率
        """
        params = params or {"window": 10}
        window = params["window"]

        try:
            # 计算收益
            returns = df["close"].pct_change().dropna()

            if len(returns) < window:
                df["ai_volatility"] = 0
                return df

            # 使用历史波动率的深度学习增强版本
            # 结合滚动标准差和价格变化的非线性特征
            volatility = returns.rolling(window=window).std()

            # 添加非线性特征
            df["price_change"] = df["close"].pct_change()
            df["abs_price_change"] = df["price_change"].abs()
            df["squared_price_change"] = df["price_change"] ** 2

            # 计算非线性组合的波动率
            df["ai_volatility"] = volatility.rolling(window=window).apply(
                lambda x: np.sqrt(np.mean(x**2) + np.mean(df.loc[x.index, "squared_price_change"]))
            )

            # 清理临时列
            df.drop(
                ["price_change", "abs_price_change", "squared_price_change"], axis=1, inplace=True
            )

        except Exception as e:
            logger.error(f"AI波动率因子计算失败: {e}")
            # 回退到简化实现
            df["ai_volatility"] = (
                df["close"]
                .pct_change()
                .rolling(window=window)
                .apply(lambda x: x.quantile(0.95) - x.quantile(0.05))
            )

        return df

    def calculate_gnn_topology(self, df, params=None):
        """
        计算图神经网络拓扑特征
        基于价格相关性网络的拓扑结构
        """
        params = params or {"window": 15}
        window = params["window"]

        try:
            # 构建价格相关性网络
            # 计算不同滞后期的价格相关性
            correlations = []
            for lag in range(1, window + 1):
                corr = df["close"].corr(df["close"].shift(lag))
                correlations.append(corr)

            # 计算网络拓扑特征：聚类系数、平均路径长度等
            # 简化实现：使用相关性的统计特征作为拓扑特征
            df["gnn_topology"] = np.nan

            # 计算滚动相关性特征
            for i in range(window, len(df)):
                # 获取窗口数据
                window_data = df.iloc[i - window : i]

                # 计算窗口内的价格相关性矩阵
                corr_matrix = window_data[["open", "high", "low", "close", "volume"]].corr()

                # 提取拓扑特征：平均相关性、最大相关性、最小相关性、相关性标准差
                corr_vals = corr_matrix.values[np.triu_indices_from(corr_matrix, k=1)]
                avg_corr = np.mean(corr_vals)
                max_corr = np.max(corr_vals)
                min_corr = np.min(corr_vals)
                std_corr = np.std(corr_vals)

                # 组合成拓扑特征
                topology_feature = avg_corr * 0.4 + max_corr * 0.3 + min_corr * 0.1 + std_corr * 0.2
                df.iloc[i, df.columns.get_loc("gnn_topology")] = topology_feature

        except Exception as e:
            logger.error(f"GNN拓扑特征计算失败: {e}")
            # 回退到简化实现
            df["gnn_topology"] = (
                df["close"]
                .rolling(window=window)
                .apply(lambda x: x.corr(x.shift(1)) if len(x) > 1 else 0)
            )

        return df

    def calculate_auto_factor(self, df, params=None):
        """
        计算自动生成因子
        使用遗传算法或强化学习自动生成因子
        """
        params = params or {"window": 21}
        window = params["window"]

        try:
            # 从rl_factor_optimizer导入RLFactorOptimizer
            from rl_factor_optimizer import RLFactorOptimizer

            # 准备因子数据
            factor_codes = ["ma", "rsi", "macd", "bb", "atr"]
            factor_data = []

            # 计算基础因子
            for factor_code in factor_codes:
                self._get_factor_meta(factor_code)
                if factor_code in self.factors:
                    factor_func = self.factors[factor_code]["func"]
                    leakage = self._detect_future_leakage(factor_code, factor_func, df)
                    if leakage.get("leakage"):
                        raise RuntimeError(f"future leakage detected: {factor_code} - {leakage}")
                    result = factor_func(df.copy())
                    result = self._extract_factor_series(factor_code, result)
                    meta = self._get_factor_meta(factor_code)
                    result = self._apply_availability_lag(result, meta.availability_lag)
                    factor_data.append(result.values)

            if not factor_data:
                # 回退到简化实现
                df["auto_factor"] = 0
                return df

            # 转置因子数据，使其形状为 (n_samples, n_factors)
            factor_data = np.array(factor_data).T

            # 计算收益数据
            returns = df["close"].pct_change().dropna().values

            # 确保因子数据和收益数据长度匹配
            min_len = min(len(factor_data), len(returns))
            factor_data = factor_data[:min_len]
            returns = returns[:min_len]

            if len(factor_data) < 2:
                df["auto_factor"] = 0
                return df

            # 使用强化学习优化因子组合
            rl_optimizer = RLFactorOptimizer(factor_codes)
            optimal_weights = rl_optimizer.optimize_factor_combination(factor_data, returns)

            # 计算自动生成因子
            auto_factor = np.dot(factor_data, optimal_weights)

            # 将结果添加到数据框
            df["auto_factor"] = 0
            if len(auto_factor) > 0:
                # 确保索引匹配
                df.iloc[-len(auto_factor) :, df.columns.get_loc("auto_factor")] = auto_factor

        except Exception as e:
            logger.error(f"自动因子计算失败: {e}")
            # 回退到简化实现，确保参数正确
            try:
                # 计算简单移动平均线
                df["ma"] = df["close"].rolling(window=window).mean()

                # 计算RSI（相对强弱指数）
                rsi_result = self.calculate_rsi(df.copy(), {"window": 14})
                if isinstance(rsi_result, pd.DataFrame) and "rsi" in rsi_result.columns:
                    df["rsi"] = rsi_result["rsi"]
                elif isinstance(rsi_result, pd.Series):
                    df["rsi"] = rsi_result
                else:
                    df["rsi"] = 50  # 中性RSI值

                # 计算MACD（平滑异同移动平均线）
                macd_result = self.calculate_macd(df.copy())
                if isinstance(macd_result, pd.DataFrame) and "macd" in macd_result.columns:
                    df["macd"] = macd_result["macd"]
                elif isinstance(macd_result, pd.Series):
                    df["macd"] = macd_result
                else:
                    df["macd"] = 0

                # 计算自动生成因子
                df["auto_factor"] = (df["ma"] / df["close"] + df["rsi"] / 100 + df["macd"]) / 3
            except Exception as fallback_e:
                logger.error(f"自动因子回退实现失败: {fallback_e}")
                df["auto_factor"] = 0

        return df

    # 因子生成方法 - 导航文档中提到的因子生成器实现
    def calculate_auto_factor_generator(self, df, params=None):
        """
        使用AutoFactorGenerator生成自动因子
        
        工作原理：
        1. 基础变量定义：从OHLCV等基础特征矩阵中选择可用变量
        2. 算子定义：11个一元算子，6个二元算子
        3. 因子表达式生成：支持一元和二元表达式，包括浅层和深层嵌套
        4. 因子评估：计算IC（信息系数）
        5. 因子筛选：按IC绝对值排序，过滤低IC因子，去除高相关性因子
        
        参数：
        - n_factors: 生成因子数量
        - min_abs_ic: 最小IC绝对值
        - max_corr: 最大因子相关性
        """
        try:
            from .auto_factor_generator import AutoFactorGenerator
            
            params = params or {}
            n_factors = params.get("n_factors", 100)
            
            # 生成未来收益率作为标签（用于IC计算）
            returns = df["close"].pct_change().shift(-1)
            
            # 初始化自动因子生成器
            generator = AutoFactorGenerator(base_features=df)
            
            # 生成因子
            factors = generator.generate_factors(n_factors=n_factors, labels=returns)
            
            # 简单返回第一个因子作为示例
            if factors:
                # 计算第一个因子的值
                factor_expr = factors[0]
                factor_values = eval(factor_expr, {"data": df, "np": np, "pd": pd})
                # 如果是Series直接返回，否则返回DataFrame
                if isinstance(factor_values, pd.Series):
                    return factor_values
                else:
                    # 将计算结果添加到DataFrame并返回
                    df["auto_factor_generator"] = factor_values
                    return df
            else:
                return df["close"].pct_change()
        except Exception as e:
            logger.error(f"AutoFactorGenerator 调用失败: {e}")
            return df["close"].pct_change()

    def calculate_layered_factor_generator(self, df, params=None):
        """
        使用5层搭积木式因子生成器生成因子
        
        5层递进式生成流程：
        1. 第1层：基础因子（约200个 → Top 50）
        2. 第2层：时间序列因子（约1000个 → Top 50）
        3. 第3层：截面因子（约500个 → Top 50）
        4. 第4层：非线性因子（约500个 → Top 50）
        5. 第5层：因子组合因子（约250个 → Top 50）
        
        参数：
        - output_path: 因子输出路径
        """
        try:
            from .factor_generator import FactorGenerator
            
            params = params or {}
            output_path = params.get("output_path")
            
            # 初始化因子生成器
            generator = FactorGenerator()
            
            # 生成5层因子
            factors = generator.generate_factors(test_data=df, output_path=output_path)
            
            # 简单返回第一个因子作为示例
            if factors:
                # 计算第一个因子的值
                factor_expr = factors[0]
                factor_values = eval(factor_expr, {"data": df, "np": np, "pd": pd})
                # 如果是Series直接返回，否则返回DataFrame
                if isinstance(factor_values, pd.Series):
                    return factor_values
                else:
                    # 将计算结果添加到DataFrame并返回
                    df["layered_factor_generator"] = factor_values
                    return df
            else:
                return df["close"].pct_change()
        except Exception as e:
            logger.error(f"FactorGenerator 调用失败: {e}")
            return df["close"].pct_change()

    def calculate_dl_factor_generator(self, df, params=None):
        """
        使用深度学习因子生成器生成因子
        
        工作原理：
        1. 数据准备：使用OHLCV原始数据，标准化，生成序列数据
        2. 模型架构：CNN层提取局部特征，LSTM层捕捉时间序列依赖，全连接层输出因子
        3. 训练过程：预测未来收益率，MSE损失函数，Adam优化器
        4. 因子提取：使用训练好的模型中间层输出作为因子
        
        参数：
        - seq_length: 序列长度
        - factor_dim: 因子维度
        - epochs: 训练轮数
        - batch_size: 批次大小
        """
        try:
            from .dl_factor_generator import DLFactorGenerator
            
            params = params or {}
            seq_length = params.get("seq_length", 24)
            factor_dim = params.get("factor_dim", 32)
            epochs = params.get("epochs", 20)
            batch_size = params.get("batch_size", 32)
            
            # 初始化深度学习因子生成器
            dl_generator = DLFactorGenerator(
                raw_data=df, 
                seq_length=seq_length, 
                factor_dim=factor_dim
            )
            
            # 运行完整的深度学习因子生成流程
            dl_factors = dl_generator.run_full_dl_pipeline(
                epochs=epochs, 
                batch_size=batch_size
            )
            
            # 简单返回第一个深度学习因子作为示例
            if dl_factors is not None and len(dl_factors.columns) > 0:
                return dl_factors.iloc[:, 0]
            else:
                return df["close"].pct_change()
        except Exception as e:
            logger.error(f"DLFactorGenerator 调用失败: {e}")
            return df["close"].pct_change()

    def calculate_multi_factor_generator(self, df, params=None):
        """
        使用多因子策略整合生成因子
        
        工作原理：
        1. 初始化：加载数据到DataFramework，初始化FactorGenerator和DLFactorGenerator
        2. 因子生成流程：生成传统因子 → 生成深度学习因子（可选）→ 合并因子 → 添加到数据框架 → 清理因子矩阵
        3. 因子评估：计算IC值，按IC值筛选最佳因子，支持因子相关性去重
        
        参数：
        - n_factors: 生成因子数量
        - n_best: 选择最佳因子数量
        - use_dl_factors: 是否使用深度学习因子
        """
        try:
            from .eth_hourly_multi_factor import ETHHourlyMultiFactor
            
            params = params or {}
            timeframe = params.get("timeframe", "1h")
            n_factors = params.get("n_factors", 100)
            n_best = params.get("n_best", 20)
            use_dl_factors = params.get("use_dl_factors", True)
            
            # 初始化多因子策略
            strategy = ETHHourlyMultiFactor(timeframe=timeframe)
            
            # 加载数据
            strategy.load_data(df)
            
            # 运行因子生成
            best_factors = strategy.run_factor_generation(
                n_factors=n_factors,      # 生成n_factors个因子
                n_best=n_best,          # 选择n_best个最佳因子
                use_dl_factors=use_dl_factors # 使用深度学习因子
            )
            
            # 简单返回第一个最佳因子作为示例
            if best_factors is not None and len(best_factors.columns) > 0:
                return best_factors.iloc[:, 0]
            else:
                return df["close"].pct_change()
        except Exception as e:
            logger.error(f"ETHHourlyMultiFactor 调用失败: {e}")
            return df["close"].pct_change()

    # Alpha因子计算方法

    def calculate_alpha009(self, df, params=None):
        """
        计算Alpha 009 - 风险调整后的趋势或反转信号
        公式: (-1*RANK(STD(HIGH,10))*CORR(HIGH,1)+DELAY(LOW,1))/2*(HIGH-LOW)/VOLUME,7
        """
        # 计算标准差
        df["std_high"] = df["high"].rolling(window=10).std()
        # 计算排名
        df["rank_std_high"] = df["std_high"].rank()
        # 计算相关性（简化实现）
        df["corr_high"] = df["high"].rolling(window=5).corr(df["high"].shift(1))
        df["corr_high"].fillna(0, inplace=True)
        # 计算延迟
        df["delay_low"] = df["low"].shift(1)
        # 计算最终因子值
        df["alpha009"] = (
            (-1 * df["rank_std_high"] * df["corr_high"] + df["delay_low"])
            / 2
            * (df["high"] - df["low"])
            / df["volume"]
        )
        # 移动平均平滑
        df["alpha009"] = df["alpha009"].rolling(window=7).mean()
        return df

    def calculate_alpha042(self, df, params=None):
        """
        计算Alpha 042
        公式: (-1 * RANK(STD(HIGH, 10))) * CORR(HIGH, VOLUME, 10)

        该因子由两部分组成：
        1. 波动性排序反转：-1 * RANK(STD(HIGH,10)) - 对过去10日最高价标准差进行截面排序后取反
        2. 价量相关性：CORR(HIGH, VOLUME,10) - 过去10日最高价与成交量的时序相关系数

        通过波动性排序与价量相关性的交互作用生成信号，平衡风险与收益
        """
        params = params or {"window": 10}
        window = params["window"]

        # 第一部分：计算过去10日最高价的标准差
        df["high_std"] = df["high"].rolling(window=window).std()

        # 第二部分：计算过去10日最高价与成交量的时序相关系数
        df["high_vol_corr"] = df["high"].rolling(window=window).corr(df["volume"])

        # 对标准差进行截面排名（这里使用排名百分比）
        df["rank_high_std"] = df["high_std"].rank(pct=True)

        # 计算最终因子值：波动性排序反转 * 价量相关性
        df["alpha042"] = (-1 * df["rank_high_std"]) * df["high_vol_corr"]

        # 处理NaN值
        df["alpha042"] = df["alpha042"].fillna(0)

        return df

    def calculate_alpha068(self, df, params=None):
        """
        计算Alpha 068
        公式: SMA(((HIGH+LOW)/2-(DELAY(HIGH,1)+DELAY(LOW,1))/2)*(HIGH-LOW)/VOLUME,15,2)
        """
        # 与alpha042类似，只是参数不同
        df["current_avg"] = (df["high"] + df["low"]) / 2
        df["prev_avg"] = (df["high"].shift(1) + df["low"].shift(1)) / 2
        df["diff"] = df["current_avg"] - df["prev_avg"]
        df["volatility"] = (df["high"] - df["low"]) / df["volume"]
        df["product"] = df["diff"] * df["volatility"]
        df["alpha068"] = df["product"].rolling(window=15).mean()
        df["alpha068"] = df["alpha068"].rolling(window=2).mean()
        return df

    def calculate_alpha070(self, df, params=None):
        """
        计算Alpha 070
        公式: STD(AMOUNT,6)
        """
        # 计算成交额
        df["amount"] = df["close"] * df["volume"]
        # 计算标准差
        df["alpha070"] = df["amount"].rolling(window=6).std()
        return df

    def calculate_alpha081(self, df, params=None):
        """
        计算Alpha 081
        公式: SMA(VOLUME,21,2)
        """
        # 计算SMA
        df["alpha081"] = df["volume"].rolling(window=21).mean()
        # 二次SMA
        df["alpha081"] = df["alpha081"].rolling(window=2).mean()
        return df

    def calculate_alpha095(self, df, params=None):
        """
        计算Alpha 095
        公式: STD(VOLUME,20)
        """
        df["alpha095"] = df["volume"].rolling(window=20).std()
        return df

    def calculate_alpha097(self, df, params=None):
        """
        计算Alpha 097
        公式: STD(VOLUME,10)
        """
        df["alpha097"] = df["volume"].rolling(window=10).std()
        return df

    def calculate_alpha100(self, df, params=None):
        """
        计算Alpha 100
        公式: STD(VOLUME, 20)

        核心是计算过去20日成交量（VOLUME）的标准差，反映市场情绪变化：
        - 高成交量标准差：伴随价格波动加剧，反映市场情绪剧烈变化（利空/利好信息释放、主力资金异动）
        - 低成交量标准差：预示市场处于观望期，价格趋势未明（横盘整理阶段）
        - 高成交量波动可能暗示流动性枯竭或资金分歧，需警惕价格反转
        - 成交量突然放大（标准差骤升）可能捕捉事件冲击后的短期交易机会
        """
        params = params or {"window": 20}
        window = params["window"]

        # 计算过去20日成交量的标准差
        df["alpha100"] = df["volume"].rolling(window=window).std()

        # 对结果进行标准化，使其在不同时间周期和品种间更具可比性
        # 使用z-score标准化：(x - mean) / std
        # 对于小样本数据，使用整个序列的统计量进行标准化
        mean = df["alpha100"].mean()
        std = df["alpha100"].std()

        # 只有当标准差不为零时才进行标准化
        if std != 0:
            df["alpha100"] = (df["alpha100"] - mean) / std
        else:
            df["alpha100"] = 0

        # 处理NaN值
        df["alpha100"] = df["alpha100"].fillna(0)

        return df

    def calculate_alpha120(self, df, params=None):
        """
        计算Alpha 120
        公式: (RANK(VWAP - CLOSE) / RANK(VWAP + CLOSE))

        分子部分：VWAP - CLOSE 反映当日成交均价与收盘价的偏离程度
        - 若 VWAP > CLOSE：盘中成交均价高于收盘价，可能隐含盘中买方力量较强但尾盘抛压导致价格回落，形成短期反转信号
        - 若 VWAP < CLOSE：可能暗示尾盘资金流入推动价格上涨，形成动量信号

        分母作为标准化参考，消除价格绝对水平的影响，便于跨股票可比性
        对分子和分母分别进行全市场截面排名，进一步消除市场整体波动的影响

        因子值解释：
        - 分子较大：反映尾盘抛售压力，次日存在价格反弹可能性，触发买入信号
        - 分子较小：暗示尾盘资金抢筹，次日延续上涨趋势，形成动量效应

        该因子可进一步与 alpha042 进行复合，增强信号强度
        """
        # 计算VWAP - 成交量加权平均价格
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap"] = (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()

        # 计算分子：VWAP - CLOSE，反映当日成交均价与收盘价的偏离程度
        df["vwap_close_diff"] = df["vwap"] - df["close"]

        # 计算分母：VWAP + CLOSE，作为标准化参考
        df["vwap_close_sum"] = df["vwap"] + df["close"]

        # 对分子和分母分别进行截面排名（使用排名百分比，范围0-1）
        df["rank_diff"] = df["vwap_close_diff"].rank(pct=True)
        df["rank_sum"] = df["vwap_close_sum"].rank(pct=True)

        # 计算最终因子值，避免除以零
        df["alpha120"] = df["rank_diff"] / df["rank_sum"].replace(0, 0.0001)

        # 处理NaN值
        df["alpha120"] = df["alpha120"].fillna(0)

        return df

    def calculate_alpha125(self, df, params=None):
        """
        计算Alpha 125
        公式: (RANK(DECAYLINEAR(CORR(VWAP,MEAN(VOLUME,80),17),20))/RANK(DECAYLINEAR(DELTA((CLOSE+VOLUME),5),16)))
        """
        # 简化实现：使用滚动相关性和排名
        df["vwap"] = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()
        df["mean_volume"] = df["volume"].rolling(window=80).mean()
        df["corr"] = df["vwap"].rolling(window=17).corr(df["mean_volume"])
        df["corr"].fillna(0, inplace=True)
        # 计算排名
        df["rank_corr"] = df["corr"].rank()
        df["delta"] = (df["close"] + df["volume"]) - (df["close"].shift(5) + df["volume"].shift(5))
        df["rank_delta"] = df["delta"].rank()
        # 计算最终因子值
        df["alpha125"] = df["rank_corr"] / df["rank_delta"]
        return df

    def calculate_alpha126(self, df, params=None):
        """
        计算Alpha 126
        公式: (CLOSE+HIGH+LOW)/3
        """
        df["alpha126"] = (df["close"] + df["high"] + df["low"]) / 3
        return df

    def calculate_alpha132(self, df, params=None):
        """
        计算Alpha 132
        公式: MEAN(AMOUNT,20)
        """
        df["amount"] = df["close"] * df["volume"]
        df["alpha132"] = df["amount"].rolling(window=20).mean()
        return df

    def calculate_alpha135(self, df, params=None):
        """
        计算Alpha 135
        公式: -SMA(DELAY(CLOSE,20),1,20,1)
        """
        df["delay_close"] = df["close"].shift(20)
        df["alpha135"] = -df["delay_close"].rolling(window=20).mean()
        return df

    def calculate_alpha153(self, df, params=None):
        """
        计算Alpha 153
        公式: (MEAN(CLOSE,3)+MEAN(CLOSE,6)+MEAN(CLOSE,12)+MEAN(CLOSE,24))/4
        """
        df["ma3"] = df["close"].rolling(window=3).mean()
        df["ma6"] = df["close"].rolling(window=6).mean()
        df["ma12"] = df["close"].rolling(window=12).mean()
        df["ma24"] = df["close"].rolling(window=24).mean()
        df["alpha153"] = (df["ma3"] + df["ma6"] + df["ma12"] + df["ma24"]) / 4
        return df

    def calculate_alpha164(self, df, params=None):
        """
        计算Alpha 164
        公式: MIN(((CLOSE>DELAY(CLOSE,1))?1/(CLOSE-DELAY(CLOSE,1)):1),12)/(HIGH-LOW)*100,13,2)
        """
        # 计算条件值
        df["condition"] = df.apply(
            lambda x: 1 / (x["close"] - x["close"].shift(1))
            if x["close"] > x["close"].shift(1)
            else 1,
            axis=1,
        )
        # 取最小值
        df["min_val"] = df["condition"].clip(upper=12)
        # 计算波动因子
        df["volatility"] = df["high"] - df["low"]
        # 避免除以零
        df["volatility"] = df["volatility"].replace(0, 1e-9)
        # 计算最终因子值
        df["alpha164"] = (df["min_val"] / df["volatility"]) * 100
        # 平滑处理
        df["alpha164"] = df["alpha164"].rolling(window=13).mean()
        df["alpha164"] = df["alpha164"].rolling(window=2).mean()
        return df

    def calculate_alpha173(self, df, params=None):
        """
        计算Alpha 173
        公式: 3*SMA(CLOSE,13,2)-2*SMA(SMA(CLOSE,13,2),13,2)+SMA(SMA(SMA(LOG(CLOSE),13,2),13,2),13,2)
        """
        # 计算SMA
        df["sma13"] = df["close"].rolling(window=13).mean()
        df["sma13_2"] = df["sma13"].rolling(window=2).mean()
        df["sma13_3"] = df["sma13_2"].rolling(window=13).mean()
        df["log_close"] = np.log(df["close"])
        df["sma_log"] = df["log_close"].rolling(window=13).mean()
        df["sma_log_2"] = df["sma_log"].rolling(window=2).mean()
        df["sma_log_3"] = df["sma_log_2"].rolling(window=13).mean()
        # 计算最终因子值
        df["alpha173"] = 3 * df["sma13_2"] - 2 * df["sma13_3"] + df["sma_log_3"]
        return df

    def calculate_alpha184(self, df, params=None):
        """
        计算Alpha 184
        公式: (RANK(CORR(DELAY(OPEN-CLOSE,1),CLOSE,200))+RANK(OPEN-CLOSE))
        """
        # 计算开盘收盘差
        df["open_close_diff"] = df["open"] - df["close"]
        # 计算延迟
        df["delay_diff"] = df["open_close_diff"].shift(1)
        # 计算相关性
        df["corr"] = df["delay_diff"].rolling(window=200).corr(df["close"])
        df["corr"].fillna(0, inplace=True)
        # 计算排名
        df["rank_corr"] = df["corr"].rank()
        df["rank_diff"] = df["open_close_diff"].rank()
        # 计算最终因子值
        df["alpha184"] = df["rank_corr"] + df["rank_diff"]
        return df

    # 因子回测和评估功能

    def backtest_factor(self, factor_code, symbol, timeframe, start_time, end_time, params=None):
        raise RuntimeError(
            "factor library backtest/performance is disabled; use factor_evaluator metrics only"
        )
        """
        回测单个因子
        
        Args:
            factor_code: 因子代码
            symbol: 交易对
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            params: 回测参数
            
        Returns:
            回测结果字典
        """
        params = params or {
            "signal_threshold": 0.5,
            "stop_loss": 0.05,
            "take_profit": 0.10,
            "leverage": 1,
        }

        logger.info(f"回测因子: {factor_code} {symbol} {timeframe}")

        # 获取K线数据
        kline_data = self.db_manager.get_kline_data(symbol, timeframe, start_time, end_time)
        if kline_data.empty:
            logger.error(f"未找到K线数据: {symbol} {timeframe}")
            return None

        # 计算因子值
        factor_df = self.calculate_factor(factor_code, kline_data, params)
        if factor_df is None:
            logger.error(f"因子计算失败: {factor_code}")
            return None

        # 生成交易信号
        signals = self.generate_signals(factor_df, factor_code, params)

        # 执行回测
        backtest_results = self.execute_backtest(signals, kline_data, params)

        # 计算绩效指标
        performance = self.calculate_performance(backtest_results)

        # 生成回测报告
        backtest_report = {
            "factor_code": factor_code,
            "symbol": symbol,
            "timeframe": timeframe,
            "start_time": start_time,
            "end_time": end_time,
            "params": params,
            "signals": len(signals[signals["signal"] != 0]),
            "performance": performance,
            "backtest_results": backtest_results,
        }

        return backtest_report

    def generate_signals(self, factor_df, factor_code, params):
        """
        基于因子值生成交易信号

        Args:
            factor_df: 包含因子值的数据框
            factor_code: 因子代码
            params: 信号生成参数

        Returns:
            包含信号的数据框
        """
        # 标准化因子值
        factor_values = factor_df[factor_code].dropna()
        factor_df["factor_norm"] = (factor_values - factor_values.mean()) / factor_values.std()

        # 生成信号：1=做多，-1=做空，0=平仓
        factor_df["signal"] = 0
        factor_df.loc[factor_df["factor_norm"] > params["signal_threshold"], "signal"] = 1
        factor_df.loc[factor_df["factor_norm"] < -params["signal_threshold"], "signal"] = -1

        return factor_df

    def execute_backtest(self, signals, kline_data, params):
        """
        执行回测

        Args:
            signals: 包含交易信号的数据框
            kline_data: K线数据
            params: 回测参数

        Returns:
            回测结果数据框
        """
        # 合并数据
        backtest_df = pd.merge(signals, kline_data, on="timestamp", how="inner")

        # 初始化回测结果
        backtest_df["position"] = 0
        backtest_df["pnl"] = 0.0
        backtest_df["cumulative_pnl"] = 0.0
        backtest_df["drawdown"] = 0.0

        # 模拟交易执行
        position = 0
        entry_price = 0
        cumulative_pnl = 0.0
        max_pnl = 0.0

        for i in range(1, len(backtest_df)):
            current_signal = backtest_df["signal"].iloc[i]
            close_price = backtest_df["close"].iloc[i]

            # 处理入场信号
            if current_signal != 0 and position == 0:
                position = current_signal
                entry_price = close_price
            # 处理出场信号
            elif current_signal != position and position != 0:
                # 计算盈亏
                pnl = (close_price - entry_price) / entry_price * position * params["leverage"]
                cumulative_pnl += pnl

                # 检查是否达到止损/止盈
                if (
                    abs((close_price - entry_price) / entry_price) >= params["stop_loss"]
                    or abs((close_price - entry_price) / entry_price) >= params["take_profit"]
                ):
                    position = 0
                # 信号反转
                elif current_signal != 0:
                    position = current_signal
                    entry_price = close_price
                else:
                    position = 0
            # 持有仓位时计算浮动盈亏
            elif position != 0:
                pnl = (close_price - entry_price) / entry_price * position * params["leverage"]
            else:
                pnl = 0.0

            # 更新回测结果
            backtest_df.at[i, "position"] = position
            backtest_df.at[i, "pnl"] = pnl
            backtest_df.at[i, "cumulative_pnl"] = cumulative_pnl

            # 计算最大回撤
            max_pnl = max(max_pnl, cumulative_pnl)
            drawdown = (max_pnl - cumulative_pnl) / max_pnl if max_pnl > 0 else 0
            backtest_df.at[i, "drawdown"] = drawdown

        return backtest_df

    def calculate_performance(self, backtest_df):
        raise RuntimeError(
            "factor library backtest/performance is disabled; use factor_evaluator metrics only"
        )
        """
        计算回测绩效指标
        
        Args:
            backtest_df: 回测结果数据框
            
        Returns:
            绩效指标字典
        """
        if backtest_df.empty:
            return {}

        cumulative_pnl = backtest_df["cumulative_pnl"].iloc[-1]
        total_trades = len(backtest_df[backtest_df["signal"] != 0])
        winning_trades = len(backtest_df[(backtest_df["pnl"] > 0) & (backtest_df["signal"] != 0)])
        losing_trades = len(backtest_df[(backtest_df["pnl"] < 0) & (backtest_df["signal"] != 0)])

        # 计算胜率
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # 计算盈亏比
        avg_win = backtest_df[backtest_df["pnl"] > 0]["pnl"].mean() if winning_trades > 0 else 0
        avg_loss = (
            abs(backtest_df[backtest_df["pnl"] < 0]["pnl"].mean()) if losing_trades > 0 else 1
        )
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0

        # 计算最大回撤
        max_drawdown = backtest_df["drawdown"].max()

        # 计算夏普比率（简化版）
        daily_returns = backtest_df["pnl"].resample("D").sum()
        sharpe_ratio = (
            daily_returns.mean() / daily_returns.std() * np.sqrt(252)
            if daily_returns.std() > 0
            else 0
        )

        performance = {
            "cumulative_return": cumulative_pnl,
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe_ratio,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
        }

        return performance

    def generate_backtest_report(self, backtest_results, output_path=None):
        raise RuntimeError(
            "factor library backtest/performance is disabled; use factor_evaluator metrics only"
        )
        """
        生成回测报告
        
        Args:
            backtest_results: 回测结果
            output_path: 输出路径
            
        Returns:
            报告路径
        """
        if not backtest_results:
            return None

        logger.info(f"生成回测报告: {backtest_results['factor_code']}")

        # 创建报告图表
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                f"累计收益 ({backtest_results['factor_code']})",
                "最大回撤",
                "交易信号分布",
                "绩效指标",
            ),
        )

        # 累计收益图表
        cumulative_pnl = backtest_results["backtest_results"]["cumulative_pnl"]
        timestamp = backtest_results["backtest_results"]["timestamp"]
        fig.add_trace(go.Scatter(x=timestamp, y=cumulative_pnl, name="累计收益"), row=1, col=1)

        # 最大回撤图表
        drawdown = backtest_results["backtest_results"]["drawdown"]
        fig.add_trace(
            go.Scatter(
                x=timestamp,
                y=drawdown,
                name="最大回撤",
                fill="tozeroy",
                fillcolor="rgba(255, 0, 0, 0.1)",
            ),
            row=1,
            col=2,
        )

        # 交易信号分布
        signals = backtest_results["backtest_results"]["signal"].value_counts()
        fig.add_trace(
            go.Bar(
                x=["做空", "无信号", "做多"],
                y=[signals.get(-1, 0), signals.get(0, 0), signals.get(1, 0)],
                name="信号分布",
            ),
            row=2,
            col=1,
        )

        # 绩效指标表格
        performance = backtest_results["performance"]
        performance_data = [
            ["累计收益", f"{performance['cumulative_return']:.2%}"],
            ["总交易次数", performance["total_trades"]],
            ["胜率", f"{performance['win_rate']:.2%}"],
            ["盈亏比", f"{performance['profit_factor']:.2f}"],
            ["最大回撤", f"{performance['max_drawdown']:.2%}"],
            ["夏普比率", f"{performance['sharpe_ratio']:.2f}"],
            ["平均盈利", f"{performance['avg_win']:.2%}"],
            ["平均亏损", f"{performance['avg_loss']:.2%}"],
        ]

        fig.add_trace(
            go.Table(
                header=dict(values=["指标", "值"], fill_color="paleturquoise", align="left"),
                cells=dict(
                    values=list(zip(*performance_data)), fill_color="lavender", align="left"
                ),
            ),
            row=2,
            col=2,
        )

        # 更新布局
        fig.update_layout(
            height=800,
            width=1000,
            title_text=f"因子回测报告: {backtest_results['factor_code']} {backtest_results['symbol']} {backtest_results['timeframe']}",
            template="plotly_white",
        )

        # 保存报告
        if output_path:
            fig.write_html(output_path)
            logger.info(f"回测报告已保存到: {output_path}")

        return output_path

    def compare_factors(self, factor_codes, symbol, timeframe, start_time, end_time, params=None):
        raise RuntimeError(
            "factor library backtest/performance is disabled; use factor_evaluator metrics only"
        )
        """
        比较多个因子的回测表现
        
        Args:
            factor_codes: 因子代码列表
            symbol: 交易对
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间
            params: 回测参数
            
        Returns:
            比较结果字典
        """
        params = params or {}

        logger.info(f"比较因子: {', '.join(factor_codes)} {symbol} {timeframe}")

        # 回测所有因子
        backtest_results = {}
        for factor_code in factor_codes:
            result = self.backtest_factor(
                factor_code, symbol, timeframe, start_time, end_time, params
            )
            if result:
                backtest_results[factor_code] = result

        # 生成比较图表
        performance_metrics = [
            "cumulative_return",
            "win_rate",
            "profit_factor",
            "max_drawdown",
            "sharpe_ratio",
        ]

        # 创建雷达图
        fig = go.Figure()

        for factor_code, result in backtest_results.items():
            performance = result["performance"]
            values = [
                performance["cumulative_return"],
                performance["win_rate"],
                performance["profit_factor"],
                1 - performance["max_drawdown"],  # 转换为正值便于比较
                performance["sharpe_ratio"],
            ]

            fig.add_trace(
                go.Scatterpolar(
                    r=values,
                    theta=["累计收益", "胜率", "盈亏比", "1-最大回撤", "夏普比率"],
                    name=factor_code,
                )
            )

        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[
                        0,
                        max(
                            [
                                max(result["performance"][metric] for metric in performance_metrics)
                                for result in backtest_results.values()
                            ]
                        ),
                    ],
                )
            ),
            title=f"因子绩效比较 ({symbol} {timeframe})",
            template="plotly_white",
        )

        # 保存比较图表
        comparison_path = f"factor_comparison_{symbol}_{timeframe}.html"
        fig.write_html(comparison_path)
        logger.info(f"因子比较图表已保存到: {comparison_path}")

        return {"backtest_results": backtest_results, "comparison_chart": comparison_path}

    def close(self):
        """
        关闭数据库连接
        """
        self.db_manager.disconnect()


# 示例使用
if __name__ == "__main__":
    # 创建因子库实例
    factor_lib = FactorLibrary()

    # 初始化因子
    factor_lib.initialize_factors()

    # 计算因子 - 只测试一个简单组合，避免处理大量数据
    symbol = "ETH-USDT"
    timeframe = "1h"
    start_time = datetime(2025, 1, 1)
    end_time = datetime(2025, 1, 30)

    try:
        logger.info(f"\n=== 处理: {symbol} {timeframe} ===")

        # 计算所有因子
        factor_lib.calculate_all_factors(symbol, timeframe, limit=30)

        # 可视化因子
        factor_codes = ["ma", "rsi", "macd", "volatility", "momentum", "mvrv", "nupl", "sopr"]

        # 生成因子可视化报告
        output_path = "factor_visualization_report.html"
        factor_lib.generate_factor_visualization_report(
            factor_codes=factor_codes,
            symbols=[symbol],
            timeframes=[timeframe],
            start_time=start_time,
            end_time=end_time,
            output_path=output_path,
        )

        logger.info("\n=== 因子计算和可视化完成 ===")

    except Exception as e:
        logger.error(f"因子处理失败: {e}")
    finally:
        # 关闭连接
        factor_lib.close()
