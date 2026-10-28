from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OrderIn(BaseModel):
    symbol: str
    timeframe: Literal["1h"] = "1h"
    side: Literal["long", "short"]
    stop_price: float = Field(gt=0)
    rr: float = Field(default=2.0, gt=0, le=10)
    source: str = Field(default="manual", max_length=30)


class PositionOut(BaseModel):
    id: int
    symbol: str
    timeframe: str
    side: str
    status: str
    source: str
    signal_time: datetime
    stop_price: float
    rr: float
    max_bars: int
    entry_time: datetime | None = None
    entry_price: float | None = None
    target_price: float | None = None
    notional: float | None = None
    quantity: float | None = None
    risk_amount: float | None = None
    bars_seen: int = 0
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    gross_pnl: float | None = None
    fees: float | None = None
    net_pnl: float | None = None
    reject_reason: str | None = None


class TradabilityRow(BaseModel):
    symbol: str
    last_close: float
    atr_bps: float
    cost_bps: float
    cost_to_atr: float
    tradable: bool


class TickResult(BaseModel):
    processed_candles: int
    filled: int
    closed: int
    rejected: int


class OpenPositionOut(BaseModel):
    id: int
    symbol: str
    side: str
    status: str
    entry_price: float | None = None
    last_price: float | None = None
    unrealized_pnl: float | None = None


class SummaryOut(BaseModel):
    start_equity: float
    realized_equity: float
    unrealized_pnl: float
    equity_with_open: float
    peak_equity: float
    drawdown: float
    realized_today: float
    closed_trades: int
    win_rate: float | None = None
    pending_orders: int
    open_positions: list[OpenPositionOut]
    drawdown_halt: bool
    daily_loss_limit_hit: bool
