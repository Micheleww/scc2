#!/usr/bin/env python3
"""
信号总线系统
策略层只输出信号，通过信号总线传递，执行层监听信号并执行
实现策略层与执行层的解耦
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型枚举"""

    ENTER = "enter"  # 入场信号
    EXIT = "exit"  # 出场信号
    HOLD = "hold"  # 持有信号
    ADJUST = "adjust"  # 调整信号


@dataclass
class Signal:
    """
    交易信号数据类
    策略层只输出信号，不直接执行订单
    """

    signal_id: str = field(
        default_factory=lambda: f"signal_{int(time.time())}_{int(time.time() * 1000) % 10000}"
    )
    signal_type: SignalType = SignalType.HOLD
    symbol: str = ""
    side: str = ""  # buy/sell
    strength: float = 0.0  # 信号强度 0.0-1.0
    stop_loss: float | None = None  # 止损价
    take_profit: float | None = None  # 止盈价
    strategy_id: str = "default"
    strategy_version: str = "v1.0.0"
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "signal_id": self.signal_id,
            "signal_type": self.signal_type.value,
            "symbol": self.symbol,
            "side": self.side,
            "strength": self.strength,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


class SignalBus:
    """
    信号总线
    负责信号的发布和订阅
    """

    def __init__(self):
        """初始化信号总线"""
        self.subscribers: dict[str, list[Callable]] = {}  # {signal_type: [callbacks]}
        self.signal_history: list[Signal] = []
        logger.info("SignalBus initialized")

    def subscribe(self, signal_type: SignalType, callback: Callable[[Signal], None]):
        """
        订阅信号

        Args:
            signal_type: 信号类型
            callback: 回调函数，接收Signal参数
        """
        signal_type_str = signal_type.value
        if signal_type_str not in self.subscribers:
            self.subscribers[signal_type_str] = []

        self.subscribers[signal_type_str].append(callback)
        logger.info(f"Subscribed to {signal_type_str} signals")

    def publish(self, signal: Signal):
        """
        发布信号

        Args:
            signal: 交易信号
        """
        # 记录信号历史
        self.signal_history.append(signal)

        # 通知订阅者
        signal_type_str = signal.signal_type.value
        if signal_type_str in self.subscribers:
            for callback in self.subscribers[signal_type_str]:
                try:
                    callback(signal)
                except Exception as e:
                    logger.error(f"Error in signal callback: {e}", exc_info=True)

        logger.info(f"Published signal: {signal.signal_id} ({signal_type_str}) for {signal.symbol}")

    def get_signal_history(self, symbol: str | None = None, limit: int = 100) -> list[Signal]:
        """
        获取信号历史

        Args:
            symbol: 交易对（可选）
            limit: 返回数量限制

        Returns:
            List[Signal]: 信号列表
        """
        history = self.signal_history
        if symbol:
            history = [s for s in history if s.symbol == symbol]

        return history[-limit:]

    def unsubscribe(self, signal_type: SignalType, callback: Callable[[Signal], None]):
        """
        取消订阅

        Args:
            signal_type: 信号类型
            callback: 回调函数
        """
        signal_type_str = signal_type.value
        if signal_type_str in self.subscribers:
            if callback in self.subscribers[signal_type_str]:
                self.subscribers[signal_type_str].remove(callback)
                logger.info(f"Unsubscribed from {signal_type_str} signals")


# 全局信号总线实例
_global_signal_bus: SignalBus | None = None


def get_signal_bus() -> SignalBus:
    """
    获取全局信号总线实例（单例模式）

    Returns:
        SignalBus: 信号总线实例
    """
    global _global_signal_bus
    if _global_signal_bus is None:
        _global_signal_bus = SignalBus()
    return _global_signal_bus


def set_signal_bus(signal_bus: SignalBus):
    """
    设置全局信号总线实例（用于测试）

    Args:
        signal_bus: 信号总线实例
    """
    global _global_signal_bus
    _global_signal_bus = signal_bus
