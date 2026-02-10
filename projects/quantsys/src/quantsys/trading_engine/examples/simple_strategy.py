#!/usr/bin/env python3
"""
简单示例策略
展示如何使用StrategyBase创建策略
"""

import pandas as pd

from src.quantsys.trading_engine.core.strategy_base import StrategyBase


class SimpleStrategy(StrategyBase):
    """
    简单策略示例
    使用RSI和移动平均线生成交易信号
    """

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """填充技术指标"""
        # RSI指标
        dataframe["rsi"] = self._calculate_rsi(dataframe["close"], period=14)
        
        # 移动平均线
        dataframe["sma_20"] = dataframe["close"].rolling(window=20).mean()
        dataframe["sma_50"] = dataframe["close"].rolling(window=50).mean()
        
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """填充入场信号"""
        # 做多条件: RSI < 30 且 价格在20日均线上方
        dataframe.loc[
            (dataframe["rsi"] < 30) &
            (dataframe["close"] > dataframe["sma_20"]),
            "enter_long"
        ] = 1
        
        # 做空条件: RSI > 70 且 价格在20日均线下方
        dataframe.loc[
            (dataframe["rsi"] > 70) &
            (dataframe["close"] < dataframe["sma_20"]),
            "enter_short"
        ] = 1
        
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        """填充出场信号"""
        # 做多出场: RSI > 70 或 价格跌破20日均线
        dataframe.loc[
            (dataframe["rsi"] > 70) |
            (dataframe["close"] < dataframe["sma_20"]),
            "exit_long"
        ] = 1
        
        # 做空出场: RSI < 30 或 价格突破20日均线
        dataframe.loc[
            (dataframe["rsi"] < 30) |
            (dataframe["close"] > dataframe["sma_20"]),
            "exit_short"
        ] = 1
        
        return dataframe

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> pd.Series:
        """计算RSI指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
