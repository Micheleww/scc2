import sys
from typing import Any, TypeVar

from pydantic import ValidationError

T = TypeVar("T")


def validate_config(config_data: dict[str, Any], schema_name: str, fail_fast: bool = True) -> Any:
    """
    Validate configuration data against a schema.

    Args:
        config_data: Configuration data dictionary
        schema_name: Name of the schema class to validate against
        fail_fast: If True, exit on validation error with clear error message

    Returns:
        Validated configuration object

    Raises:
        ValidationError: If validation fails and fail_fast is False
    """
    from .config_schema import MainConfig
    from .data_schema import CandleData, FundingRateData, TradeData
    from .signal_schema import ActionIntent, FreqtradeSignal, SignalIntent

    schema_map = {
        "MainConfig": MainConfig,
        "SignalIntent": SignalIntent,
        "FreqtradeSignal": FreqtradeSignal,
        "ActionIntent": ActionIntent,
        "CandleData": CandleData,
        "TradeData": TradeData,
        "FundingRateData": FundingRateData,
    }

    if schema_name not in schema_map:
        raise ValueError(f"Unknown schema: {schema_name}. Available: {list(schema_map.keys())}")

    schema_class = schema_map[schema_name]

    try:
        return schema_class(**config_data)
    except ValidationError as e:
        error_msg = f"\n{'=' * 80}\n"
        error_msg += f"CONFIG VALIDATION FAILED: {schema_name}\n"
        error_msg += f"{'=' * 80}\n"

        for error in e.errors():
            field_path = " -> ".join(str(loc) for loc in error["loc"])
            error_msg += f"\n❌ Field: {field_path}\n"
            error_msg += f"   Error: {error['msg']}\n"
            error_msg += f"   Input: {error['input']}\n"

        error_msg += f"\n{'=' * 80}\n"
        error_msg += "Please fix the configuration errors and try again.\n"
        error_msg += f"{'=' * 80}\n"

        print(error_msg, file=sys.stderr)

        if fail_fast:
            sys.exit(1)
        else:
            raise


def validate_config_file(config_path: str, schema_name: str, fail_fast: bool = True) -> Any:
    """
    Load and validate a configuration file.

    Args:
        config_path: Path to the configuration file (JSON)
        schema_name: Name of the schema class to validate against
        fail_fast: If True, exit on validation error with clear error message

    Returns:
        Validated configuration object
    """
    import json

    try:
        with open(config_path, encoding="utf-8") as f:
            config_data = json.load(f)
    except FileNotFoundError:
        error_msg = f"Configuration file not found: {config_path}"
        print(error_msg, file=sys.stderr)
        if fail_fast:
            sys.exit(1)
        else:
            raise FileNotFoundError(error_msg)
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON in configuration file: {config_path}\nError: {e}"
        print(error_msg, file=sys.stderr)
        if fail_fast:
            sys.exit(1)
        else:
            raise

    return validate_config(config_data, schema_name, fail_fast)


def validate_signal_intent(signal_path: str, fail_fast: bool = True) -> Any:
    """
    Validate a signal intent file.

    Args:
        signal_path: Path to the signal intent file (JSON)
        fail_fast: If True, exit on validation error with clear error message

    Returns:
        Validated SignalIntent object
    """
    return validate_config_file(signal_path, "SignalIntent", fail_fast)


def validate_freqtrade_signal(signal_path: str, fail_fast: bool = True) -> Any:
    """
    Validate a Freqtrade signal file.

    Args:
        signal_path: Path to the Freqtrade signal file (JSON)
        fail_fast: If True, exit on validation error with clear error message

    Returns:
        Validated FreqtradeSignal object
    """
    return validate_config_file(signal_path, "FreqtradeSignal", fail_fast)
