from datetime import datetime

from pydantic import BaseModel


class MarkedPosition(BaseModel):
    id: int | None = None
    symbol: str
    side: str
    entry_price: float | None = None
    last_price: float | None = None
    mark_time: datetime | None = None
    mark_stale: bool
    notional: float | None = None
    risk_amount: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    unrealized_pnl: float | None = None
    unrealized_pct: float | None = None
    unrealized_r: float | None = None


class SymbolExposure(BaseModel):
    long: float
    short: float
    net: float
    gross: float


class ExposureOut(BaseModel):
    gross_notional: float
    long_notional: float
    short_notional: float
    net_notional: float
    gross_pct_of_equity: float | None = None
    max_gross_pct: float
    headroom_pct: float | None = None
    slots_used: int
    slots_max: int
    by_symbol: dict[str, SymbolExposure] = {}


class DrawdownOut(BaseModel):
    points: int
    peak_equity: float | None = None
    peak_time: datetime | None = None
    current_equity: float | None = None
    current_drawdown: float
    current_drawdown_usd: float
    max_drawdown: float
    max_drawdown_time: datetime | None = None
    underwater_now: bool
    days_underwater: float
    longest_underwater_days: float


class DailyLimitOut(BaseModel):
    realized_today: float
    limit_pct: float
    limit_usd: float
    used_pct: float | None = None
    hit: bool


class HaltsOut(BaseModel):
    drawdown_halt: bool
    max_drawdown_halt: float
    daily_loss_limit_hit: bool
    new_orders_blocked: bool


class EvidenceOut(BaseModel):
    trades: int
    win_rate: float | None = None
    expectancy_r: float | None = None
    expectancy_r_low: float | None = None
    expectancy_r_high: float | None = None
    sample_warning: str | None = None


class OverviewOut(BaseModel):
    as_of: datetime
    start_equity: float
    realized_equity: float
    realized_pnl: float
    unrealized_pnl: float
    equity_with_open: float
    total_pnl: float
    total_return_pct: float
    closed_trades: int
    pending_orders: int
    open_positions: list[MarkedPosition] = []
    marks_missing: int
    marks_stale: int
    exposure: ExposureOut
    drawdown: DrawdownOut
    daily_limit: DailyLimitOut
    halts: HaltsOut
    next_trade_risk_usd: float
    mark_price_source: str
    unrealized_includes_exit_costs: bool
    research_only: bool
    evidence: EvidenceOut | None = None


class PnlBucket(BaseModel):
    period_start: datetime
    trades: int
    wins: int
    losses: int
    net_pnl: float
    gross_pnl: float
    fees: float
    cumulative_pnl: float
    equity_end: float


class PnlOut(BaseModel):
    period: str
    timezone: str
    start_equity: float
    buckets: list[PnlBucket] = []


class JournalTrade(BaseModel):
    id: int | None = None
    symbol: str | None = None
    side: str | None = None
    source: str | None = None
    entry_time: datetime | None = None
    entry_price: float | None = None
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    notional: float | None = None
    risk_amount: float | None = None
    gross_pnl: float | None = None
    fees: float | None = None
    net_pnl: float
    outcome: str
    r_multiple: float | None = None
    hold_hours: float | None = None
    bars_held: int | None = None
    cost_bps: float | None = None


class TradesPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[JournalTrade] = []


class BreakdownGroup(BaseModel):
    name: str
    trades: int
    share_of_trades: float
    wins: int
    win_rate: float
    net_pnl: float
    gross_pnl: float
    fees: float
    avg_net_pnl: float
    avg_r: float | None = None
    profit_factor: float | None = None
    thin: bool


class BreakdownOut(BaseModel):
    by: str
    total_trades: int
    note: str
    groups: list[BreakdownGroup] = []
