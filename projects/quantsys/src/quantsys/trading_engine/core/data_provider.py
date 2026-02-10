#!/usr/bin/env python3
"""
数据提供者
负责获取和管理市场数据，支持多数据源、多时间周期
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class DataProvider:
    """
    数据提供者类
    统一管理市场数据的获取、缓存和提供
    """

    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化数据提供者

        Args:
            config: 配置字典
        """
        self.config = config or {}
        self.data_dir = Path(self.config.get("data_dir", "data"))
        self.cache_enabled = self.config.get("cache_enabled", True)
        self.cache_ttl = self.config.get("cache_ttl", 300)  # 5分钟缓存
        
        # 数据缓存
        self._cache: Dict[str, Dict] = {}
        
        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"数据提供者初始化完成，数据目录: {self.data_dir}")

    def get_ohlcv(
        self,
        pair: str,
        timeframe: str,
        since: Optional[datetime] = None,
        limit: int = 500,
        **kwargs
    ) -> pd.DataFrame:
        """
        获取OHLCV数据

        Args:
            pair: 交易对，如 'BTC/USDT'
            timeframe: 时间周期，如 '1h', '4h', '1d'
            since: 起始时间
            limit: 数据条数限制

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        cache_key = f"{pair}_{timeframe}_{since}_{limit}"
        
        # 检查缓存
        if self.cache_enabled and cache_key in self._cache:
            cached_data = self._cache[cache_key]
            if datetime.now() - cached_data["timestamp"] < timedelta(seconds=self.cache_ttl):
                logger.debug(f"使用缓存数据: {cache_key}")
                return cached_data["data"].copy()
        
        # 从文件加载数据
        df = self._load_from_file(pair, timeframe, since, limit)
        
        # 缓存数据
        if self.cache_enabled:
            self._cache[cache_key] = {
                "data": df.copy(),
                "timestamp": datetime.now(),
            }
        
        return df

    def _load_from_file(
        self,
        pair: str,
        timeframe: str,
        since: Optional[datetime] = None,
        limit: int = 500
    ) -> pd.DataFrame:
        """
        从文件加载数据

        Args:
            pair: 交易对
            timeframe: 时间周期
            since: 起始时间
            limit: 数据条数

        Returns:
            DataFrame
        """
        # 转换交易对格式
        pair_clean = pair.replace("/", "-")
        
        # 构建文件路径
        file_path = self.data_dir / f"{pair_clean}-{timeframe}.csv"
        
        if not file_path.exists():
            logger.warning(f"数据文件不存在: {file_path}")
            return pd.DataFrame()
        
        try:
            # 读取CSV文件
            df = pd.read_csv(file_path)
            
            # 确保有timestamp列
            if "timestamp" in df.columns:
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df = df.set_index("timestamp")
            elif "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
                df.index.name = "timestamp"
            
            # 确保必要的列存在
            required_columns = ["open", "high", "low", "close", "volume"]
            for col in required_columns:
                if col not in df.columns:
                    logger.error(f"数据文件缺少必要列: {col}")
                    return pd.DataFrame()
            
            # 按时间过滤
            if since:
                df = df[df.index >= since]
            
            # 限制数据条数
            if len(df) > limit:
                df = df.tail(limit)
            
            # 排序
            df = df.sort_index()
            
            logger.debug(f"从文件加载数据: {pair} {timeframe}, 共 {len(df)} 条")
            return df
            
        except Exception as e:
            logger.error(f"加载数据文件失败: {file_path}, 错误: {e}")
            return pd.DataFrame()

    def save_ohlcv(
        self,
        pair: str,
        timeframe: str,
        dataframe: pd.DataFrame,
        **kwargs
    ) -> bool:
        """
        保存OHLCV数据到文件

        Args:
            pair: 交易对
            timeframe: 时间周期
            dataframe: 数据

        Returns:
            是否成功
        """
        try:
            pair_clean = pair.replace("/", "-")
            file_path = self.data_dir / f"{pair_clean}-{timeframe}.csv"
            
            # 确保有timestamp索引
            if dataframe.index.name != "timestamp":
                dataframe.index.name = "timestamp"
            
            # 保存到CSV
            dataframe.to_csv(file_path)
            
            logger.info(f"数据已保存: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"保存数据失败: {e}")
            return False

    def get_ticker(self, pair: str) -> Dict[str, Any]:
        """
        获取最新价格

        Args:
            pair: 交易对

        Returns:
            价格信息字典
        """
        # 尝试获取1m数据，如果没有则使用最小时间周期
        df = self.get_ohlcv(pair, "1m", limit=1)
        
        # 如果1m数据不存在，尝试使用策略的时间周期
        if df.empty:
            # 获取所有可用时间周期
            timeframes = self.get_available_timeframes(pair)
            if timeframes:
                # 使用最小的时间周期
                min_timeframe = min(timeframes, key=lambda x: self._timeframe_to_minutes(x))
                df = self.get_ohlcv(pair, min_timeframe, limit=1)
        
        if df.empty:
            logger.warning(f"无法获取 {pair} 的价格数据")
            return {}
        
        latest = df.iloc[-1]
        
        return {
            "symbol": pair,
            "last": float(latest["close"]),
            "bid": float(latest["close"]),
            "ask": float(latest["close"]),
            "timestamp": latest.name.isoformat() if hasattr(latest.name, "isoformat") else str(latest.name),
        }
    
    def _timeframe_to_minutes(self, timeframe: str) -> int:
        """将时间周期转换为分钟数"""
        if timeframe.endswith("m"):
            return int(timeframe[:-1])
        elif timeframe.endswith("h"):
            return int(timeframe[:-1]) * 60
        elif timeframe.endswith("d"):
            return int(timeframe[:-1]) * 1440
        else:
            return 999999  # 未知时间周期，返回大值

    def clear_cache(self) -> None:
        """清空缓存"""
        self._cache.clear()
        logger.info("数据缓存已清空")

    def get_available_pairs(self) -> List[str]:
        """
        获取可用的交易对列表

        Returns:
            交易对列表
        """
        pairs = set()
        
        for file_path in self.data_dir.glob("*.csv"):
            # 解析文件名: BTC-USDT-1h.csv -> BTC/USDT
            parts = file_path.stem.split("-")
            if len(parts) >= 2:
                pair = f"{parts[0]}/{parts[1]}"
                pairs.add(pair)
        
        return sorted(list(pairs))

    def get_available_timeframes(self, pair: Optional[str] = None) -> List[str]:
        """
        获取可用的时间周期列表

        Args:
            pair: 交易对（可选）

        Returns:
            时间周期列表
        """
        timeframes = set()
        
        pattern = f"*-*.csv" if not pair else f"{pair.replace('/', '-')}-*.csv"
        
        for file_path in self.data_dir.glob(pattern):
            # 解析文件名: BTC-USDT-1h.csv -> 1h
            parts = file_path.stem.split("-")
            if len(parts) >= 3:
                timeframe = "-".join(parts[2:])
                timeframes.add(timeframe)
        
        return sorted(list(timeframes))
