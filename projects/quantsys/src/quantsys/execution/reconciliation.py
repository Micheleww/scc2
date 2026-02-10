#!/usr/bin/env python3

"""
Reconciliation module for exchange-local state synchronization.

This module provides functionality to reconcile exchange state with local state,
identifying discrepancies and generating actionable reports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DriftType(Enum):
    """Types of state drift that can be detected."""

    BALANCE = "BALANCE"
    ORDER = "ORDER"
    POSITION = "POSITION"
    FILL = "FILL"
    UNKNOWN = "UNKNOWN"


class RecommendedAction(Enum):
    """Recommended actions based on reconciliation results."""

    BLOCK = "BLOCK"  # Block all trading activities
    RESYNC = "RESYNC"  # Resynchronize state from exchange
    CANCEL_ALL = "CANCEL_ALL"  # Cancel all open orders
    FLATTEN = "FLATTEN"  # Close all positions
    NONE = "NONE"  # No action needed
    CHECK_TIME_SETTINGS = "CHECK_TIME_SETTINGS"  # Check system time settings
    INVESTIGATE_CONFIG_CHANGES = "INVESTIGATE_CONFIG_CHANGES"  # Investigate configuration changes


@dataclass
class Balance:
    """Standardized balance information."""

    total: float
    available: float
    currency: str


@dataclass
class Position:
    """Standardized position information."""

    symbol: str
    side: str  # LONG/SHORT
    size: float
    entry_price: float
    unrealized_pnl: float


@dataclass
class Order:
    """Standardized order information."""

    id: str
    client_order_id: str | None
    symbol: str
    side: str  # BUY/SELL
    type: str  # MARKET/LIMIT/...
    price: float
    amount: float
    filled: float
    status: str  # OPEN/CLOSED/CANCELED/...


@dataclass
class Fill:
    """Standardized fill information."""

    id: str
    order_id: str
    symbol: str
    side: str  # BUY/SELL
    price: float
    amount: float
    timestamp: int


@dataclass
class ReconciliationDiff:
    """Structured difference between exchange and local state."""

    category: str  # BALANCE/POSITION/ORDER/FILL
    key: str  # Unique identifier for the item
    exchange_value: Any
    local_value: Any
    field: str | None = None
    threshold: float | None = None


@dataclass
class SnapshotMeta:
    """Metadata for a state snapshot."""

    timestamp: int
    symbols: list[str]
    source: str
    version: str = "1.0"


@dataclass
class ReconciliationReport:
    """Result of a reconciliation operation."""

    ok: bool
    drift_type: DriftType
    diffs: list[ReconciliationDiff]
    exchange_snapshot_meta: SnapshotMeta
    local_snapshot_meta: SnapshotMeta
    recommended_action: RecommendedAction
    summary: str = ""


class ReconciliationConfig:
    """Configuration for reconciliation process."""

    def __init__(self, **kwargs):
        self.balance_threshold: float = kwargs.get("balance_threshold", 0.01)
        self.position_threshold: float = kwargs.get("position_threshold", 0.001)
        self.price_threshold: float = kwargs.get("price_threshold", 0.001)
        self.max_fills_check: int = kwargs.get("max_fills_check", 50)
        self.symbol_map: dict[str, str] = kwargs.get("symbol_map", {})


class ExchangeStandardizer:
    """Standardizes exchange responses to a unified schema."""

    @staticmethod
    def standardize_balance(exchange_balance: dict[str, Any], currency: str = "USDT") -> Balance:
        """Standardize exchange balance response."""
        if isinstance(exchange_balance, dict):
            # Check if it's OKX API format: {'code': '0', 'msg': '', 'data': [{'ccy': 'USDT', 'availBal': '1000', 'cashBal': '1000'}]}
            if (
                "code" in exchange_balance
                and exchange_balance.get("code") == "0"
                and "data" in exchange_balance
            ):
                data = exchange_balance["data"]
                if isinstance(data, list) and len(data) > 0:
                    # Find the balance for the requested currency
                    for balance_item in data:
                        if balance_item.get("ccy") == currency:
                            total = balance_item.get("cashBal", "0.0") or "0.0"
                            available = balance_item.get("availBal", "0.0") or "0.0"
                            return Balance(
                                total=float(total), available=float(available), currency=currency
                            )
            # CCXT format: {'total': {'USDT': 1000}, 'free': {'USDT': 900}}
            elif "total" in exchange_balance and "free" in exchange_balance:
                total = exchange_balance["total"].get(currency, 0.0) or 0.0
                available = exchange_balance["free"].get(currency, 0.0) or 0.0
            # Some exchanges return direct balance object
            elif "balance" in exchange_balance:
                total = exchange_balance["balance"].get(currency, 0.0) or 0.0
                available = exchange_balance["balance"].get(currency, 0.0) or 0.0
            else:
                # Fallback: try to get total and available directly
                total = exchange_balance.get("total", 0.0) or 0.0
                available = exchange_balance.get("available", 0.0) or 0.0
        else:
            total = 0.0
            available = 0.0

        return Balance(total=float(total), available=float(available), currency=currency)

    @staticmethod
    def standardize_positions(exchange_positions: list[dict[str, Any]]) -> list[Position]:
        """Standardize exchange positions response."""
        standardized = []

        # Check if it's OKX API format: {'code': '0', 'msg': '', 'data': [{'instId': 'ETH-USDT-SWAP', 'posSide': 'long', 'pos': '0.001'}]}
        if (
            isinstance(exchange_positions, dict)
            and "code" in exchange_positions
            and exchange_positions.get("code") == "0"
        ):
            exchange_positions = exchange_positions.get("data", [])

        for pos in exchange_positions:
            if isinstance(pos, dict):
                # Skip closed positions
                if pos.get("size", 0.0) == 0 and pos.get("pos", 0.0) == 0:
                    continue

                # Handle OKX API format
                if "instId" in pos:
                    symbol = pos.get("instId", "")
                    side = pos.get("posSide", "long").upper()
                    size = float(pos.get("pos", "0.0"))
                    entry_price = float(pos.get("avgPx", "0.0") or "0.0")
                    unrealized_pnl = float(pos.get("upl", "0.0") or "0.0")
                # Handle CCXT format
                else:
                    symbol = pos.get("symbol", "")
                    side = "LONG" if pos.get("size", 0.0) > 0 else "SHORT"
                    size = abs(float(pos.get("size", 0.0)))
                    entry_price = float(pos.get("entryPrice", pos.get("average", 0.0)))
                    unrealized_pnl = float(pos.get("unrealizedPnl", 0.0))

                standardized.append(
                    Position(
                        symbol=symbol,
                        side=side,
                        size=size,
                        entry_price=entry_price,
                        unrealized_pnl=unrealized_pnl,
                    )
                )

        return standardized

    @staticmethod
    def standardize_orders(exchange_orders: list[dict[str, Any]]) -> list[Order]:
        """Standardize exchange orders response."""
        standardized = []

        # Check if it's OKX API format: {'code': '0', 'msg': '', 'data': [{'ordId': '123', 'clOrdId': '456', 'instId': 'ETH-USDT-SWAP'}]}
        if (
            isinstance(exchange_orders, dict)
            and "code" in exchange_orders
            and exchange_orders.get("code") == "0"
        ):
            exchange_orders = exchange_orders.get("data", [])

        for order in exchange_orders:
            if isinstance(order, dict):
                # Handle OKX API format
                if "ordId" in order:
                    # Skip closed/canceled orders
                    state = order.get("state", "").lower()
                    status_map = {
                        "pending": "OPEN",
                        "live": "OPEN",
                        "partially_filled": "PARTIAL",
                        "filled": "FILLED",
                        "canceled": "CANCELED",
                        "rejected": "REJECTED",
                    }
                    status = status_map.get(state, state.upper())

                    # Skip filled or canceled orders
                    if status in ["FILLED", "CANCELED", "REJECTED"]:
                        continue

                    standardized.append(
                        Order(
                            id=order.get("ordId", ""),
                            client_order_id=order.get("clOrdId"),
                            symbol=order.get("instId", ""),
                            side=order.get("side", "").upper(),
                            type=order.get("ordType", "").upper(),
                            price=float(order.get("px", "0.0") or "0.0"),
                            amount=float(order.get("sz", "0.0") or "0.0"),
                            filled=float(order.get("accFillSz", "0.0") or "0.0"),
                            status=status,
                        )
                    )
                # Handle CCXT format
                else:
                    # Skip closed/canceled orders
                    status = order.get("status", "").upper()
                    if status in ["CLOSED", "CANCELED", "FILLED"] and float(
                        order.get("filled", 0.0) or 0.0
                    ) >= float(order.get("amount", 0.0) or 0.0):
                        continue

                    standardized.append(
                        Order(
                            id=order.get("id", ""),
                            client_order_id=order.get("clientOrderId"),
                            symbol=order.get("symbol", ""),
                            side=order.get("side", "").upper(),
                            type=order.get("type", "").upper(),
                            price=float(order.get("price", 0.0) or 0.0),
                            amount=float(order.get("amount", order.get("quantity", 0.0)) or 0.0),
                            filled=float(order.get("filled", 0.0) or 0.0),
                            status=status,
                        )
                    )

        return standardized

    @staticmethod
    def standardize_fills(exchange_fills: list[dict[str, Any]]) -> list[Fill]:
        """Standardize exchange fills response."""
        standardized = []

        for fill in exchange_fills:
            if isinstance(fill, dict):
                standardized.append(
                    Fill(
                        id=fill.get("id", ""),
                        order_id=fill.get("orderId", fill.get("order_id", "")),
                        symbol=fill.get("symbol", ""),
                        side=fill.get("side", "").upper(),
                        price=float(fill.get("price", 0.0)),
                        amount=float(fill.get("amount", fill.get("quantity", 0.0))),
                        timestamp=int(fill.get("timestamp", fill.get("time", 0))),
                    )
                )

        # Sort by timestamp descending
        return sorted(standardized, key=lambda x: x.timestamp, reverse=True)


class ReconciliationEngine:
    """Engine for reconciling exchange state with local state."""

    def __init__(self, config: ReconciliationConfig):
        self.config = config
        self.standardizer = ExchangeStandardizer()

    def reconcile_balance(
        self, exchange_balance: Balance, local_balance: Balance
    ) -> list[ReconciliationDiff]:
        """Reconcile balance information."""
        diffs = []
        threshold = self.config.balance_threshold

        # Check total balance
        if abs(exchange_balance.total - local_balance.total) > threshold:
            diffs.append(
                ReconciliationDiff(
                    category="BALANCE",
                    key=f"balance_{exchange_balance.currency}",
                    exchange_value=exchange_balance.total,
                    local_value=local_balance.total,
                    field="total",
                    threshold=threshold,
                )
            )

        # Check available balance
        if abs(exchange_balance.available - local_balance.available) > threshold:
            diffs.append(
                ReconciliationDiff(
                    category="BALANCE",
                    key=f"balance_{exchange_balance.currency}",
                    exchange_value=exchange_balance.available,
                    local_value=local_balance.available,
                    field="available",
                    threshold=threshold,
                )
            )

        return diffs

    def reconcile_positions(
        self, exchange_positions: list[Position], local_positions: list[Position]
    ) -> list[ReconciliationDiff]:
        """Reconcile position information."""
        diffs = []
        size_threshold = self.config.position_threshold
        price_threshold = self.config.price_threshold

        # Create position maps for easy comparison
        exchange_pos_map = {pos.symbol: pos for pos in exchange_positions}
        local_pos_map = {pos.symbol: pos for pos in local_positions}

        # Check all positions from exchange
        for symbol, exchange_pos in exchange_pos_map.items():
            if symbol not in local_pos_map:
                # Position exists on exchange but not locally
                diffs.append(
                    ReconciliationDiff(
                        category="POSITION",
                        key=symbol,
                        exchange_value=exchange_pos,
                        local_value=None,
                        field="existence",
                    )
                )
            else:
                # Compare position details
                local_pos = local_pos_map[symbol]

                # Check side
                if exchange_pos.side != local_pos.side:
                    diffs.append(
                        ReconciliationDiff(
                            category="POSITION",
                            key=symbol,
                            exchange_value=exchange_pos.side,
                            local_value=local_pos.side,
                            field="side",
                        )
                    )

                # Check size
                if abs(exchange_pos.size - local_pos.size) > size_threshold:
                    diffs.append(
                        ReconciliationDiff(
                            category="POSITION",
                            key=symbol,
                            exchange_value=exchange_pos.size,
                            local_value=local_pos.size,
                            field="size",
                            threshold=size_threshold,
                        )
                    )

                # Check entry price (allow small percentage difference)
                if exchange_pos.entry_price > 0 and local_pos.entry_price > 0:
                    price_diff = (
                        abs(exchange_pos.entry_price - local_pos.entry_price)
                        / exchange_pos.entry_price
                    )
                    if price_diff > price_threshold:
                        diffs.append(
                            ReconciliationDiff(
                                category="POSITION",
                                key=symbol,
                                exchange_value=exchange_pos.entry_price,
                                local_value=local_pos.entry_price,
                                field="entry_price",
                                threshold=price_threshold,
                            )
                        )

        # Check for positions that exist locally but not on exchange
        for symbol in local_pos_map:
            if symbol not in exchange_pos_map:
                diffs.append(
                    ReconciliationDiff(
                        category="POSITION",
                        key=symbol,
                        exchange_value=None,
                        local_value=local_pos_map[symbol],
                        field="existence",
                    )
                )

        return diffs

    def reconcile_orders(
        self, exchange_orders: list[Order], local_orders: list[Order]
    ) -> list[ReconciliationDiff]:
        """Reconcile order information."""
        diffs = []

        # Create order maps (use client_order_id if available, otherwise id)
        def get_order_key(order: Order) -> str:
            return order.client_order_id if order.client_order_id else order.id

        exchange_order_map = {get_order_key(order): order for order in exchange_orders}
        local_order_map = {get_order_key(order): order for order in local_orders}

        # Check all orders from exchange
        for key, exchange_order in exchange_order_map.items():
            if key not in local_order_map:
                # Order exists on exchange but not locally
                diffs.append(
                    ReconciliationDiff(
                        category="ORDER",
                        key=key,
                        exchange_value=exchange_order,
                        local_value=None,
                        field="existence",
                    )
                )
            else:
                # Compare order details
                local_order = local_order_map[key]

                # Compare critical fields
                for field in ["symbol", "side", "type", "price", "amount", "status"]:
                    exchange_val = getattr(exchange_order, field)
                    local_val = getattr(local_order, field)

                    if isinstance(exchange_val, float) and isinstance(local_val, float):
                        # Allow small difference for price/amount
                        if abs(exchange_val - local_val) > 0.0001:
                            diffs.append(
                                ReconciliationDiff(
                                    category="ORDER",
                                    key=key,
                                    exchange_value=exchange_val,
                                    local_value=local_val,
                                    field=field,
                                    threshold=0.0001,
                                )
                            )
                    elif exchange_val != local_val:
                        diffs.append(
                            ReconciliationDiff(
                                category="ORDER",
                                key=key,
                                exchange_value=exchange_val,
                                local_value=local_val,
                                field=field,
                            )
                        )

        # Check for orders that exist locally but not on exchange
        for key in local_order_map:
            if key not in exchange_order_map:
                diffs.append(
                    ReconciliationDiff(
                        category="ORDER",
                        key=key,
                        exchange_value=None,
                        local_value=local_order_map[key],
                        field="existence",
                    )
                )

        return diffs

    def reconcile_fills(
        self, exchange_fills: list[Fill], local_fills: list[Fill]
    ) -> list[ReconciliationDiff]:
        """Reconcile fill information (optional)."""
        diffs = []

        # Only check recent fills (up to max_fills_check)
        exchange_fills = exchange_fills[: self.config.max_fills_check]
        local_fills = local_fills[: self.config.max_fills_check]

        # Create fill maps
        exchange_fill_map = {fill.id: fill for fill in exchange_fills}
        local_fill_map = {fill.id: fill for fill in local_fills}

        # Check for duplicate fills or missing fills
        for fill_id, exchange_fill in exchange_fill_map.items():
            if fill_id not in local_fill_map:
                # Fill exists on exchange but not locally (could be new fill)
                continue

            # Compare fill details
            local_fill = local_fill_map[fill_id]

            for field in ["symbol", "side", "price", "amount", "order_id"]:
                exchange_val = getattr(exchange_fill, field)
                local_val = getattr(local_fill, field)

                if isinstance(exchange_val, float) and isinstance(local_val, float):
                    if abs(exchange_val - local_val) > 0.0001:
                        diffs.append(
                            ReconciliationDiff(
                                category="FILL",
                                key=fill_id,
                                exchange_value=exchange_val,
                                local_value=local_val,
                                field=field,
                            )
                        )
                elif exchange_val != local_val:
                    diffs.append(
                        ReconciliationDiff(
                            category="FILL",
                            key=fill_id,
                            exchange_value=exchange_val,
                            local_value=local_val,
                            field=field,
                        )
                    )

        return diffs

    def generate_recommended_action(
        self, drift_type: DriftType, diff_count: int
    ) -> RecommendedAction:
        """Generate recommended action based on drift type and severity."""
        if diff_count == 0:
            return RecommendedAction.NONE

        action_map = {
            DriftType.BALANCE: RecommendedAction.BLOCK,
            DriftType.ORDER: RecommendedAction.CANCEL_ALL,
            DriftType.POSITION: RecommendedAction.FLATTEN,
            DriftType.FILL: RecommendedAction.RESYNC,
            DriftType.UNKNOWN: RecommendedAction.BLOCK,
        }

        return action_map.get(drift_type, RecommendedAction.BLOCK)


class OrderReconciliation:
    """
    订单对账类
    实现本地订单与交易所订单的匹配逻辑
    """

    @staticmethod
    def match_orders(
        local_orders: list[dict[str, Any]], exchange_orders: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        匹配本地订单与交易所订单

        匹配规则：
        1. 优先使用clientOrderId匹配
        2. 没有clientOrderId时，使用(symbol, side, price, amount, create_ts≈)做备用匹配
        3. 标记匹配类型为"strong_match"或"weak_match"

        Args:
            local_orders: 本地订单列表
            exchange_orders: 交易所订单列表

        Returns:
            matched_orders: 匹配结果列表
        """
        matched_results = []

        # 复制交易所订单列表，用于跟踪已匹配的订单
        available_exchange_orders = exchange_orders.copy()

        # 第一步：使用clientOrderId进行强匹配
        for local_order in local_orders:
            local_client_order_id = local_order.get("clientOrderId")
            matched = False

            # 跳过已完成的订单
            if local_order.get("status") in ["FILLED", "CANCELED", "REJECTED"]:
                continue

            # 寻找匹配的交易所订单
            for i, exchange_order in enumerate(available_exchange_orders):
                exchange_client_order_id = exchange_order.get("clOrdId") or exchange_order.get(
                    "clientOrderId"
                )

                # 如果双方都有clientOrderId且匹配
                if (
                    local_client_order_id
                    and exchange_client_order_id
                    and local_client_order_id == exchange_client_order_id
                ):
                    matched_results.append(
                        {
                            "local_order": local_order,
                            "exchange_order": exchange_order,
                            "match_type": "strong_match",
                            "match_reason": f"clientOrderId匹配: {local_client_order_id}",
                        }
                    )
                    # 从可用列表中移除已匹配的交易所订单
                    available_exchange_orders.pop(i)
                    matched = True
                    break

            if matched:
                continue

            # 第二步：备用匹配（弱匹配）
            # 使用(symbol, side, price, amount, create_ts≈)进行匹配
            for i, exchange_order in enumerate(available_exchange_orders):
                # 检查基本字段匹配
                symbol_match = local_order.get("symbol") == exchange_order.get("instId")
                side_match = local_order.get("side") == exchange_order.get("side")

                # 价格匹配：允许1%的误差
                local_price = local_order.get("price") or 0.0
                exchange_price = float(exchange_order.get("px") or 0.0)
                price_match = abs(local_price - exchange_price) / (local_price or 1.0) <= 0.01

                # 数量匹配：允许1%的误差
                local_amount = local_order.get("amount") or 0.0
                exchange_amount = float(exchange_order.get("sz") or 0.0)
                amount_match = abs(local_amount - exchange_amount) / (local_amount or 1.0) <= 0.01

                # 时间匹配：允许5分钟的误差
                local_create_ts = local_order.get("create_ts") or 0.0
                exchange_create_ts = float(exchange_order.get("cTime") or 0.0) / 1000  # 转换为秒
                time_match = abs(local_create_ts - exchange_create_ts) <= 5 * 60

                if symbol_match and side_match and price_match and amount_match and time_match:
                    matched_results.append(
                        {
                            "local_order": local_order,
                            "exchange_order": exchange_order,
                            "match_type": "weak_match",
                            "match_reason": f"备用匹配: symbol={local_order.get('symbol')}, side={local_order.get('side')}, price={local_price}, amount={local_amount}",
                        }
                    )
                    # 从可用列表中移除已匹配的交易所订单
                    available_exchange_orders.pop(i)
                    break

        return matched_results

    @staticmethod
    def find_unmatched_orders(
        local_orders: list[dict[str, Any]],
        exchange_orders: list[dict[str, Any]],
        matched_results: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """
        查找未匹配的订单

        Args:
            local_orders: 本地订单列表
            exchange_orders: 交易所订单列表
            matched_results: 已匹配结果列表

        Returns:
            unmatched_local: 未匹配的本地订单
            unmatched_exchange: 未匹配的交易所订单
        """
        # 收集已匹配的本地订单ID和交易所订单ID
        matched_local_ids = set()
        matched_exchange_ids = set()

        for result in matched_results:
            matched_local_ids.add(result["local_order"].get("clientOrderId"))
            exchange_order_id = result["exchange_order"].get("ordId") or result[
                "exchange_order"
            ].get("orderId")
            matched_exchange_ids.add(exchange_order_id)

        # 查找未匹配的本地订单
        unmatched_local = [
            order
            for order in local_orders
            if order.get("clientOrderId") not in matched_local_ids
            and order.get("status") in ["CREATED", "SENT", "ACK", "OPEN", "PARTIAL"]
        ]

        # 查找未匹配的交易所订单
        unmatched_exchange = [
            order
            for order in exchange_orders
            if (order.get("ordId") or order.get("orderId")) not in matched_exchange_ids
        ]

        return unmatched_local, unmatched_exchange

    @staticmethod
    def reconcile(
        local_orders: list[dict[str, Any]], exchange_orders: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        执行对账流程

        Args:
            local_orders: 本地订单列表
            exchange_orders: 交易所订单列表

        Returns:
            reconciliation_result: 对账结果
        """
        import logging
        import time

        logger = logging.getLogger(__name__)

        logger.info(
            f"开始对账：本地订单数={len(local_orders)}, 交易所订单数={len(exchange_orders)}"
        )

        # 匹配订单
        matched_results = OrderReconciliation.match_orders(local_orders, exchange_orders)

        # 查找未匹配订单
        unmatched_local, unmatched_exchange = OrderReconciliation.find_unmatched_orders(
            local_orders, exchange_orders, matched_results
        )

        # 计算匹配统计
        total_local_active = sum(
            1
            for order in local_orders
            if order.get("status") in ["CREATED", "SENT", "ACK", "OPEN", "PARTIAL"]
        )
        total_exchange = len(exchange_orders)

        reconciliation_result = {
            "timestamp": time.time(),
            "total_local_active": total_local_active,
            "total_exchange": total_exchange,
            "matched_count": len(matched_results),
            "matched_orders": matched_results,
            "unmatched_local": unmatched_local,
            "unmatched_exchange": unmatched_exchange,
            "match_rate": len(matched_results) / max(total_local_active, 1),
            "drift_count": len(unmatched_local) + len(unmatched_exchange),
        }

        logger.info(
            f"对账完成：匹配订单数={len(matched_results)}, 未匹配本地订单数={len(unmatched_local)}, 未匹配交易所订单数={len(unmatched_exchange)}"
        )

        return reconciliation_result

    @staticmethod
    def format_reconciliation_result(result: dict[str, Any]) -> str:
        """
        格式化对账结果

        Args:
            result: 对账结果

        Returns:
            formatted_result: 格式化后的结果字符串
        """
        import time

        lines = [
            "=== 订单对账结果 ===",
            f"对账时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(result['timestamp']))}",
            f"本地活跃订单: {result['total_local_active']}",
            f"交易所订单: {result['total_exchange']}",
            f"匹配订单: {result['matched_count']}",
            f"匹配率: {result['match_rate']:.2%}",
            f"漂移订单: {result['drift_count']}",
            "\n匹配详情:",
        ]

        for i, match in enumerate(result["matched_orders"], 1):
            match_type = match["match_type"]
            local_client_id = match["local_order"].get("clientOrderId")
            exchange_order_id = match["exchange_order"].get("ordId") or match["exchange_order"].get(
                "orderId"
            )
            symbol = match["local_order"].get("symbol")
            side = match["local_order"].get("side")

            lines.append(
                f"{i}. [{match_type}] {symbol} {side} | 本地ID: {local_client_id} | 交易所ID: {exchange_order_id}"
            )

        if result["unmatched_local"]:
            lines.append("\n未匹配本地订单:")
            for i, order in enumerate(result["unmatched_local"], 1):
                lines.append(
                    f"{i}. {order.get('symbol')} {order.get('side')} | 本地ID: {order.get('clientOrderId')}"
                )

        if result["unmatched_exchange"]:
            lines.append("\n未匹配交易所订单:")
            for i, order in enumerate(result["unmatched_exchange"], 1):
                lines.append(
                    f"{i}. {order.get('instId')} {order.get('side')} | 交易所ID: {order.get('ordId') or order.get('orderId')}"
                )

        return "\n".join(lines)


def reconcile(
    exchange_client,
    local_state: dict[str, Any],
    symbol_map: dict[str, str],
    now_ts: int,
    config: dict[str, Any],
) -> ReconciliationReport:
    """
    Main reconciliation function.

    Args:
        exchange_client: CCXT exchange client instance
        local_state: Local state dictionary
        symbol_map: Mapping from local symbols to exchange symbols
        now_ts: Current timestamp in milliseconds
        config: Reconciliation configuration

    Returns:
        ReconciliationReport: Result of the reconciliation
    """
    # Create reconciliation config
    recon_config = ReconciliationConfig(
        balance_threshold=config.get("balance_threshold", 0.01),
        position_threshold=config.get("position_threshold", 0.001),
        price_threshold=config.get("price_threshold", 0.001),
        max_fills_check=config.get("max_fills_check", 50),
        symbol_map=symbol_map,
    )

    engine = ReconciliationEngine(recon_config)
    all_diffs = []

    # Get symbols to reconcile
    symbols = list(symbol_map.values())

    # 1. Fetch and standardize exchange data
    try:
        # Fetch exchange data (mock-safe: only read operations)
        exchange_balance_raw = getattr(exchange_client, "fetch_balance", lambda: {})()
        exchange_positions_raw = getattr(exchange_client, "fetch_positions", lambda: [])()
        exchange_orders_raw = getattr(exchange_client, "fetch_open_orders", lambda: [])()
        exchange_fills_raw = getattr(exchange_client, "fetch_my_trades", lambda: [])()

        # Standardize exchange data
        exchange_balance = engine.standardizer.standardize_balance(exchange_balance_raw)
        exchange_positions = engine.standardizer.standardize_positions(exchange_positions_raw)
        exchange_orders = engine.standardizer.standardize_orders(exchange_orders_raw)
        exchange_fills = engine.standardizer.standardize_fills(exchange_fills_raw)

        # Extract exchange symbols
        exchange_symbols = list({pos.symbol for pos in exchange_positions})
        exchange_symbols.extend({order.symbol for order in exchange_orders})
        exchange_symbols = list(set(exchange_symbols))

        exchange_meta = SnapshotMeta(timestamp=now_ts, symbols=exchange_symbols, source="exchange")
    except Exception as e:
        # If exchange data fetch fails, report error
        local_meta = SnapshotMeta(timestamp=now_ts, symbols=symbols, source="local")
        return ReconciliationReport(
            ok=False,
            drift_type=DriftType.UNKNOWN,
            diffs=[
                ReconciliationDiff(
                    category="UNKNOWN",
                    key="exchange_fetch_failed",
                    exchange_value=None,
                    local_value=None,
                    field="error",
                    threshold=None,
                )
            ],
            exchange_snapshot_meta=SnapshotMeta(
                timestamp=now_ts, symbols=[], source="exchange", version="1.0"
            ),
            local_snapshot_meta=local_meta,
            recommended_action=RecommendedAction.BLOCK,
            summary=f"Failed to fetch exchange data: {str(e)}",
        )

    # 2. Extract and standardize local data
    try:
        # Extract local data
        local_balance_raw = local_state.get("balance", {})
        local_positions_raw = local_state.get("positions", [])
        local_orders_raw = local_state.get("orders", [])
        local_fills_raw = local_state.get("fills", [])

        # Standardize local data (using same standardizer for consistency)
        local_balance = engine.standardizer.standardize_balance(local_balance_raw)
        local_positions = engine.standardizer.standardize_positions(local_positions_raw)
        local_orders = engine.standardizer.standardize_orders(local_orders_raw)
        local_fills = engine.standardizer.standardize_fills(local_fills_raw)

        local_meta = SnapshotMeta(timestamp=now_ts, symbols=symbols, source="local")
    except Exception as e:
        return ReconciliationReport(
            ok=False,
            drift_type=DriftType.UNKNOWN,
            diffs=[
                ReconciliationDiff(
                    category="UNKNOWN",
                    key="local_data_invalid",
                    exchange_value=None,
                    local_value=None,
                    field="error",
                    threshold=None,
                )
            ],
            exchange_snapshot_meta=exchange_meta,
            local_snapshot_meta=SnapshotMeta(
                timestamp=now_ts, symbols=[], source="local", version="1.0"
            ),
            recommended_action=RecommendedAction.BLOCK,
            summary=f"Invalid local state: {str(e)}",
        )

    # 3. Perform reconciliation
    balance_diffs = engine.reconcile_balance(exchange_balance, local_balance)
    position_diffs = engine.reconcile_positions(exchange_positions, local_positions)
    order_diffs = engine.reconcile_orders(exchange_orders, local_orders)
    fill_diffs = engine.reconcile_fills(exchange_fills, local_fills)

    all_diffs.extend(balance_diffs)
    all_diffs.extend(position_diffs)
    all_diffs.extend(order_diffs)
    all_diffs.extend(fill_diffs)

    # 4. Determine drift type
    drift_type = DriftType.UNKNOWN
    if balance_diffs:
        drift_type = DriftType.BALANCE
    elif position_diffs:
        drift_type = DriftType.POSITION
    elif order_diffs:
        drift_type = DriftType.ORDER
    elif fill_diffs:
        drift_type = DriftType.FILL

    # 5. Generate recommended action
    ok = len(all_diffs) == 0
    recommended_action = engine.generate_recommended_action(drift_type, len(all_diffs))

    # 6. Create summary
    summary = f"Reconciliation {'PASSED' if ok else 'FAILED'}: {len(all_diffs)} differences found"
    if not ok:
        summary += f" (Type: {drift_type.value})"

    # 7. Create and return report
    return ReconciliationReport(
        ok=ok,
        drift_type=drift_type,
        diffs=all_diffs,
        exchange_snapshot_meta=exchange_meta,
        local_snapshot_meta=local_meta,
        recommended_action=recommended_action,
        summary=summary,
    )
