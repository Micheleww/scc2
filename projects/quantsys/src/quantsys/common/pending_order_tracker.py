#!/usr/bin/env python3
"""
Pending订单跟踪器
准确跟踪所有pending订单，用于风险控制
"""

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """订单状态"""

    PENDING = "pending"  # 待成交
    PARTIALLY_FILLED = "partially_filled"  # 部分成交
    FILLED = "filled"  # 已成交
    CANCELED = "canceled"  # 已取消
    REJECTED = "rejected"  # 已拒绝


@dataclass
class PendingOrder:
    """Pending订单记录"""

    order_id: str
    symbol: str
    side: str
    amount: float  # 订单金额（USDT）
    price: float | None
    status: OrderStatus
    created_time: float
    updated_time: float


class PendingOrderTracker:
    """
    Pending订单跟踪器
    准确跟踪所有pending订单，提供原子性的订单管理
    """

    def __init__(self):
        """初始化Pending订单跟踪器"""
        self._orders: dict[str, PendingOrder] = {}  # order_id -> PendingOrder
        self._lock = threading.Lock()
        logger.info("PendingOrderTracker initialized")

    def add_order(
        self, order_id: str, symbol: str, side: str, amount: float, price: float | None = None
    ) -> bool:
        """
        添加pending订单

        Args:
            order_id: 订单ID
            symbol: 交易对
            side: 买卖方向
            amount: 订单金额（USDT）
            price: 订单价格（可选）

        Returns:
            bool: 是否成功添加
        """
        with self._lock:
            if order_id in self._orders:
                logger.warning(f"订单已存在: {order_id}")
                return False

            order = PendingOrder(
                order_id=order_id,
                symbol=symbol,
                side=side,
                amount=amount,
                price=price,
                status=OrderStatus.PENDING,
                created_time=time.time(),
                updated_time=time.time(),
            )
            self._orders[order_id] = order
            logger.info(f"Pending订单已添加: {order_id} {symbol} {side} {amount} USDT")
            return True

    def update_order_status(
        self, order_id: str, status: OrderStatus, filled_amount: float | None = None
    ) -> bool:
        """
        更新订单状态

        Args:
            order_id: 订单ID
            status: 新状态
            filled_amount: 已成交金额（用于部分成交）

        Returns:
            bool: 是否成功更新
        """
        with self._lock:
            if order_id not in self._orders:
                logger.warning(f"订单不存在: {order_id}")
                return False

            order = self._orders[order_id]
            order.status = status
            order.updated_time = time.time()

            # 如果是部分成交，更新金额
            if status == OrderStatus.PARTIALLY_FILLED and filled_amount is not None:
                remaining = order.amount - filled_amount
                if remaining > 0:
                    order.amount = remaining
                    logger.info(f"订单部分成交: {order_id}, 剩余金额={remaining:.2f} USDT")
                else:
                    order.status = OrderStatus.FILLED
                    logger.info(f"订单已完全成交: {order_id}")

            # 如果订单已完成（成交/取消/拒绝），从pending列表中移除
            if status in [OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.REJECTED]:
                del self._orders[order_id]
                logger.info(f"Pending订单已移除: {order_id} (状态={status.value})")

            return True

    def remove_order(self, order_id: str) -> bool:
        """
        移除订单（用于取消或拒绝）

        Args:
            order_id: 订单ID

        Returns:
            bool: 是否成功移除
        """
        with self._lock:
            if order_id not in self._orders:
                return False

            order = self._orders[order_id]
            del self._orders[order_id]
            logger.info(f"Pending订单已移除: {order_id} {order.symbol} {order.side}")
            return True

    def get_total_pending_amount(self, side: str | None = None) -> float:
        """
        获取总pending金额

        Args:
            side: 买卖方向过滤（'buy'或'sell'），None表示所有方向

        Returns:
            float: 总pending金额（USDT）
        """
        with self._lock:
            if side:
                return sum(
                    order.amount
                    for order in self._orders.values()
                    if order.side == side and order.status == OrderStatus.PENDING
                )
            else:
                return sum(
                    order.amount
                    for order in self._orders.values()
                    if order.status == OrderStatus.PENDING
                )

    def get_pending_orders(
        self, symbol: str | None = None, side: str | None = None
    ) -> list[dict[str, any]]:
        """
        获取pending订单列表

        Args:
            symbol: 交易对过滤
            side: 买卖方向过滤

        Returns:
            List[Dict]: 订单列表
        """
        with self._lock:
            orders = []
            for order in self._orders.values():
                if order.status != OrderStatus.PENDING:
                    continue
                if symbol and order.symbol != symbol:
                    continue
                if side and order.side != side:
                    continue

                orders.append(
                    {
                        "order_id": order.order_id,
                        "symbol": order.symbol,
                        "side": order.side,
                        "amount": order.amount,
                        "price": order.price,
                        "created_time": order.created_time,
                        "updated_time": order.updated_time,
                    }
                )

            return orders

    def get_order(self, order_id: str) -> PendingOrder | None:
        """
        获取订单信息

        Args:
            order_id: 订单ID

        Returns:
            Optional[PendingOrder]: 订单对象或None
        """
        with self._lock:
            return self._orders.get(order_id)

    def get_stats(self) -> dict[str, any]:
        """
        获取统计信息

        Returns:
            Dict: 统计信息
        """
        with self._lock:
            total_pending = self.get_total_pending_amount()
            buy_pending = self.get_total_pending_amount(side="buy")
            sell_pending = self.get_total_pending_amount(side="sell")
            order_count = len([o for o in self._orders.values() if o.status == OrderStatus.PENDING])

            return {
                "total_pending_amount": total_pending,
                "buy_pending_amount": buy_pending,
                "sell_pending_amount": sell_pending,
                "pending_order_count": order_count,
                "total_tracked_orders": len(self._orders),
            }

    def clear(self) -> None:
        """清空所有订单"""
        with self._lock:
            self._orders.clear()
            logger.info("所有pending订单已清空")
