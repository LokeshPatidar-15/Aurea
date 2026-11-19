from datetime import datetime

from pydantic import BaseModel


class OutcomeOut(BaseModel):
    horizon_h: int
    status: str
    gross_bps: float | None = None
    net_bps: float | None = None
    direction_correct: bool | None = None
    net_win: bool | None = None


class SignalRowOut(BaseModel):
    id: int
    symbol: str
    kind: str
    candle_time: datetime
    direction: int
    signal: str
    status: str | None = None
    confidence: float | None = None
    reference_price: float | None = None
    outcomes: dict[str, OutcomeOut] = {}


class SignalHistoryOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[SignalRowOut] = []


class CellOut(BaseModel):
    kind: str
    symbol: str
    horizon_h: int
    n: int
    n_effective: float
    pending: int
    no_data: int
    accuracy: float | None = None
    accuracy_low: float | None = None
    accuracy_high: float | None = None
    mean_gross_bps: float | None = None
    mean_net_bps: float | None = None
    net_win_rate: float | None = None
    net_low_bps: float | None = None
    net_high_bps: float | None = None
    net_low_adj_bps: float | None = None
    net_high_adj_bps: float | None = None
    baseline_long_gross_bps: float | None = None
    verdict: str


class AccountabilityOut(BaseModel):
    cost_bps: float
    horizons_h: list[int]
    looks: int
    coverage: dict
    groups: list[CellOut] = []
    notes: list[str] = []
    research_only: bool
