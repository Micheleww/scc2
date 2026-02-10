# Contracts Runtime

Runtime schema validation for QuantSys configuration, data, signals, and action intents.

## Overview

This module provides Pydantic-based runtime validation schemas for:
- **Config**: System configuration validation
- **Data**: Market data validation (candles, trades, funding rates, order book, open interest)
- **Signal**: Signal intent and action intent validation

## Usage

### Config Validation

```python
from quantsys.contracts_runtime import MainConfig
import json

# Load and validate config
with open('configs/config.json', 'r') as f:
    config_data = json.load(f)

config = MainConfig(**config_data)
```

### Signal Validation

```python
from quantsys.contracts_runtime import SignalIntent

signal = SignalIntent(
    status="OK",
    timestamp="2026-01-12T00:34:57.268560",
    strategy="EthPerpTrendStrategy",
    direction="OPEN_LONG",
    entry_price=2418.45,
    stop_loss=2390.64,
    reason="多头信号: EMA多头排列，ADX=13.64",
    signal={
        "timestamp": "2026-01-12T00:34:57.260846",
        "close": 2418.45,
        "enter_long": True,
        "enter_short": False,
        "exit_long": False,
        "exit_short": False,
        "indicators": {
            "ema_fast": 2434.26,
            "ema_slow": 2422.54,
            "adx": 13.64,
            "atr": 11.13,
            "bb_upper": 0.0,
            "bb_mid": 0.0,
            "bb_lower": 0.0,
            "rsi": 0.0
        }
    }
)
```

### Data Validation

```python
from quantsys.contracts_runtime import CandleData

candle = CandleData(
    ts=1705027200000,
    instId="ETH-USDT-SWAP",
    timeframe="1h",
    source="okx",
    open=2400.0,
    high=2420.0,
    low=2390.0,
    close=2415.0,
    volume=1000.0
)
```

## Schemas

### Config Schemas (`config_schema.py`)

- `SystemConfig`: System-level configuration
- `DatabaseConfig`: Database connection settings
- `DataCollectionConfig`: Data collection parameters
- `RealTimeConfig`: Real-time data settings
- `FactorConfig`: Factor calculation settings
- `StrategyConfig`: Strategy configuration
- `FreqtradeConfig`: Freqtrade integration settings
- `LiveConfig`: Live trading settings
- `DryRunConfig`: Dry run mode settings
- `RiskConfig`: Risk management parameters
- `ReconciliationConfig`: Reconciliation settings
- `BacktestConfig`: Backtest configuration
- `MainConfig`: Main configuration container

### Signal Schemas (`signal_schema.py`)

- `SignalIndicators`: Technical indicators
- `SignalData`: Signal data with indicators
- `SignalIntent`: Complete signal intent
- `FreqtradeSignal`: Freqtrade-compatible signal
- `ActionIntentEntry`: Entry action parameters
- `ActionIntentExit`: Exit action parameters
- `ActionIntent`: Complete action intent

### Data Schemas (`data_schema.py`)

- `CandleData`: OHLCV candle data
- `TradeData`: Trade data
- `FundingRateData`: Funding rate data
- `OrderBookSnapshot`: Order book snapshot
- `OpenInterestData`: Open interest data

## Validation Rules

### Config Validation

- All numeric fields have range constraints (e.g., `ge=0`, `le=1`)
- Timeframes must be valid: `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`
- Live trading requires explicit confirmation (`live.confirm=True`)
- Required fields must be present

### Signal Validation

- Timestamps must be in ISO format
- Prices must be positive
- Confidence must be between 0 and 1
- Direction must be one of: `OPEN_LONG`, `OPEN_SHORT`, `CLOSE_LONG`, `CLOSE_SHORT`, `HOLD`

### Data Validation

- Timestamps must be positive integers (UTC milliseconds)
- Prices must be positive
- High must be >= low
- Volumes must be non-negative

## Integration with Entry Points

All entry point scripts should validate their configuration on startup:

```python
from quantsys.contracts_runtime import MainConfig, validate_config

def main():
    # Load config
    config = load_config('configs/config.json')
    
    # Validate config (fail-fast on error)
    validated_config = validate_config(config, 'MainConfig')
    
    # Continue with validated config...
```

See `validator.py` for the `validate_config` function.
