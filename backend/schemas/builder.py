from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class StrategyIn(BaseModel):
    strategy: dict[str, Any]


class ValidateOut(BaseModel):
    valid: bool
    errors: list[str]
    strategy: dict[str, Any] | None = None
    long_text: str | None = None
    short_text: str | None = None
    conditions_used: list[str]
    nodes: int


class TemplateOut(BaseModel):
    id: str
    title: str
    idea: str
    evidence: str
    long_text: str | None = None
    short_text: str | None = None
    strategy: dict[str, Any]


class PreviewOut(BaseModel):
    symbol: str
    timeframe: str
    strategy_name: str
    long_text: str | None = None
    short_text: str | None = None
    status: Literal["signal", "none"]
    reason: str
    side: Literal["long", "short", "none"]
    as_of: datetime
    reference_price: float
    stop_price: float | None = None
    risk_atr: float | None = None
    data_age_minutes: float
    stale: bool
    signals_in_window: int
    window_candles: int
    research_only: bool
    note: str
