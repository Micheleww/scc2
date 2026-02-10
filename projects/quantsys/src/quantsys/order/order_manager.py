import json
import time
import uuid
from enum import Enum
from typing import Any


class OrderStatus(Enum):
    CREATED = "CREATED"
    SENT = "SENT"
    ACK = "ACK"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"


class Order:
    def __init__(
        self,
        idempotency_key: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
    ):
        self.order_id = str(uuid.uuid4())
        self.idempotency_key = idempotency_key
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.status = OrderStatus.CREATED
        self.created_time = time.time()
        self.updated_time = time.time()
        self.last_action_time = time.time()

    def update_status(self, status: OrderStatus):
        self.status = status
        self.updated_time = time.time()
        self.last_action_time = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "idempotency_key": self.idempotency_key,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "status": self.status.value,
            "created_time": self.created_time,
            "updated_time": self.updated_time,
        }


class OrderManager:
    def __init__(self, journal_path: str = "order_journal.jsonl"):
        self.orders: dict[str, Order] = {}
        self.idempotency_map: dict[str, str] = {}
        self.journal_path = journal_path
        self.pending_cancels: set[str] = set()
        self.max_retry_attempts = 3
        self.retry_delay = 1.0
        self.order_timeout = 30.0

    def _write_journal(self, action: str, order: Order, **kwargs):
        entry = {
            "timestamp": time.time(),
            "action": action,
            "order_id": order.order_id,
            "idempotency_key": order.idempotency_key,
            "status": order.status.value,
            **kwargs,
        }
        with open(self.journal_path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def place_order(
        self,
        idempotency_key: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float | None = None,
    ) -> str | None:
        # 幂等检查：同一信号只允许一个"开仓意图"落到一个订单
        if idempotency_key in self.idempotency_map:
            existing_order_id = self.idempotency_map[idempotency_key]
            existing_order = self.orders[existing_order_id]
            self._write_journal(
                "PLACE_ORDER_DUPLICATE", existing_order, reason="Idempotency key already used"
            )
            return existing_order_id

        # 创建新订单
        order = Order(idempotency_key, symbol, side, quantity, price)
        self.orders[order.order_id] = order
        self.idempotency_map[idempotency_key] = order.order_id

        self._write_journal("PLACE_ORDER_CREATED", order)

        # 模拟订单发送
        return self._send_order(order)

    def _send_order(self, order: Order) -> str:
        # 模拟网络延迟
        time.sleep(0.1)

        order.update_status(OrderStatus.SENT)
        self._write_journal("PLACE_ORDER_SENT", order)

        # 模拟交易所确认
        return self._acknowledge_order(order)

    def _acknowledge_order(self, order: Order) -> str:
        # 模拟网络延迟
        time.sleep(0.1)

        order.update_status(OrderStatus.ACK)
        self._write_journal("PLACE_ORDER_ACK", order)

        # 模拟订单成交
        return self._fill_order(order)

    def _fill_order(self, order: Order) -> str:
        # 模拟网络延迟
        time.sleep(0.1)

        order.update_status(OrderStatus.FILLED)
        self._write_journal("PLACE_ORDER_FILLED", order)

        return order.order_id

    def cancel_order(self, order_id: str) -> bool:
        if order_id not in self.orders:
            return False

        order = self.orders[order_id]

        # 只有特定状态的订单可以取消
        if order.status not in [OrderStatus.CREATED, OrderStatus.SENT, OrderStatus.ACK]:
            self._write_journal(
                "CANCEL_ORDER_REJECTED", order, reason="Order not in cancelable status"
            )
            return False

        # 标记为待取消
        self.pending_cancels.add(order_id)
        self._write_journal("CANCEL_ORDER_REQUESTED", order)

        # 模拟取消请求发送
        time.sleep(0.1)

        order.update_status(OrderStatus.CANCELED)
        self.pending_cancels.remove(order_id)
        self._write_journal("CANCEL_ORDER_CONFIRMED", order)

        return True

    def get_order(self, order_id: str) -> Order | None:
        return self.orders.get(order_id)

    def get_order_by_idempotency(self, idempotency_key: str) -> Order | None:
        if idempotency_key in self.idempotency_map:
            return self.orders.get(self.idempotency_map[idempotency_key])
        return None

    def check_timeouts(self):
        current_time = time.time()
        for order in self.orders.values():
            if (
                order.status in [OrderStatus.SENT, OrderStatus.ACK]
                and (current_time - order.last_action_time) > self.order_timeout
            ):
                self._write_journal("ORDER_TIMEOUT", order, timeout_seconds=self.order_timeout)
                # 超时订单标记为失败
                previous_status = order.status
                order.update_status(OrderStatus.REJECTED)
                # 记录状态变更
                self._write_journal(
                    "ORDER_STATUS_CHANGED",
                    order,
                    from_status=previous_status.value,
                    to_status=OrderStatus.REJECTED.value,
                )

    def retry_order(self, order_id: str) -> str | None:
        if order_id not in self.orders:
            return None

        order = self.orders[order_id]

        # 只有失败状态的订单可以重试
        if order.status != OrderStatus.REJECTED:
            self._write_journal(
                "RETRY_ORDER_REJECTED", order, reason="Order not in retryable status"
            )
            return None

        # 创建新的幂等键（基于原订单ID和时间戳）
        new_idempotency_key = f"{order.idempotency_key}_retry_{time.time()}"

        # 创建新订单重试
        new_order = Order(
            new_idempotency_key, order.symbol, order.side, order.quantity, order.price
        )

        self.orders[new_order.order_id] = new_order
        self.idempotency_map[new_idempotency_key] = new_order.order_id

        self._write_journal("RETRY_ORDER_CREATED", new_order, original_order_id=order.order_id)

        # 发送重试订单
        return self._send_order(new_order)

    def get_all_orders(self) -> dict[str, Order]:
        return self.orders.copy()
