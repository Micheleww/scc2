#!/usr/bin/env python3
"""
Strategy Package Builder

Generates deployable strategy packages with:
- Strategy code and parameters
- Dependencies
- manifest.json (strategy_version/factor_version/config_hash)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.quantsys.strategy.strategy_interface import StrategyRegistry, StrategySpec
from src.quantsys.strategy.strategy_library import StrategyLibrary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            f"logs/strategy_package_builder_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("strategy_package_builder")


@dataclass
class StrategyPackageConfig:
    """Strategy package configuration."""

    strategy_code: str
    strategy_version: str
    factor_version: str
    config_hash: str
    include_dependencies: bool = True
    include_parameters: bool = True
    include_source_code: bool = True


@dataclass
class StrategyManifest:
    """Strategy package manifest."""

    package_name: str
    strategy_code: str
    strategy_version: str
    factor_version: str
    config_hash: str
    created_at: str
    dependencies: list[str]
    parameters: dict[str, Any]
    files: list[str]
    package_size: int


class StrategyPackageBuilder:
    """
    Strategy package builder.

    Generates deployable strategy packages with manifest.json
    that includes strategy code, parameters, and dependencies.
    """

    def __init__(self, output_dir: Path | None = None):
        """
        Initialize package builder.

        Args:
            output_dir: Output directory for packages (default: packages/strategies)
        """
        self.output_dir = output_dir or Path("packages/strategies")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize strategy library
        self.strategy_lib = StrategyLibrary()
        self.strategy_registry = StrategyRegistry()

        logger.info("Strategy Package Builder initialized")

    def _calculate_config_hash(self, config: dict[str, Any]) -> str:
        """
        Calculate hash of strategy configuration.

        Args:
            config: Strategy configuration dictionary

        Returns:
            str: SHA256 hash (first 16 characters)
        """
        config_str = json.dumps(config, sort_keys=True, ensure_ascii=False)
        hash_obj = hashlib.sha256(config_str.encode("utf-8"))
        return hash_obj.hexdigest()[:16]

    def _generate_package_manifest(
        self, strategy_spec: StrategySpec, config: dict[str, Any], package_files: list[str]
    ) -> StrategyManifest:
        """
        Generate package manifest.

        Args:
            strategy_spec: Strategy specification
            config: Strategy configuration
            package_files: List of files in package

        Returns:
            StrategyManifest: Package manifest
        """
        # Get dependencies
        dependencies = strategy_spec.dependencies if hasattr(strategy_spec, "dependencies") else []

        # Get factor dependencies
        factor_deps = strategy_spec.factors if hasattr(strategy_spec, "factors") else []

        # Calculate config hash
        config_hash = self._calculate_config_hash(config)

        # Calculate package size
        package_size = sum(
            (self.output_dir / f).stat().st_size if (self.output_dir / f).exists() else 0
            for f in package_files
        )

        manifest = StrategyManifest(
            package_name=f"{strategy_spec.code}_v{strategy_spec.version}",
            strategy_code=strategy_spec.code,
            strategy_version=strategy_spec.version,
            factor_version="1.0.0",  # Default factor version
            config_hash=config_hash,
            created_at=datetime.now().isoformat(),
            dependencies=dependencies + factor_deps,
            parameters=config,
            files=package_files,
            package_size=package_size,
        )

        return manifest

    def _create_package_directory(self, strategy_code: str) -> Path:
        """
        Create package directory for a strategy.

        Args:
            strategy_code: Strategy code

        Returns:
            Path: Package directory path
        """
        package_dir = self.output_dir / strategy_code
        package_dir.mkdir(exist_ok=True)
        return package_dir

    def _copy_strategy_code(self, package_dir: Path, strategy_code: str) -> list[str]:
        """
        Copy strategy code to package directory.

        Args:
            package_dir: Package directory
            strategy_code: Strategy code

        Returns:
            List[str]: List of copied files
        """
        copied_files = []

        # Find strategy source files
        strategy_files = [
            f"src/quantsys/strategy/{strategy_code}.py",
            f"src/quantsys/strategy/{strategy_code}_config.json",
        ]

        for file_path in strategy_files:
            src_file = Path(file_path)
            if src_file.exists():
                dst_file = package_dir / src_file.name
                shutil.copy2(src_file, dst_file)
                copied_files.append(src_file.name)
                logger.info(f"Copied: {src_file} -> {dst_file}")

        return copied_files

    def _generate_config_file(
        self, package_dir: Path, strategy_spec: StrategySpec
    ) -> dict[str, Any]:
        """
        Generate configuration file for strategy.

        Args:
            package_dir: Package directory
            strategy_spec: Strategy specification

        Returns:
            Dict[str, Any]: Strategy configuration
        """
        config = {
            "strategy_code": strategy_spec.code,
            "strategy_name": strategy_spec.name,
            "strategy_version": strategy_spec.version,
            "type": strategy_spec.type,
            "description": strategy_spec.description,
            "factors": strategy_spec.factors if hasattr(strategy_spec, "factors") else [],
            "frequency": strategy_spec.frequency,
            "window": strategy_spec.window,
            "entry_rules": strategy_spec.entry_rules
            if hasattr(strategy_spec, "entry_rules")
            else {},
            "exit_rules": strategy_spec.exit_rules if hasattr(strategy_spec, "exit_rules") else {},
            "risk_management": strategy_spec.risk_management
            if hasattr(strategy_spec, "risk_management")
            else {},
            "order_config": strategy_spec.order_config
            if hasattr(strategy_spec, "order_config")
            else {},
            "params_schema": strategy_spec.params_schema
            if hasattr(strategy_spec, "params_schema")
            else {},
            "output_type": strategy_spec.output_type
            if hasattr(strategy_spec, "output_type")
            else "target_position",
        }

        # Save config to file
        config_file = package_dir / "config.json"
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        logger.info(f"Generated config file: {config_file}")

        return config

    def _generate_requirements_file(self, package_dir: Path, dependencies: list[str]) -> None:
        """
        Generate requirements.txt file for strategy dependencies.

        Args:
            package_dir: Package directory
            dependencies: List of dependencies
        """
        if not dependencies:
            return

        requirements_file = package_dir / "requirements.txt"

        # Generate requirements content
        requirements = [
            "# Strategy Package Requirements",
            f"# Generated: {datetime.now().isoformat()}",
            "",
            "# Internal dependencies (managed by system)",
            *[f"# {dep}" for dep in dependencies],
            "",
            "# System dependencies (do not modify)",
            "pandas>=1.3.0",
            "numpy>=1.20.0",
            "plotly>=5.0.0",
        ]

        with open(requirements_file, "w", encoding="utf-8") as f:
            f.write("\n".join(requirements))

        logger.info(f"Generated requirements file: {requirements_file}")

    def _create_package_zip(self, package_dir: Path, strategy_code: str) -> Path:
        """
        Create ZIP archive of the package.

        Args:
            package_dir: Package directory
            strategy_code: Strategy code

        Returns:
            Path: Path to ZIP file
        """
        zip_filename = f"{strategy_code}_package.zip"
        zip_path = self.output_dir / zip_filename

        # Create ZIP file
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in package_dir.rglob("*"):
                if file_path.is_file():
                    zipf.write(file_path, file_path.name)
                    logger.info(f"Added to ZIP: {file_path.name}")

        logger.info(f"Created package ZIP: {zip_path}")

        return zip_path

    def build_package(
        self, strategy_code: str, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Build a strategy package.

        Args:
            strategy_code: Strategy code to package
            config: Optional configuration (uses default from registry)

        Returns:
            Dict[str, Any]: Package build result
        """
        logger.info(f"Building package for strategy: {strategy_code}")

        try:
            # Get strategy spec from registry
            strategy_spec = self.strategy_registry.get_spec(strategy_code)

            # Create package directory
            package_dir = self._create_package_directory(strategy_code)

            # Generate or use provided config
            if config is None:
                config = self._generate_config_file(package_dir, strategy_spec)
            else:
                config = config
                # Save config to file
                config_file = package_dir / "config.json"
                with open(config_file, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)

            # Copy strategy code
            code_files = self._copy_strategy_code(package_dir, strategy_code)

            # Generate requirements file
            dependencies = (
                strategy_spec.dependencies if hasattr(strategy_spec, "dependencies") else []
            )
            self._generate_requirements_file(package_dir, dependencies)

            # Generate manifest
            package_files = code_files + ["config.json", "requirements.txt"]
            manifest = self._generate_package_manifest(strategy_spec, config, package_files)

            # Save manifest to file
            manifest_file = package_dir / "manifest.json"
            with open(manifest_file, "w", encoding="utf-8") as f:
                json.dump(asdict(manifest), f, indent=2, ensure_ascii=False)

            package_files.append("manifest.json")

            # Create ZIP package
            zip_path = self._create_package_zip(package_dir, strategy_code)

            logger.info(f"Package built successfully: {zip_path}")

            return {
                "success": True,
                "strategy_code": strategy_code,
                "package_dir": str(package_dir),
                "zip_file": str(zip_path),
                "manifest": asdict(manifest),
                "files": package_files,
            }

        except Exception as e:
            logger.error(f"Failed to build package for {strategy_code}: {e}")
            return {"success": False, "strategy_code": strategy_code, "error": str(e)}

    def build_all_packages(self) -> list[dict[str, Any]]:
        """
        Build packages for all registered strategies.

        Returns:
            List[Dict[str, Any]]: List of build results
        """
        logger.info("Building packages for all registered strategies...")

        results = []
        registered_strategies = self.strategy_registry.list_registered()

        for strategy_code in registered_strategies:
            result = self.build_package(strategy_code)
            results.append(result)

        logger.info(f"Built {len(results)} packages")

        return results


