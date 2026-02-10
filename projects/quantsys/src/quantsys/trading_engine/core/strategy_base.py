#!/usr/bin/env python3
"""
策略基类
提供统一的策略接口，兼容freqtrade策略格式，支持可扩展的策略开发
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


class StrategyBase(ABC):
    """
    策略基类
    所有交易策略必须继承此类
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化策略

        Args:
            config: 策略配置字典
        """
        self.config = config or {}
        self.name = self.__class__.__name__
        self.timeframe = self.config.get("timeframe", "1h")
        self.stake_currency = self.config.get("stake_currency", "USDT")
        self.stake_amount = self.config.get("stake_amount", 0.01)
        self.max_open_trades = self.config.get("max_open_trades", 3)
        
        # 策略状态
        self.positions: Dict[str, Dict] = {}
        self.orders: Dict[str, Dict] = {}
        
        logger.info(f"策略 {self.name} 初始化完成")

    @abstractmethod
    def populate_indicators(self, dataframe: pd.DataFrame, metadata: Dict) -> pd.DataFrame:
        """
        填充技术指标
        
        Args:
            dataframe: K线数据
            metadata: 元数据（包含交易对等信息）
            
        Returns:
            添加了指标后的DataFrame
        """
        pass

    @abstractmethod
    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: Dict) -> pd.DataFrame:
        """
        填充入场信号
        
        Args:
            dataframe: 包含指标的数据
            metadata: 元数据
            
        Returns:
            添加了入场信号的DataFrame（enter_long, enter_short列）
        """
        pass

    @abstractmethod
    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: Dict) -> pd.DataFrame:
        """
        填充出场信号
        
        Args:
            dataframe: 包含指标的数据
            metadata: 元数据
            
        Returns:
            添加了出场信号的DataFrame（exit_long, exit_short列）
        """
        pass

    def informative_pairs(self) -> List[tuple]:
        """
        定义需要获取的其他时间周期或交易对
        
        Returns:
            列表，格式: [('BTC/USDT', '1d'), ('ETH/USDT', '4h')]
        """
        return []

    def leverage(self, pair: str, current_time: datetime, current_rate: float,
                 proposed_leverage: float, max_leverage: float, entry_tag: str,
                 is_entry: bool, **kwargs) -> float:
        """
        动态杠杆计算
        
        Returns:
            杠杆倍数
        """
        return proposed_leverage

    def custom_stoploss(self, pair: str, trade, current_time: datetime,
                       current_rate: float, current_profit: float, **kwargs) -> float:
        """
        自定义止损
        
        Returns:
            止损比例（负数，如-0.02表示2%止损）
        """
        return self.config.get("stoploss", -0.10)

    def custom_exit(self, pair: str, trade, current_time: datetime, current_rate: float,
                   current_profit: float, **kwargs) -> Optional[str]:
        """
        自定义出场条件
        
        Returns:
            出场标签或None
        """
        return None

    def confirm_trade_entry(self, pair: str, order_type: str, amount: float,
                           rate: float, time_in_force: str, current_time: datetime,
                           entry_tag: Optional[str], side: str, **kwargs) -> bool:
        """
        确认是否允许入场
        
        Returns:
            True允许，False拒绝
        """
        return True

    def confirm_trade_exit(self, pair: str, trade, order_type: str, amount: float,
                          rate: float, time_in_force: str, exit_reason: str,
                          current_time: datetime, **kwargs) -> bool:
        """
        确认是否允许出场
        
        Returns:
            True允许，False拒绝
        """
        return True

    def adjust_trade_position(self, trade, current_time: datetime, current_rate: float,
                             current_profit: float, min_stake: float, max_stake: float,
                             current_entry_rate: float, current_exit_rate: float,
                             current_entry_profit: float, current_exit_profit: float,
                             **kwargs) -> Optional[float]:
        """
        动态调整仓位大小
        
        Returns:
            新的仓位大小或None（不调整）
        """
        return None

    def bot_start(self, **kwargs) -> None:
        """
        策略启动时调用
        """
        logger.info(f"策略 {self.name} 启动")

    def bot_stop(self, **kwargs) -> None:
        """
        策略停止时调用
        """
        logger.info(f"策略 {self.name} 停止")

    def get_strategy_config(self) -> Dict[str, Any]:
        """
        获取策略配置
        
        Returns:
            策略配置字典
        """
        return {
            "name": self.name,
            "timeframe": self.timeframe,
            "stake_currency": self.stake_currency,
            "stake_amount": self.stake_amount,
            "max_open_trades": self.max_open_trades,
            **self.config,
        }
