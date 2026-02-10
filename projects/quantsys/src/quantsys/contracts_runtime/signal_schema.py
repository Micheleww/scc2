from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SignalIndicators(BaseModel):
    ema_fast: float = Field(..., description="Fast EMA value")
    ema_slow: float = Field(..., description="Slow EMA value")
    adx: float = Field(..., description="ADX value")
    atr: float = Field(..., description="ATR value")
    bb_upper: float = Field(default=0.0, description="Bollinger Bands upper")
    bb_mid: float = Field(default=0.0, description="Bollinger Bands middle")
    bb_lower: float = Field(default=0.0, description="Bollinger Bands lower")
    rsi: float = Field(default=0.0, description="RSI value")


class SignalData(BaseModel):
    timestamp: str = Field(..., description="Signal timestamp (ISO format)")
    close: float = Field(..., gt=0, description="Close price")
    enter_long: bool = Field(default=False, description="Enter long signal")
    enter_short: bool = Field(default=False, description="Enter short signal")
    exit_long: bool = Field(default=False, description="Exit long signal")
    exit_short: bool = Field(default=False, description="Exit short signal")
    indicators: SignalIndicators = Field(..., description="Technical indicators")


class SignalIntent(BaseModel):
    status: Literal["OK", "ERROR", "HOLD"] = Field(..., description="Signal status")
    timestamp: str = Field(..., description="Intent timestamp (ISO format)")
    strategy: str = Field(..., description="Strategy name")
    direction: Literal["OPEN_LONG", "OPEN_SHORT", "CLOSE_LONG", "CLOSE_SHORT", "HOLD"] = Field(
        ..., description="Trading direction"
    )
    entry_price: float = Field(..., gt=0, description="Entry price")
    stop_loss: float = Field(..., gt=0, description="Stop loss price")
    reason: str = Field(..., description="Signal reason")
    signal: SignalData = Field(..., description="Signal data")

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v):
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"Invalid timestamp format: {v}. Expected ISO format.")
        return v


class FreqtradeSignal(BaseModel):
    intent_id: str = Field(..., description="Unique intent ID")
    timestamp: str = Field(..., description="Signal timestamp (ISO format)")
    pair: str = Field(..., description="Trading pair (e.g., ETH/USDT:USDT)")
    side: Literal["buy", "sell"] = Field(..., description="Order side")
    action: Literal["enter", "exit"] = Field(..., description="Order action")
    strategy: str = Field(..., description="Strategy name")
    entry_price: float = Field(..., gt=0, description="Entry price")
    stop_loss: float = Field(..., gt=0, description="Stop loss price")
    reason: str = Field(..., description="Signal reason")
    signal_timestamp: str = Field(..., description="Original signal timestamp (ISO format)")

    @field_validator("pair")
    @classmethod
    def validate_pair(cls, v):
        if "/" not in v:
            raise ValueError(f"Invalid trading pair format: {v}. Expected format: BASE/QUOTE:QUOTE")
        return v


class ActionIntentEntry(BaseModel):
    type: Literal["breakout", "pullback", "mean", "custom"] = Field(..., description="Entry type")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Entry parameters")


class ActionIntentExit(BaseModel):
    type: Literal["time", "price", "condition", "custom"] = Field(..., description="Exit type")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Exit parameters")


class ActionIntent(BaseModel):
    action_type: Literal["enter", "exit", "hold"] = Field(..., description="Action type")
    entry_type: str | None = Field(default=None, description="Entry type (for enter actions)")
    exit_logic: ActionIntentExit | None = Field(
        default=None, description="Exit logic (for exit actions)"
    )
    confidence: float = Field(default=0.8, ge=0, le=1, description="Confidence level")
    strategy_code: str = Field(..., description="Strategy code")
    output_type: Literal["action_intent"] = Field(
        default="action_intent", description="Output type"
    )

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, v, info):
        if v == "enter" and info.data.get("entry_type") is None:
            raise ValueError("entry_type is required when action_type is 'enter'")
        if v == "exit" and info.data.get("exit_logic") is None:
            raise ValueError("exit_logic is required when action_type is 'exit'")
        return v
