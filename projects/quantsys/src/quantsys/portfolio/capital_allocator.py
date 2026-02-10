#!/usr/bin/env python3
"""
Capital Allocator

Allocates notional based on strategy weights and risk budget.
Supports dynamic adjustment and limits (per strategy/per symbol/total leverage).
Outputs allocation snapshots.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            f"logs/capital_allocator_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("capital_allocator")


@dataclass
class AllocationLimits:
    """Allocation limits configuration."""

    max_leverage: float = 1.0
    max_per_strategy: float = 1.0
    max_per_symbol: float = 1.0
    max_total_notional: float = float("inf")


@dataclass
class StrategyAllocation:
    """Strategy allocation details."""

    strategy_code: str
    weight: float
    notional: float
    leverage: float
    symbols: dict[str, float] = field(default_factory=dict)


@dataclass
class AllocationSnapshot:
    """Allocation snapshot."""

    timestamp: str
    total_capital: float
    total_notional: float
    total_leverage: float
    strategies: list[dict[str, Any]]
    symbols: dict[str, float]
    limits: dict[str, float]
    allocation_hash: str


class CapitalAllocator:
    """
    Capital allocator for strategy portfolio.

    Allocates notional based on strategy weights and risk budget.
    Supports dynamic adjustment and limits.
    """

    def __init__(self, total_capital: float, limits: AllocationLimits | None = None):
        """
        Initialize capital allocator.

        Args:
            total_capital: Total available capital
            limits: Allocation limits configuration
        """
        self.total_capital = total_capital
        self.limits = limits or AllocationLimits()
        self.strategy_weights: dict[str, float] = {}
        self.strategy_risk_budgets: dict[str, float] = {}
        self.current_allocations: dict[str, StrategyAllocation] = {}
        self.allocation_history: list[AllocationSnapshot] = []

        logger.info(f"Capital Allocator initialized with total_capital={total_capital}")
        logger.info(
            f"Limits: max_leverage={self.limits.max_leverage}, "
            f"max_per_strategy={self.limits.max_per_strategy}, "
            f"max_per_symbol={self.limits.max_per_symbol}"
        )

    def set_strategy_weights(self, weights: dict[str, float]):
        """
        Set strategy weights.

        Args:
            weights: Dictionary of strategy_code -> weight (0-1)
        """
        total_weight = sum(weights.values())
        if abs(total_weight - 1.0) > 1e-6:
            logger.warning(f"Strategy weights sum to {total_weight}, normalizing to 1.0")
            weights = {k: v / total_weight for k, v in weights.items()}

        self.strategy_weights = weights
        logger.info(f"Strategy weights set: {weights}")

    def set_strategy_risk_budgets(self, risk_budgets: dict[str, float]):
        """
        Set strategy risk budgets.

        Args:
            risk_budgets: Dictionary of strategy_code -> risk_budget (0-1)
        """
        self.strategy_risk_budgets = risk_budgets
        logger.info(f"Strategy risk budgets set: {risk_budgets}")

    def _calculate_allocation_hash(self, allocations: dict[str, StrategyAllocation]) -> str:
        """
        Calculate hash of current allocation.

        Args:
            allocations: Current strategy allocations

        Returns:
            str: SHA256 hash (first 16 characters)
        """
        allocation_data = {
            code: {
                "weight": alloc.weight,
                "notional": alloc.notional,
                "leverage": alloc.leverage,
                "symbols": alloc.symbols,
            }
            for code, alloc in allocations.items()
        }
        allocation_str = json.dumps(allocation_data, sort_keys=True, ensure_ascii=False)
        hash_obj = hashlib.sha256(allocation_str.encode("utf-8"))
        return hash_obj.hexdigest()[:16]

    def _apply_limits(
        self, allocations: dict[str, StrategyAllocation]
    ) -> dict[str, StrategyAllocation]:
        """
        Apply allocation limits.

        Args:
            allocations: Strategy allocations before limits

        Returns:
            Dict[str, StrategyAllocation]: Allocations after limits
        """
        total_notional = sum(alloc.notional for alloc in allocations.values())
        total_leverage = total_notional / self.total_capital if self.total_capital > 0 else 0

        # Check total leverage limit
        if total_leverage > self.limits.max_leverage:
            logger.warning(
                f"Total leverage {total_leverage} exceeds max {self.limits.max_leverage}, scaling down"
            )
            scale_factor = self.limits.max_leverage / total_leverage
            for alloc in allocations.values():
                alloc.notional *= scale_factor
                alloc.leverage *= scale_factor

        # Check per-strategy limit
        for code, alloc in allocations.items():
            if alloc.notional > self.limits.max_per_strategy:
                logger.warning(
                    f"Strategy {code} notional {alloc.notional} exceeds max {self.limits.max_per_strategy}"
                )
                # Scale down symbol allocations proportionally to maintain distribution
                if alloc.symbols:
                    scale_factor = self.limits.max_per_strategy / alloc.notional
                    alloc.symbols = {
                        symbol: notional * scale_factor
                        for symbol, notional in alloc.symbols.items()
                    }
                    alloc.notional = sum(alloc.symbols.values())
                else:
                    alloc.notional = self.limits.max_per_strategy
                if alloc.weight > 0:
                    alloc.leverage = alloc.notional / (alloc.weight * self.total_capital)
                else:
                    alloc.leverage = 0

        # Check per-symbol limit
        symbol_notional: dict[str, float] = {}
        for alloc in allocations.values():
            for symbol, notional in alloc.symbols.items():
                symbol_notional[symbol] = symbol_notional.get(symbol, 0) + notional

        # Reduce allocations for symbols exceeding limit
        for symbol, notional in symbol_notional.items():
            if notional > self.limits.max_per_symbol:
                logger.warning(
                    f"Symbol {symbol} notional {notional} exceeds max {self.limits.max_per_symbol}"
                )
                scale = self.limits.max_per_symbol / notional
                # Reduce allocations for this symbol
                for alloc in allocations.values():
                    if symbol in alloc.symbols:
                        alloc.symbols[symbol] *= scale

        # Recalculate strategy notionals after symbol adjustment (only if symbols exist)
        for alloc in allocations.values():
            if alloc.symbols:
                alloc.notional = sum(alloc.symbols.values())
                if alloc.weight > 0:
                    alloc.leverage = alloc.notional / (alloc.weight * self.total_capital)
                else:
                    alloc.leverage = 0

        return allocations

    def allocate_by_weight(self) -> dict[str, StrategyAllocation]:
        """
        Allocate capital by strategy weights.

        Returns:
            Dict[str, StrategyAllocation]: Strategy allocations
        """
        allocations = {}

        for strategy_code, weight in self.strategy_weights.items():
            base_notional = weight * self.total_capital
            leverage = 1.0

            allocations[strategy_code] = StrategyAllocation(
                strategy_code=strategy_code,
                weight=weight,
                notional=base_notional,
                leverage=leverage,
                symbols={},
            )

        # Apply limits
        allocations = self._apply_limits(allocations)

        logger.info(
            f"Allocated by weight: {[(code, alloc.notional) for code, alloc in allocations.items()]}"
        )
        return allocations

    def allocate_by_risk_budget(self) -> dict[str, StrategyAllocation]:
        """
        Allocate capital by risk budget.

        Returns:
            Dict[str, StrategyAllocation]: Strategy allocations
        """
        allocations = {}

        total_risk_budget = sum(self.strategy_risk_budgets.values())

        for strategy_code, risk_budget in self.strategy_risk_budgets.items():
            if total_risk_budget > 0:
                weight = risk_budget / total_risk_budget
            else:
                weight = 1.0 / len(self.strategy_risk_budgets) if self.strategy_risk_budgets else 0

            base_notional = weight * self.total_capital
            leverage = 1.0

            allocations[strategy_code] = StrategyAllocation(
                strategy_code=strategy_code,
                weight=weight,
                notional=base_notional,
                leverage=leverage,
                symbols={},
            )

        # Apply limits
        allocations = self._apply_limits(allocations)

        logger.info(
            f"Allocated by risk budget: {[(code, alloc.notional) for code, alloc in allocations.items()]}"
        )
        return allocations

    def allocate(self, method: str = "weight") -> dict[str, StrategyAllocation]:
        """
        Allocate capital using specified method.

        Args:
            method: Allocation method ("weight" or "risk_budget")

        Returns:
            Dict[str, StrategyAllocation]: Strategy allocations
        """
        if method == "weight":
            allocations = self.allocate_by_weight()
        elif method == "risk_budget":
            allocations = self.allocate_by_risk_budget()
        else:
            raise ValueError(f"Unknown allocation method: {method}")

        self.current_allocations = allocations
        return allocations

    def adjust_allocation(self, strategy_code: str, adjustment_factor: float):
        """
        Dynamically adjust allocation for a strategy.

        Args:
            strategy_code: Strategy to adjust
            adjustment_factor: Factor to multiply allocation by (e.g., 1.1 for +10%)
        """
        if strategy_code not in self.current_allocations:
            logger.warning(f"Strategy {strategy_code} not found in current allocations")
            return

        old_notional = self.current_allocations[strategy_code].notional
        new_notional = old_notional * adjustment_factor

        self.current_allocations[strategy_code].notional = new_notional
        self.current_allocations[strategy_code].leverage = (
            new_notional / (self.current_allocations[strategy_code].weight * self.total_capital)
            if self.current_allocations[strategy_code].weight > 0
            else 0
        )

        logger.info(f"Adjusted {strategy_code} allocation: {old_notional} -> {new_notional}")

    def create_snapshot(self) -> AllocationSnapshot:
        """
        Create allocation snapshot.

        Returns:
            AllocationSnapshot: Current allocation snapshot
        """
        total_notional = sum(alloc.notional for alloc in self.current_allocations.values())
        total_leverage = total_notional / self.total_capital if self.total_capital > 0 else 0

        # Aggregate by symbol
        symbol_notional: dict[str, float] = {}
        for alloc in self.current_allocations.values():
            for symbol, notional in alloc.symbols.items():
                symbol_notional[symbol] = symbol_notional.get(symbol, 0) + notional

        # Convert allocations to dict
        strategies = [
            {
                "strategy_code": alloc.strategy_code,
                "weight": alloc.weight,
                "notional": alloc.notional,
                "leverage": alloc.leverage,
                "symbols": alloc.symbols,
            }
            for alloc in self.current_allocations.values()
        ]

        # Calculate allocation hash
        allocation_hash = self._calculate_allocation_hash(self.current_allocations)

        snapshot = AllocationSnapshot(
            timestamp=datetime.now().isoformat(),
            total_capital=self.total_capital,
            total_notional=total_notional,
            total_leverage=total_leverage,
            strategies=strategies,
            symbols=symbol_notional,
            limits={
                "max_leverage": self.limits.max_leverage,
                "max_per_strategy": self.limits.max_per_strategy,
                "max_per_symbol": self.limits.max_per_symbol,
                "max_total_notional": self.limits.max_total_notional,
            },
            allocation_hash=allocation_hash,
        )

        self.allocation_history.append(snapshot)
        return snapshot

    def save_snapshot(self, snapshot: AllocationSnapshot, file_path: str):
        """
        Save allocation snapshot to file.

        Args:
            snapshot: Allocation snapshot to save
            file_path: Path to save snapshot
        """
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(asdict(snapshot), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved allocation snapshot: {file_path}")

    def load_snapshot(self, file_path: str) -> AllocationSnapshot:
        """
        Load allocation snapshot from file.

        Args:
            file_path: Path to load snapshot from

        Returns:
            AllocationSnapshot: Loaded snapshot
        """
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        return AllocationSnapshot(**data)


def main():
    """Main entry point for testing."""
    allocator = CapitalAllocator(
        total_capital=100000.0,
        limits=AllocationLimits(max_leverage=3.0, max_per_strategy=50000.0, max_per_symbol=30000.0),
    )

    # Set strategy weights
    allocator.set_strategy_weights({"trend_following": 0.4, "mean_reversion": 0.3, "momentum": 0.3})

    # Allocate by weight
    allocations = allocator.allocate(method="weight")

    # Add symbol allocations
    for alloc in allocations.values():
        if alloc.strategy_code == "trend_following":
            alloc.symbols = {"BTC/USDT": alloc.notional * 0.6, "ETH/USDT": alloc.notional * 0.4}
        elif alloc.strategy_code == "mean_reversion":
            alloc.symbols = {"ETH/USDT": alloc.notional}
        elif alloc.strategy_code == "momentum":
            alloc.symbols = {"BTC/USDT": alloc.notional * 0.5, "SOL/USDT": alloc.notional * 0.5}

    # Create and save snapshot
    snapshot = allocator.create_snapshot()
    allocator.save_snapshot(snapshot, "reports/capital_allocation_snapshot.json")

    print(f"Total capital: {snapshot.total_capital}")
    print(f"Total notional: {snapshot.total_notional}")
    print(f"Total leverage: {snapshot.total_leverage}")
    print(f"Allocation hash: {snapshot.allocation_hash}")


if __name__ == "__main__":
    main()
