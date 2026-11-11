from datetime import datetime

from pydantic import BaseModel


class PatternHit(BaseModel):
    time: datetime
    patterns: list[str]


class PatternsOut(BaseModel):
    symbol: str
    timeframe: str
    as_of: datetime
    data_age_minutes: float
    stale: bool
    latest: dict[str, bool]
    sweep: dict[str, bool]
    recent: list[PatternHit]
    recent_candles: int
    research_only: bool
    note: str


class ConditionOut(BaseModel):
    name: str
    description: str