def load_config(config_path: str) -> StrategyPackageConfig:
    """
    Load package builder configuration from file.

    Args:
        config_path: Path to configuration file

    Returns:
        StrategyPackageConfig: Loaded configuration
    """
    with open(config_path) as f:
        config_data = json.load(f)

    return StrategyPackageConfig(**config_data)


def main():
    """Main entry point."""
    # Load configuration
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/package_builder.json"

    try:
        config = load_config(config_path)
        logger.info(f"Configuration loaded from: {config_path}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        logger.info("Using default configuration")
        config = StrategyPackageConfig(
            strategy_code="trend_following",
            strategy_version="1.0.0",
            factor_version="1.0.0",
            config_hash="",
        )

    # Create package builder
    builder = StrategyPackageBuilder()

    # Build package for specified strategy or all strategies
    if config.strategy_code:
        results = [builder.build_package(config.strategy_code)]
    else:
        results = builder.build_all_packages()

    # Generate summary
    success_count = sum(1 for r in results if r.get("success", False))
    total_count = len(results)

    logger.info("\n=== Package Build Summary ===")
    logger.info(f"Total packages: {total_count}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {total_count - success_count}")

    # Return exit code
    return 0 if success_count == total_count else 1


if __name__ == "__main__":
    sys.exit(main())
