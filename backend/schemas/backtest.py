from typing import Any

from pydantic import BaseModel


class Verdict(BaseModel):
    label: str
    reasons: list[str]
    message: str


class BacktestOut(BaseModel):
    symbol: str
    timeframe: str
    strategy_name: str
    strategy_key: str
    long_text: str | None = None
    short_text: str | None = None
    stop_mode: str
    stop_buffer_atr: float
    data: dict[str, Any]
    signals: dict[str, int]
    result: dict[str, Any]
    trades_per_year: float | None = None
    cost_sensitivity: list[dict[str, Any]]
    random_baseline: dict[str, Any] | None = None
    slices: list[dict[str, Any]]
    positive_slices: int
    sharpe: dict[str, Any]
    multiple_testing: dict[str, Any]
    verdict: Verdict
    assumptions: dict[str, Any]
    research_only: bool
    note: str


class TrialsOut(BaseModel):
    strategies_tried: int
    bonferroni_threshold: float
    recent: list[dict[str, Any]]
