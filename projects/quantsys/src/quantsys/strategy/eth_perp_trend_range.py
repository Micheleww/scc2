#!/usr/bin/env python3
"""
ETH perpetual 1h strategies for Quantsys backtest engine.
Includes a trend-following strategy and a range mean-reversion strategy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import talib.abstract as ta


@dataclass
class StrategyParams:
    timeframe: str = "1h"
    leverage: int = 3
    max_leverage: int = 10
    risk_per_trade: float = 0.008
    cooldown_candles: int = 48
    atr_period: int = 14
    atr_stop_mult: float = 2.0
    atr_trail_start_mult: float = 2.5
    atr_trail_mult: float = 1.5
    taker_entry_atr_mult: float = 0.6
    taker_exit_atr_mult: float = 0.6
    breakout_lookback: int = 20


class EthPerpTrendStrategy:
    """
    Trend-following strategy for ETH perpetual (1h).
    """

    name = "eth_perp_trend_1h"

    def __init__(self, params: StrategyParams | None = None) -> None:
        self.params = params or StrategyParams(
            leverage=3,
            cooldown_candles=96,
            atr_stop_mult=2.5,
            atr_trail_start_mult=3.5,
            taker_entry_atr_mult=1.0,
            breakout_lookback=40,
        )

    def populate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = ta.EMA(df, timeperiod=20)
        df["ema_slow"] = ta.EMA(df, timeperiod=60)
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["atr"] = ta.ATR(df, timeperiod=self.params.atr_period)
        df["rolling_high"] = df["high"].shift(1).rolling(self.params.breakout_lookback).max()
        df["rolling_low"] = df["low"].shift(1).rolling(self.params.breakout_lookback).min()
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.populate_indicators(df)
        adx_th = 30
        adx_exit = 22

        enter_long = (
            (df["ema_fast"] > df["ema_slow"])
            & (df["adx"] > adx_th)
            & (df["close"] > df["rolling_high"])
            & (df["close"] > df["ema_fast"])
            & (df["close"] > df["ema_slow"] * 1.002)
        )
        enter_short = (
            (df["ema_fast"] < df["ema_slow"])
            & (df["adx"] > adx_th)
            & (df["close"] < df["rolling_low"])
            & (df["close"] < df["ema_fast"])
            & (df["close"] < df["ema_slow"] * 0.998)
        )

        exit_long = (df["close"] < df["ema_slow"]) | (df["adx"] < adx_exit)
        exit_short = (df["close"] > df["ema_slow"]) | (df["adx"] < adx_exit)

        stop_distance = df["atr"] * self.params.atr_stop_mult
        taker_entry = (
            df["close"] - df["rolling_high"] > df["atr"] * self.params.taker_entry_atr_mult
        ) | (df["rolling_low"] - df["close"] > df["atr"] * self.params.taker_entry_atr_mult)
        taker_exit = df["atr"] * self.params.taker_exit_atr_mult

        signals = pd.DataFrame(index=df.index)
        signals["enter_long"] = enter_long.astype(int)
        signals["enter_short"] = enter_short.astype(int)
        signals["exit_long"] = exit_long.astype(int)
        signals["exit_short"] = exit_short.astype(int)
        signals["stop_distance"] = stop_distance
        signals["taker_entry"] = taker_entry.astype(int)
        signals["taker_exit_distance"] = taker_exit
        return signals

    def get_parameters(self) -> dict[str, Any]:
        return {
            "risk_management": {
                "risk_per_trade": self.params.risk_per_trade,
                "leverage": min(self.params.leverage, self.params.max_leverage),
                "max_leverage": self.params.max_leverage,
                "cooldown_candles": self.params.cooldown_candles,
                "atr_stop_mult": self.params.atr_stop_mult,
                "atr_trail_start_mult": self.params.atr_trail_start_mult,
                "atr_trail_mult": self.params.atr_trail_mult,
                "max_drawdown_limit": 0.08,
            },
            "order_config": {
                "entry_order_type": "limit",
                "exit_order_type": "limit",
                "stop_order_type": "market",
            },
        }


class EthPerpRangeStrategy:
    """
    Mean-reversion range strategy for ETH perpetual (1h).
    """

    name = "eth_perp_range_1h"

    def __init__(self, params: StrategyParams | None = None) -> None:
        self.params = params or StrategyParams(leverage=4, cooldown_candles=36, atr_stop_mult=1.6)

    def populate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["rsi"] = ta.RSI(df, timeperiod=14)
        df["adx"] = ta.ADX(df, timeperiod=14)
        df["atr"] = ta.ATR(df, timeperiod=self.params.atr_period)
        mid = df["close"].rolling(20).mean()
        std = df["close"].rolling(20).std()
        df["bb_mid"] = mid
        df["bb_upper"] = mid + 2 * std
        df["bb_lower"] = mid - 2 * std
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / mid
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.populate_indicators(df)
        adx_range = 18
        adx_break = 25
        width_range = 0.04
        width_break = 0.07

        range_regime = (df["adx"] < adx_range) & (df["bb_width"] < width_range)
        enter_long = range_regime & (df["close"] <= df["bb_lower"]) & (df["rsi"] < 30)
        enter_short = range_regime & (df["close"] >= df["bb_upper"]) & (df["rsi"] > 70)

        exit_long = (
            (df["close"] >= df["bb_mid"]) | (df["adx"] > adx_break) | (df["bb_width"] > width_break)
        )
        exit_short = (
            (df["close"] <= df["bb_mid"]) | (df["adx"] > adx_break) | (df["bb_width"] > width_break)
        )

        stop_distance = df["atr"] * self.params.atr_stop_mult
        taker_entry = (
            df["bb_lower"] - df["close"] > df["atr"] * self.params.taker_entry_atr_mult
        ) | (df["close"] - df["bb_upper"] > df["atr"] * self.params.taker_entry_atr_mult)
        taker_exit = df["atr"] * self.params.taker_exit_atr_mult

        signals = pd.DataFrame(index=df.index)
        signals["enter_long"] = enter_long.astype(int)
        signals["enter_short"] = enter_short.astype(int)
        signals["exit_long"] = exit_long.astype(int)
        signals["exit_short"] = exit_short.astype(int)
        signals["stop_distance"] = stop_distance
        signals["taker_entry"] = taker_entry.astype(int)
        signals["taker_exit_distance"] = taker_exit
        return signals

    def get_parameters(self) -> dict[str, Any]:
        return {
            "risk_management": {
                "risk_per_trade": self.params.risk_per_trade,
                "leverage": min(self.params.leverage, self.params.max_leverage),
                "max_leverage": self.params.max_leverage,
                "cooldown_candles": self.params.cooldown_candles,
                "atr_stop_mult": self.params.atr_stop_mult,
                "atr_trail_start_mult": self.params.atr_trail_start_mult,
                "atr_trail_mult": self.params.atr_trail_mult,
                "max_drawdown_limit": 0.08,
            },
            "order_config": {
                "entry_order_type": "limit",
                "exit_order_type": "limit",
                "stop_order_type": "market",
            },
        }
