from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SystemConfig(BaseModel):
    name: str = Field(default="quantsys", description="System name")
    version: str = Field(default="1.0.0", description="System version")
    run_mode: Literal["development", "production", "testing"] = Field(
        default="development", description="Run mode"
    )
    drill_mode: bool = Field(default=False, description="Drill mode flag")
    live_trading: bool = Field(default=False, description="Live trading flag")


class DatabaseConfig(BaseModel):
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, ge=1, le=65535, description="Database port")
    database: str = Field(..., description="Database name")
    user: str = Field(..., description="Database user")
    password: str = Field(..., description="Database password")


class DataCollectionConfig(BaseModel):
    exchanges: list[str] = Field(default_factory=list, description="List of exchanges")
    symbols: list[str] = Field(..., min_length=1, description="List of trading symbols")
    timeframes: list[str] = Field(..., min_length=1, description="List of timeframes")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")

    @field_validator("timeframes")
    @classmethod
    def validate_timeframes(cls, v):
        valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
        for tf in v:
            if tf not in valid_timeframes:
                raise ValueError(f"Invalid timeframe: {tf}. Must be one of {valid_timeframes}")
        return v


class RealTimeConfig(BaseModel):
    exchanges: list[str] = Field(default_factory=list, description="List of exchanges")
    symbols: list[str] = Field(..., min_length=1, description="List of trading symbols")
    timeframes: list[str] = Field(..., min_length=1, description="List of timeframes")


class FactorConfig(BaseModel):
    calculate_factors: bool = Field(default=True, description="Whether to calculate factors")
    traditional_factors: bool = Field(
        default=True, description="Whether to use traditional factors"
    )
    dl_factors: bool = Field(default=False, description="Whether to use deep learning factors")


class StrategyConfig(BaseModel):
    strategy_id: int = Field(..., ge=1, description="Strategy ID")
    strategy_file: str | None = Field(default=None, description="Strategy file path")
    strategy_class: str | None = Field(default=None, description="Strategy class name")
    max_strategies: int = Field(default=10, ge=1, description="Maximum number of strategies")


class FreqtradeConfig(BaseModel):
    config_path: str = Field(..., description="Freqtrade config path")


class LiveConfig(BaseModel):
    enabled: bool = Field(default=False, description="Live trading enabled")
    confirm: bool = Field(default=False, description="Live trading confirmation")
    exchange: str = Field(default="okx", description="Exchange name")
    symbol: str = Field(default="ETH-USDT", description="Trading symbol")
    timeframe: str = Field(default="1h", description="Timeframe")
    symbols_allowlist: list[str] = Field(default_factory=list, description="Allowed symbols list")

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v):
        valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
        if v not in valid_timeframes:
            raise ValueError(f"Invalid timeframe: {v}. Must be one of {valid_timeframes}")
        return v


class DryRunConfig(BaseModel):
    enabled: bool = Field(default=True, description="Dry run mode enabled")
    initial_capital: float = Field(default=100000, gt=0, description="Initial capital")


class RiskConfig(BaseModel):
    max_total_usdt: float = Field(default=10.0, gt=0, description="Maximum total USDT")
    max_position_percent: float = Field(
        default=0.1, gt=0, le=1, description="Maximum position percentage"
    )
    max_total_position: float = Field(default=0.5, gt=0, le=1, description="Maximum total position")
    max_daily_loss: float = Field(default=0.05, gt=0, le=1, description="Maximum daily loss")
    max_order_size: float = Field(default=1000, gt=0, description="Maximum order size")
    max_leverage: float = Field(default=1, ge=1, le=100, description="Maximum leverage")


class ReconciliationConfig(BaseModel):
    reconcile_interval: int = Field(
        default=3, ge=1, description="Reconciliation interval (seconds)"
    )
    balance_threshold: float = Field(default=0.01, ge=0, le=1, description="Balance threshold")
    position_threshold: float = Field(default=0.001, ge=0, le=1, description="Position threshold")
    max_allowed_drifts: int = Field(default=3, ge=1, description="Maximum allowed drifts")


class BacktestConfig(BaseModel):
    initial_capital: float = Field(default=100000, gt=0, description="Initial capital")
    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(default="1h", description="Timeframe")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    leverage: float = Field(default=1, ge=1, le=100, description="Leverage")
    fee: float = Field(default=0.001, ge=0, le=1, description="Trading fee")
    maker_fee: float = Field(default=0.0002, ge=0, le=1, description="Maker fee")
    taker_fee: float = Field(default=0.0005, ge=0, le=1, description="Taker fee")
    slippage_bps: float = Field(default=0.0, ge=0, description="Slippage in basis points")
    funding_rate: float = Field(default=0.0, ge=0, description="Funding rate")
    funding_interval_hours: int = Field(default=8, ge=1, description="Funding interval in hours")
    execution_delay_bars: int = Field(default=1, ge=0, description="Execution delay in bars")
    random_seed: int = Field(default=42, ge=0, description="Random seed")
    risk_free_rate: float = Field(default=0.0, ge=0, description="Risk-free rate")
    max_drawdown_limit: float = Field(
        default=0.08, gt=0, le=1, description="Maximum drawdown limit"
    )
    risk_per_trade: float = Field(default=0.008, gt=0, le=1, description="Risk per trade")
    max_leverage: float = Field(default=10, ge=1, le=100, description="Maximum leverage")
    data_path: str | None = Field(default=None, description="Data path")
    use_local_data_only: bool = Field(default=False, description="Use local data only")

    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v):
        valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d"]
        if v not in valid_timeframes:
            raise ValueError(f"Invalid timeframe: {v}. Must be one of {valid_timeframes}")
        return v


class MainConfig(BaseModel):
    system: SystemConfig | None = Field(default=None, description="System configuration")
    database: DatabaseConfig | None = Field(default=None, description="Database configuration")
    data_collection: DataCollectionConfig | None = Field(
        default=None, description="Data collection configuration"
    )
    real_time: RealTimeConfig | None = Field(default=None, description="Real-time configuration")
    factor: FactorConfig | None = Field(default=None, description="Factor configuration")
    strategy: StrategyConfig | None = Field(default=None, description="Strategy configuration")
    freqtrade: FreqtradeConfig | None = Field(default=None, description="Freqtrade configuration")
    live: LiveConfig | None = Field(default=None, description="Live trading configuration")
    dry_run: DryRunConfig | None = Field(default=None, description="Dry run configuration")
    risk: RiskConfig | None = Field(default=None, description="Risk configuration")
    reconciliation: ReconciliationConfig | None = Field(
        default=None, description="Reconciliation configuration"
    )
    backtest: BacktestConfig | None = Field(default=None, description="Backtest configuration")

    @model_validator(mode="after")
    def validate_config_consistency(self):
        if self.live and self.live.enabled and not self.live.confirm:
            raise ValueError(
                "Live trading is enabled but not confirmed. Set live.confirm=True to confirm."
            )
        return self
