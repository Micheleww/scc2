"""
Factor registry management and validation with FactorSpec.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class UnregisteredFactorError(ValueError):
    pass


class InvalidFactorSpecError(ValueError):
    pass


@dataclass(frozen=True)
class FactorSpec:
    """
    Factor specification with complete metadata.

    Attributes:
        code: Factor unique identifier
        name: Human-readable name
        version: Version string (semver format recommended)
        type: Factor category (price, volume, volatility, etc.)
        description: Brief description
        dependencies: List of factor codes this factor depends on
        frequency: Data frequency (1m, 5m, 1h, 1d, etc.)
        window: Calculation window size
        lag: Availability lag in periods
        availability_lag: int  # Compatibility field for FactorMeta
        output_columns: List of output column names
        missing_strategy: How to handle missing data (drop, fill, etc.)
        standardized: Whether the factor is standardized
        availability: Whether the factor is available for use
        input_fields: List of input data fields required
        output_range: Expected output value range
    """

    code: str
    name: str
    version: str
    type: str
    description: str
    dependencies: list[str]
    frequency: str
    window: str
    lag: int
    availability_lag: int  # Compatibility field
    output_columns: list[str]
    missing_strategy: str
    standardized: bool
    availability: bool
    input_fields: list[str]
    output_range: str


# Compatibility alias for FactorMeta
FactorMeta = FactorSpec


class FactorRegistry:
    """
    Factor registry for managing FactorSpec instances.
    """

    def __init__(self, registry_path: str | None = None) -> None:
        """
        Initialize factor registry.

        Args:
            registry_path: Path to registry JSON file, optional
        """
        self._defaults = {
            "version": "1.0.0",
            "description": "",
            "dependencies": [],
            "frequency": "1d",
            "window": "20",
            "lag": 0,
            "availability_lag": 0,
            "output_columns": [],
            "missing_strategy": "drop",
            "standardized": False,
            "availability": True,
            "input_fields": [],
            "output_range": "[-inf, inf]",
        }
        self._factors: dict[str, dict[str, Any]] = {}
        self._registry_path: Path | None = None

        if registry_path:
            self._registry_path = Path(registry_path)
            self.load_from_file(self._registry_path)

    def generate_factor_version(
        self,
        spec: FactorSpec,
        code_hash: str,
        data_version: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Generate factor version based on FactorSpec, code hash, data version, and parameters.

        Args:
            spec: Factor specification
            code_hash: Hash of the factor calculation code
            data_version: Input data version
            params: Additional parameters (optional)

        Returns:
            str: Factor version hash (first 16 characters of SHA256)
        """
        # Convert FactorSpec to a reproducible string
        spec_dict = asdict(spec)
        # Sort keys to ensure consistent order
        spec_str = json.dumps(spec_dict, sort_keys=True, ensure_ascii=False)

        # Convert params to a reproducible string
        params_str = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)

        # Create combined string for hashing
        combined = f"{spec_str}{code_hash}{data_version}{params_str}"

        # Generate SHA256 hash and take first 16 characters
        hash_obj = hashlib.sha256(combined.encode("utf-8"))
        factor_version = hash_obj.hexdigest()[:16]

        return factor_version

    def save_factor_metadata(
        self,
        code: str,
        spec: FactorSpec,
        factor_version: str,
        data_version: str,
        code_hash: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        """
        Save factor metadata to JSON file.

        Args:
            code: Factor code
            spec: Factor specification
            factor_version: Generated factor version
            data_version: Input data version
            code_hash: Code hash used in version generation
            params: Additional parameters

        Returns:
            str: Path to the saved metadata file
        """
        # Create metadata dictionary
        metadata = {
            "factor_code": code,
            "factor_version": factor_version,
            "data_version": data_version,
            "code_hash": code_hash,
            "factor_spec": asdict(spec),
            "params": params or {},
            "generated_at": str(Path().resolve()),
            "timestamp": datetime.now().isoformat(),
        }

        # Ensure reports directory exists
        reports_dir = Path("reports/factors")
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata to file
        metadata_path = reports_dir / f"{code}_{factor_version}_metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # Also update factor registry with version info
        if code in self._factors:
            self._factors[code].setdefault("versions", []).append(
                {
                    "version": factor_version,
                    "data_version": data_version,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            # Save registry if path is set
            if self._registry_path:
                self.save_to_file()

        return str(metadata_path)

    def calculate_code_hash(self, factor_code: str) -> str:
        """
        Calculate hash of the factor implementation code.

        Args:
            factor_code: Factor code

        Returns:
            str: Hash of the factor code (first 16 characters of SHA256)
        """
        # For simplicity, we'll generate a hash based on the factor code and registry info
        # In a real implementation, this would read the actual factor implementation file
        factor_info = (
            f"{factor_code}{json.dumps(self._factors.get(factor_code, {}), sort_keys=True)}"
        )
        hash_obj = hashlib.sha256(factor_info.encode("utf-8"))
        return hash_obj.hexdigest()[:16]

    def load_from_file(self, path: Path) -> None:
        """
        Load factor registry from JSON file.

        Args:
            path: Path to registry JSON file

        Raises:
            FileNotFoundError: If registry file not found
            json.JSONDecodeError: If registry file is invalid JSON
        """
        if not path.exists():
            raise FileNotFoundError(f"factor registry not found: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        self._defaults.update(data.get("defaults", {}))
        self._factors = data.get("factors", {})

    def save_to_file(self, path: Path | None = None) -> None:
        """
        Save factor registry to JSON file.

        Args:
            path: Path to save registry, uses initialized path if None

        Raises:
            ValueError: If no path provided and no initialized path
        """
        save_path = path or self._registry_path
        if not save_path:
            raise ValueError("No registry path specified")

        data = {"defaults": self._defaults, "factors": self._factors}
        save_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FactorRegistry:
        """
        Create registry from dictionary.

        Args:
            data: Registry data

        Returns:
            FactorRegistry instance
        """
        obj = cls()
        obj._defaults.update(data.get("defaults", {}))
        obj._factors = data.get("factors", {})
        return obj

    def to_dict(self) -> dict[str, Any]:
        """
        Convert registry to dictionary.

        Returns:
            Registry data as dictionary
        """
        return {"defaults": self._defaults, "factors": self._factors}

    def list_registered(self) -> list[str]:
        """
        List all registered factor codes.

        Returns:
            Sorted list of factor codes
        """
        return sorted(self._factors.keys())

    def get_spec(self, code: str) -> FactorSpec:
        """
        Get FactorSpec for a factor.

        Args:
            code: Factor code

        Returns:
            FactorSpec instance

        Raises:
            UnregisteredFactorError: If factor not registered
        """
        if code not in self._factors:
            raise UnregisteredFactorError(f"factor not registered: {code}")
        raw = {**self._defaults, **self._factors[code]}

        # Validate required fields
        required_fields = ["type"]
        for field in required_fields:
            if field not in raw or not raw[field]:
                raise InvalidFactorSpecError(f"Missing required field {field} for factor {code}")

        # Provide sensible defaults for missing optional fields
        if "name" not in raw:
            raw["name"] = code
        if "version" not in raw:
            raw["version"] = "1.0.0"

        return FactorSpec(
            code=code,
            name=str(raw["name"]),
            version=str(raw["version"]),
            type=str(raw["type"]),
            description=str(raw.get("description", "")),
            dependencies=list(raw.get("dependencies", [])),
            frequency=str(raw["frequency"]),
            window=str(raw["window"]),
            lag=int(raw["lag"]),
            availability_lag=int(
                raw.get("availability_lag", raw["lag"])
            ),  # Use lag as default for compatibility
            output_columns=list(raw.get("output_columns", [])),
            missing_strategy=str(raw["missing_strategy"]),
            standardized=bool(raw["standardized"]),
            availability=bool(raw["availability"]),
            input_fields=list(raw.get("input_fields", [])),
            output_range=str(raw["output_range"]),
        )

    def register_factor(self, spec_data: dict[str, Any]) -> None:
        """
        Register a new factor.

        Args:
            spec_data: Factor specification data

        Raises:
            ValueError: If code not provided
        """
        code = spec_data.get("code")
        if not code:
            raise ValueError("Factor code is required")

        # Remove code from spec_data as it's used as key
        factor_data = spec_data.copy()
        factor_data.pop("code")
        self._factors[code] = factor_data

    def validate(self) -> list[str]:
        """
        Validate all registered factors.

        Returns:
            List of validation error messages
        """
        errors: list[str] = []

        for code in self._factors:
            try:
                spec = self.get_spec(code)

                # Validate dependencies exist
                for dep in spec.dependencies:
                    if dep not in self._factors:
                        errors.append(f"Factor {code} depends on unregistered factor {dep}")

                # Validate output columns
                if not spec.output_columns:
                    errors.append(f"Factor {code} has no output columns specified")

                # Validate version format (simple check)
                version_parts = spec.version.split(".")
                if len(version_parts) < 2:
                    errors.append(f"Invalid version format for factor {code}: {spec.version}")

            except InvalidFactorSpecError as e:
                errors.append(f"Invalid spec for factor {code}: {e}")

        return errors

    def list_available(self) -> list[str]:
        """
        List all available factors.

        Returns:
            List of available factor codes
        """
        available = []
        for code in self._factors:
            try:
                spec = self.get_spec(code)
                if spec.availability:
                    available.append(code)
            except Exception:
                continue
        return sorted(available)

    def get_meta(self, code: str) -> FactorSpec:
        """
        Legacy method for backward compatibility.

        Args:
            code: Factor code

        Returns:
            FactorSpec instance
        """
        logging.warning("get_meta() is deprecated, use get_spec() instead")
        return self.get_spec(code)
