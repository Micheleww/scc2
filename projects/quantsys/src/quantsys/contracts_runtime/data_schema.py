from typing import Literal

from pydantic import BaseModel, Field, field_validator


class CandleData(BaseModel):
    ts: int = Field(..., gt=0, description="UTC millisecond timestamp")
    instId: str = Field(..., min_length=1, description="Instrument ID")
    timeframe: str = Field(..., min_length=1, description="Timeframe")
    source: str = Field(..., min_length=1, description="Data source")
    open: float = Field(..., gt=0, description="Open price")
    high: float = Field(..., gt=0, description="High price")
    low: float = Field(..., gt=0, description="Low price")
    close: float = Field(..., gt=0, description="Close price")
    volume: float = Field(..., ge=0, description="Volume")
    open_interest: float | None = Field(default=None, ge=0, description="Open interest")
    funding_rate: float | None = Field(default=None, description="Funding rate")
    liquidation_volume: float | None = Field(default=None, ge=0, description="Liquidation volume")

    @field_validator("high", "low")
    @classmethod
    def validate_price_relationship(cls, v, info):
        if info.field_name == "low" and "high" in info.data and v > info.data["high"]:
            raise ValueError("Low price cannot be greater than high price")
        if info.field_name == "high" and "low" in info.data and v < info.data["low"]:
            raise ValueError("High price cannot be less than low price")
        return v


class TradeData(BaseModel):
    tradeId: int = Field(..., gt=0, description="Trade ID (unique)")
    ts: int = Field(..., gt=0, description="UTC millisecond timestamp")
    instId: str = Field(..., min_length=1, description="Instrument ID")
    side: Literal["buy", "sell"] = Field(..., description="Trade side")
    price: float = Field(..., gt=0, description="Trade price")
    amount: float = Field(..., gt=0, description="Trade amount")
    source: str = Field(..., min_length=1, description="Data source")


class FundingRateData(BaseModel):
    ts: int = Field(..., gt=0, description="UTC millisecond timestamp")
    instId: str = Field(..., min_length=1, description="Instrument ID")
    metric: str = Field(..., min_length=1, description="Metric name")
    value: float = Field(..., description="Metric value")


class OrderBookSnapshot(BaseModel):
    ts: int = Field(..., gt=0, description="UTC millisecond timestamp")
    instId: str = Field(..., min_length=1, description="Instrument ID")
    side: Literal["buy", "sell"] = Field(..., description="Order side")
    price: float = Field(..., gt=0, description="Order price")
    amount: float = Field(..., gt=0, description="Order amount")
    source: str = Field(..., min_length=1, description="Data source")


class OpenInterestData(BaseModel):
    ts: int = Field(..., gt=0, description="UTC millisecond timestamp")
    instId: str = Field(..., min_length=1, description="Instrument ID")
    metric: str = Field(..., min_length=1, description="Metric name")
    value: float = Field(..., description="Metric value")
