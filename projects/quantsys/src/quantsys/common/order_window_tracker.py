#!/usr/bin/env python3
"""
订单时间窗口跟踪器
防止订单拆分攻击，跟踪时间窗口内的累计订单金额
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WindowOrder:
    """时间窗口内的订单记录"""

    timestamp: float
    amount: float
    symbol: str
    side: str


class OrderWindowTracker:
    """
    订单时间窗口跟踪器
    跟踪指定时间窗口内的订单，用于防止订单拆分攻击
    """

    def __init__(self, window_seconds: int = 60, max_window_amount: float = 1000.0):
        """
        初始化订单窗口跟踪器

        Args:
            window_seconds: 时间窗口大小（秒），默认60秒
            max_window_amount: 时间窗口内最大累计金额（USDT），默认1000.0
        """
        self.window_seconds = window_seconds
        self.max_window_amount = max_window_amount
        self._orders: deque = deque()  # 使用deque存储订单，自动过期
        self._lock = threading.Lock()
        logger.info(
            f"OrderWindowTracker initialized: window={window_seconds}s, max_amount={max_window_amount} USDT"
        )

    def add_order(self, amount: float, symbol: str, side: str) -> tuple[bool, float]:
        """
        添加订单到时间窗口

        Args:
            amount: 订单金额（USDT）
            symbol: 交易对
            side: 买卖方向

        Returns:
            tuple: (is_allowed, current_window_total)
                is_allowed: 是否允许（如果累计金额未超限）
                current_window_total: 当前窗口内的累计金额
        """
        with self._lock:
            current_time = time.time()

            # 清理过期订单
            self._cleanup_expired(current_time)

            # 计算当前窗口内的累计金额
            current_total = sum(order.amount for order in self._orders)

            # 检查是否超过限制（使用严格小于，更安全）
            new_total = current_total + amount
            is_allowed = new_total < self.max_window_amount  # 严格小于，不允许等于限制

            if is_allowed:
                # 添加订单到窗口
                order = WindowOrder(timestamp=current_time, amount=amount, symbol=symbol, side=side)
                self._orders.append(order)
                logger.info(
                    f"订单已添加到窗口: {symbol} {side} {amount} USDT, 窗口累计={new_total:.2f} USDT"
                )
                return True, new_total
            else:
                logger.warning(
                    f"订单被拒绝（窗口累计超限）: {symbol} {side} {amount} USDT, "
                    f"当前累计={current_total:.2f} USDT, 新累计={new_total:.2f} USDT, "
                    f"限制={self.max_window_amount} USDT"
                )
                return False, current_total

    def get_window_total(self) -> float:
        """
        获取当前时间窗口内的累计金额

        Returns:
            float: 累计金额（USDT）
        """
        with self._lock:
            current_time = time.time()
            self._cleanup_expired(current_time)
            return sum(order.amount for order in self._orders)

    def get_window_orders(self) -> list[dict[str, any]]:
        """
        获取当前时间窗口内的所有订单

        Returns:
            List[Dict]: 订单列表
        """
        with self._lock:
            current_time = time.time()
            self._cleanup_expired(current_time)
            return [
                {
                    "timestamp": order.timestamp,
                    "amount": order.amount,
                    "symbol": order.symbol,
                    "side": order.side,
                }
                for order in self._orders
            ]

    def _cleanup_expired(self, current_time: float) -> None:
        """
        清理过期的订单

        Args:
            current_time: 当前时间戳
        """
        cutoff_time = current_time - self.window_seconds

        # 从左侧移除过期订单
        while self._orders and self._orders[0].timestamp < cutoff_time:
            expired_order = self._orders.popleft()
            logger.debug(
                f"订单已过期: {expired_order.symbol} {expired_order.side} "
                f"{expired_order.amount} USDT (age={current_time - expired_order.timestamp:.1f}s)"
            )

    def reset(self) -> None:
        """重置窗口（清空所有订单）"""
        with self._lock:
            self._orders.clear()
            logger.info("订单窗口已重置")

    def get_stats(self) -> dict[str, any]:
        """
        获取窗口统计信息

        Returns:
            Dict: 统计信息
        """
        with self._lock:
            current_time = time.time()
            self._cleanup_expired(current_time)

            total = sum(order.amount for order in self._orders)
            count = len(self._orders)

            return {
                "window_seconds": self.window_seconds,
                "max_window_amount": self.max_window_amount,
                "current_total": total,
                "order_count": count,
                "remaining_capacity": max(0, self.max_window_amount - total),
                "utilization": total / self.max_window_amount
                if self.max_window_amount > 0
                else 0.0,
            }
