#!/usr/bin/env python3
"""
QuantSys Trading Engine - 可扩展的交易执行系统
替代freqtrade的完整功能，支持策略、回测、实盘交易、API服务等
"""

from .core.trading_bot import TradingBot
from .core.strategy_base import StrategyBase
from .core.data_provider import DataProvider
from .core.backtest_engine import BacktestEngine
from .api.server import TradingAPIServer

__all__ = [
    "TradingBot",
    "StrategyBase",
    "DataProvider",
    "BacktestEngine",
    "TradingAPIServer",
]

__version__ = "1.0.0"
