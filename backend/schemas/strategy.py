from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Conditions(BaseModel):
    sweep_bull: bool
    sweep_bear: bool
    volume_ok: bool
    trend: Literal["up", "down", "flat"]


class SignalOut(BaseModel):
    symbol: str
    timeframe: str
    strategy: str
    status: Literal["signal", "none"]
    reason: str
    side: Literal["long", "short", "none"]
    as_of: datetime
    reference_price: float
    stop_price: float | None = None
    rr: float
    risk_atr: float | None = None
    atr: float | None = None
    data_age_minutes: float
    stale: bool
    conditions: Conditions
    research_only: bool
    note: str
