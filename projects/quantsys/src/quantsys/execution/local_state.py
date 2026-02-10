#!/usr/bin/env python3

"""
Local State Management for Execution Layer

This module provides a unified interface to read local state snapshots without relying on exchanges.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .reconciliation import Balance, Fill, Order, Position, SnapshotMeta


@dataclass
class LocalSnapshot:
    """
    Local state snapshot containing balances, positions, orders, and fills.
    Aligned with AI-1 reconciliation standardized schema.
    """

    balances: dict[str, Balance]
    positions: list[Position]
    open_orders: list[Order]
    recent_fills: list[Fill]
    meta: SnapshotMeta


class LocalStateStore:
    """
    Local state store that can use either JSON file or database (if available).
    """

    def __init__(self, store_path: Path | None = None):
        """
        Initialize the local state store.

        Args:
            store_path: Path to the local state file (default: data/state/local_ledger.json)
        """
        self.store_path = store_path or Path("data/state/local_ledger.json")
        self._ensure_store_exists()

    def _ensure_store_exists(self):
        """Ensure the state store directory and file exist."""
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            with open(self.store_path, "w") as f:
                json.dump(
                    {"balances": {}, "positions": [], "orders": [], "fills": [], "last_updated": 0},
                    f,
                    indent=2,
                )

    def _read_state(self) -> dict[str, Any]:
        """Read the current state from the store."""
        try:
            with open(self.store_path) as f:
                return json.load(f)
        except Exception:
            return {"balances": {}, "positions": [], "orders": [], "fills": [], "last_updated": 0}

    def _write_state(self, state: dict[str, Any]):
        """Write the state to the store."""
        state["last_updated"] = int(time.time() * 1000)
        with open(self.store_path, "w") as f:
            json.dump(state, f, indent=2)

    def update_balance(self, currency: str, total: float, available: float):
        """Update balance information."""
        state = self._read_state()
        state["balances"][currency] = {"total": total, "available": available}
        self._write_state(state)

    def update_position(
        self, symbol: str, side: str, size: float, entry_price: float, unrealized_pnl: float
    ):
        """Update position information."""
        state = self._read_state()

        # Remove existing position for the symbol
        state["positions"] = [pos for pos in state["positions"] if pos["symbol"] != symbol]

        # Add new position if size is non-zero
        if size != 0:
            state["positions"].append(
                {
                    "symbol": symbol,
                    "side": side,
                    "size": size,
                    "entry_price": entry_price,
                    "unrealized_pnl": unrealized_pnl,
                }
            )

        self._write_state(state)

    def add_order(self, order: dict[str, Any]):
        """Add or update an order."""
        state = self._read_state()

        # Check if order already exists
        order_id = order.get("id")
        client_order_id = order.get("clientOrderId")

        # Remove existing order with same id or client_order_id
        new_orders = []
        for existing_order in state["orders"]:
            if (
                existing_order.get("id") != order_id
                and existing_order.get("clientOrderId") != client_order_id
            ):
                new_orders.append(existing_order)

        # Add the new order
        new_orders.append(order)
        state["orders"] = new_orders

        self._write_state(state)

    def add_fill(self, fill: dict[str, Any]):
        """Add a fill record."""
        state = self._read_state()
        state["fills"].append(fill)
        # Keep only last 100 fills for performance
        if len(state["fills"]) > 100:
            state["fills"] = state["fills"][-100:]
        self._write_state(state)

    def get_snapshot(
        self, symbols: list[str] | None = None, now_ts: int | None = None
    ) -> LocalSnapshot:
        """
        Get a snapshot of the current local state.

        Args:
            symbols: List of symbols to filter positions and orders (optional)
            now_ts: Current timestamp in milliseconds (optional, defaults to now)

        Returns:
            LocalSnapshot: The local state snapshot
        """
        state = self._read_state()
        now_ts = now_ts or int(time.time() * 1000)

        # Build balances
        balances = {}
        for currency, bal_data in state["balances"].items():
            balances[currency] = Balance(
                total=float(bal_data.get("total", 0.0)),
                available=float(bal_data.get("available", 0.0)),
                currency=currency,
            )

        # If no balances, add default USDT balance
        if not balances:
            balances["USDT"] = Balance(total=0.0, available=0.0, currency="USDT")

        # Build positions
        positions = []
        for pos_data in state["positions"]:
            if symbols and pos_data["symbol"] not in symbols:
                continue
            positions.append(
                Position(
                    symbol=pos_data["symbol"],
                    side=pos_data["side"],
                    size=float(pos_data["size"]),
                    entry_price=float(pos_data["entry_price"]),
                    unrealized_pnl=float(pos_data["unrealized_pnl"]),
                )
            )

        # Build open orders
        open_orders = []
        for order_data in state["orders"]:
            if symbols and order_data["symbol"] not in symbols:
                continue
            # Only include open orders
            if order_data.get("status", "").upper() not in ["CLOSED", "CANCELED", "FILLED"]:
                open_orders.append(
                    Order(
                        id=order_data["id"],
                        client_order_id=order_data.get("clientOrderId"),
                        symbol=order_data["symbol"],
                        side=order_data["side"].upper(),
                        type=order_data["type"].upper(),
                        price=float(order_data["price"]),
                        amount=float(order_data["amount"]),
                        filled=float(order_data.get("filled", 0.0)),
                        status=order_data["status"].upper(),
                    )
                )

        # Build recent fills
        recent_fills = []
        for fill_data in state["fills"]:
            if symbols and fill_data["symbol"] not in symbols:
                continue
            recent_fills.append(
                Fill(
                    id=fill_data["id"],
                    order_id=fill_data["order_id"],
                    symbol=fill_data["symbol"],
                    side=fill_data["side"].upper(),
                    price=float(fill_data["price"]),
                    amount=float(fill_data["amount"]),
                    timestamp=int(fill_data["timestamp"]),
                )
            )

        # Sort fills by timestamp descending
        recent_fills.sort(key=lambda x: x.timestamp, reverse=True)

        # Create snapshot meta
        meta = SnapshotMeta(timestamp=now_ts, symbols=symbols or [], source="local_state_store")

        return LocalSnapshot(
            balances=balances,
            positions=positions,
            open_orders=open_orders,
            recent_fills=recent_fills,
            meta=meta,
        )


def get_local_snapshot(
    db_or_store: LocalStateStore | Any, symbols: list[str] | None = None, now_ts: int | None = None
) -> LocalSnapshot:
    """
    Unified interface to get local state snapshot.

    Args:
        db_or_store: Either a LocalStateStore instance or a database connection
        symbols: List of symbols to filter (optional)
        now_ts: Current timestamp in milliseconds (optional)

    Returns:
        LocalSnapshot: The local state snapshot
    """
    # If db_or_store is already a LocalStateStore instance, use it directly
    if isinstance(db_or_store, LocalStateStore):
        return db_or_store.get_snapshot(symbols, now_ts)

    # Otherwise, create a new LocalStateStore instance (default file-based store)
    # This provides a fallback if no database is available
    store = LocalStateStore()
    return store.get_snapshot(symbols, now_ts)


def create_default_state_store() -> LocalStateStore:
    """
    Create a default local state store instance.

    Returns:
        LocalStateStore: Default state store instance
    """
    return LocalStateStore()
