from datetime import datetime

from pydantic import BaseModel


class GroupStats(BaseModel):
    trades: int
    net_pnl: float
    win_rate: float


class PerformanceOut(BaseModel):
    trades: int
    start_equity: float
    end_equity: float
    net_pnl: float | None = None
    return_pct: float | None = None
    win_rate: float | None = None
    avg_win: float | None = None
    avg_loss: float | None = None
    payoff_ratio: float | None = None
    profit_factor: float | None = None
    expectancy_usd: float | None = None
    expectancy_r: float | None = None
    expectancy_r_low: float | None = None
    expectancy_r_high: float | None = None
    gross_pnl: float | None = None
    fees: float | None = None
    fees_share_of_gross: float | None = None
    max_drawdown: float | None = None
    max_drawdown_usd: float | None = None
    current_drawdown: float | None = None
    longest_losing_streak: int | None = None
    avg_bars_held: float | None = None
    exit_reasons: dict[str, int] = {}
    by_symbol: dict[str, GroupStats] = {}
    by_side: dict[str, GroupStats] = {}
    sample_warning: str | None = None


class EquityPoint(BaseModel):
    time: datetime
    equity: float
    drawdown: float
    position_id: int | None = None
