#!/usr/bin/env python3
"""
Strategy specification and unified strategy interface.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class UnregisteredStrategyError(ValueError):
    """Raised when accessing an unregistered strategy."""

    pass


class InvalidStrategySpecError(ValueError):
    """Raised when strategy specification is invalid."""

    pass


@dataclass(frozen=True)
class StrategySpec:
    """
    Strategy specification with complete metadata.

    Attributes:
        code: Strategy unique identifier
        name: Human-readable name
        version: Version string (semver format recommended)
        type: Strategy category (trend, mean_reversion, machine_learning, etc.)
        description: Brief description
        dependencies: List of strategy codes this strategy depends on
        factors: List of factor codes used by this strategy
        frequency: Data frequency (1m, 5m, 1h, 1d, etc.)
        window: Calculation window size
        entry_rules: Entry rules configuration
        exit_rules: Exit rules configuration
        order_config: Order configuration
        params_schema: Parameter validation schema
        availability: Whether the strategy is available for use
        output_type: Output type (action_intent only)
    """

    code: str
    name: str
    version: str
    type: str
    description: str
    dependencies: list[str]
    factors: list[str]
    frequency: str
    window: str
    entry_rules: dict[str, Any]
    exit_rules: dict[str, Any]
    order_config: dict[str, Any]
    params_schema: dict[str, Any]
    availability: bool
    output_type: str


class StrategyRegistry:
    """
    Strategy registry for managing StrategySpec instances.
    """

    def __init__(self, registry_path: str | None = None) -> None:
        """
        Initialize strategy registry.

        Args:
            registry_path: Path to registry JSON file, optional
        """
        self._defaults = {
            "version": "1.0.0",
            "description": "",
            "dependencies": [],
            "factors": [],
            "frequency": "1d",
            "window": "20",
            "entry_rules": {},
            "exit_rules": {},
            "order_config": {"order_type": "market", "slippage": 0.001},
            "params_schema": {},
            "availability": True,
            "output_type": "action_intent",
        }
        self._strategies: dict[str, dict[str, Any]] = {}
        self._registry_path: Path | None = None

        if registry_path:
            self._registry_path = Path(registry_path)
            self.load_from_file(self._registry_path)

    def load_from_file(self, path: Path) -> None:
        """
        Load strategy registry from JSON file.

        Args:
            path: Path to registry JSON file

        Raises:
            FileNotFoundError: If registry file not found
            json.JSONDecodeError: If registry file is invalid JSON
        """
        if not path.exists():
            raise FileNotFoundError(f"strategy registry not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        self._defaults.update(data.get("defaults", {}))
        self._strategies = data.get("strategies", {})

    def save_to_file(self, path: Path | None = None) -> None:
        """
        Save strategy registry to JSON file.

        Args:
            path: Path to save registry, uses initialized path if None

        Raises:
            ValueError: If no path provided and no initialized path
        """
        save_path = path or self._registry_path
        if not save_path:
            raise ValueError("No registry path specified")

        data = {"defaults": self._defaults, "strategies": self._strategies}
        save_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyRegistry:
        """
        Create registry from dictionary.

        Args:
            data: Registry data

        Returns:
            StrategyRegistry instance
        """
        obj = cls()
        obj._defaults.update(data.get("defaults", {}))
        obj._strategies = data.get("strategies", {})
        return obj

    def to_dict(self) -> dict[str, Any]:
        """
        Convert registry to dictionary.

        Returns:
            Registry data as dictionary
        """
        return {"defaults": self._defaults, "strategies": self._strategies}

    def list_registered(self) -> list[str]:
        """
        List all registered strategy codes.

        Returns:
            Sorted list of strategy codes
        """
        return sorted(self._strategies.keys())

    def get_spec(self, code: str) -> StrategySpec:
        """
        Get StrategySpec for a strategy.

        Args:
            code: Strategy code

        Returns:
            StrategySpec instance

        Raises:
            UnregisteredStrategyError: If strategy not registered
        """
        if code not in self._strategies:
            raise UnregisteredStrategyError(f"strategy not registered: {code}")
        raw = {**self._defaults, **self._strategies[code]}

        # Validate required fields
        required_fields = ["name", "version", "type"]
        for field in required_fields:
            if field not in raw or not raw[field]:
                raise InvalidStrategySpecError(
                    f"Missing required field {field} for strategy {code}"
                )

        return StrategySpec(
            code=code,
            name=str(raw["name"]),
            version=str(raw["version"]),
            type=str(raw["type"]),
            description=str(raw.get("description", "")),
            dependencies=list(raw.get("dependencies", [])),
            factors=list(raw.get("factors", [])),
            frequency=str(raw["frequency"]),
            window=str(raw["window"]),
            entry_rules=dict(raw.get("entry_rules", {})),
            exit_rules=dict(raw.get("exit_rules", {})),
            order_config=dict(raw.get("order_config", {})),
            params_schema=dict(raw.get("params_schema", {})),
            availability=bool(raw["availability"]),
            output_type=str(raw["output_type"]),
        )

    def register_strategy(self, spec_data: dict[str, Any]) -> None:
        """
        Register a new strategy.

        Args:
            spec_data: Strategy specification data

        Raises:
            ValueError: If code not provided
        """
        code = spec_data.get("code")
        if not code:
            raise ValueError("Strategy code is required")

        # Remove code from spec_data as it's used as key
        strategy_data = spec_data.copy()
        strategy_data.pop("code")
        self._strategies[code] = strategy_data

    def validate(self) -> list[str]:
        """
        Validate all registered strategies.

        Returns:
            List of validation error messages
        """
        errors: list[str] = []

        for code in self._strategies:
            try:
                spec = self.get_spec(code)

                # Validate dependencies exist
                for dep in spec.dependencies:
                    if dep not in self._strategies:
                        errors.append(f"Strategy {code} depends on unregistered strategy {dep}")

                # Validate output type is supported - only action_intent is allowed per V1.6 constitution
                if spec.output_type != "action_intent":
                    errors.append(
                        f"Invalid output_type for strategy {code}: {spec.output_type}. Only 'action_intent' is allowed per V1.6 constitution."
                    )

            except InvalidStrategySpecError as e:
                errors.append(f"Invalid spec for strategy {code}: {e}")

        return errors

    def list_available(self) -> list[str]:
        """
        List all available strategies.

        Returns:
            List of available strategy codes
        """
        available = []
        for code in self._strategies:
            try:
                spec = self.get_spec(code)
                if spec.availability:
                    available.append(code)
            except Exception:
                continue
        return sorted(available)


class StrategyInterface:
    """
    Unified strategy interface.

    Input: features + availability_mask + context
    Output: target_position or order_intent
    """

    def __init__(self, registry: StrategyRegistry, config: dict[str, Any] | None = None):
        """
        Initialize strategy interface.

        Args:
            registry: Strategy registry instance
            config: Configuration dictionary, optional
        """
        self.registry = registry
        self.config = config or {}
        self._strategies = {}

    def get_strategy(self, code: str) -> Any:
        """
        Get strategy implementation by code.

        Args:
            code: Strategy code

        Returns:
            Strategy implementation
        """
        if code not in self._strategies:
            # In a real implementation, this would load the strategy class
            # For now, we'll just return a dummy implementation
            self._strategies[code] = self._create_dummy_strategy(code)
        return self._strategies[code]

    def _create_dummy_strategy(self, code: str) -> Any:
        """
        Create a dummy strategy implementation for testing.

        Args:
            code: Strategy code

        Returns:
            Dummy strategy implementation
        """
        spec = self.registry.get_spec(code)

        class DummyStrategy:
            """Dummy strategy implementation."""

            def __init__(self, spec: StrategySpec):
                self.spec = spec
                self.code = code

            def execute(
                self,
                features: dict[str, Any],
                availability_mask: dict[str, bool],
                context: dict[str, Any],
            ) -> dict[str, Any]:
                """
                Execute the strategy.

                Args:
                    features: Feature data
                    availability_mask: Availability mask for features
                    context: Additional context

                Returns:
                    Strategy output (action_intent only, per V1.6 constitution)
                """
                # Action Intent implementation according to V1.6 constitution
                return {
                    "action_intent": {
                        "action_type": "enter",  # enter/exit/hold
                        "entry_type": "breakout",  # breakout/pullback/mean/etc
                        "exit_logic": {
                            "type": "time",  # time/price/condition
                            "parameters": {"duration": "1h"},
                        },
                    },
                    "confidence": 0.8,
                    "strategy_code": self.code,
                    "output_type": "action_intent",
                }

        return DummyStrategy(spec)

    def run_strategy(
        self,
        code: str,
        features: dict[str, Any],
        availability_mask: dict[str, bool],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Run a strategy with the given input.

        Args:
            code: Strategy code
            features: Feature data
            availability_mask: Availability mask for features
            context: Additional context

        Returns:
            Strategy output
        """
        strategy = self.get_strategy(code)
        return strategy.execute(features, availability_mask, context)

    def validate_strategy_input(
        self,
        code: str,
        features: dict[str, Any],
        availability_mask: dict[str, bool],
        context: dict[str, Any],
    ) -> bool:
        """
        Validate strategy input.

        Args:
            code: Strategy code
            features: Feature data
            availability_mask: Availability mask for features
            context: Additional context

        Returns:
            True if input is valid, False otherwise
        """
        try:
            spec = self.registry.get_spec(code)

            # Check if required features are available
            for factor in spec.factors:
                if factor in features and not availability_mask.get(factor, True):
                    return False

            return True
        except Exception:
            return False
