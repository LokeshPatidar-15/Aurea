from datetime import datetime, timezone

from sqlalchemy import func, select

from database import SessionLocal
from models import PriceHistory
from models.paper import PaperPosition
from services import paper_analytics, portfolio_analytics as pa
from services.paper_service import LIMITS, to_dict

MAX_PAGE = 200


def _limits() -> dict:
    return {
        "max_drawdown_halt": LIMITS.max_drawdown_halt,
        "daily_loss_limit": LIMITS.daily_loss_limit,
        "max_gross_exposure": LIMITS.max_gross_exposure,
        "max_open_positions": LIMITS.max_open_positions,
        "risk_per_trade": LIMITS.risk_per_trade,
    }


def _load():
    with SessionLocal() as session:
        rows = [to_dict(r) for r in session.execute(select(PaperPosition)).scalars().all()]
        marks = {}
        for r in rows:
            key = (r["symbol"], r["timeframe"])
            if r["status"] != "open" or key in marks:
                continue
            last = session.execute(
                select(PriceHistory.close, PriceHistory.open_time)
                .where(PriceHistory.symbol == r["symbol"], PriceHistory.timeframe == r["timeframe"])
                .order_by(PriceHistory.open_time.desc())
                .limit(1)
            ).first()
            marks[key] = (last[0], last[1]) if last else (None, None)
    return rows, marks


def _split(rows: list):
    closed = [r for r in rows if r["status"] == "closed"]
    open_rows = [r for r in rows if r["status"] == "open"]
    pending = sum(1 for r in rows if r["status"] == "pending")
    return closed, open_rows, pending


def overview() -> dict:
    rows, marks = _load()
    closed, open_rows, pending = _split(rows)
    now = datetime.now(timezone.utc)
    marked = [pa.mark_position(r, *marks.get((r["symbol"], r["timeframe"]), (None, None)), now) for r in open_rows]
    out = pa.build_overview(closed, marked, pending, now, _limits())
    perf = paper_analytics.performance(closed)
    out["evidence"] = {
        "trades": perf["trades"],
        "win_rate": perf.get("win_rate"),
        "expectancy_r": perf.get("expectancy_r"),
        "expectancy_r_low": perf.get("expectancy_r_low"),
        "expectancy_r_high": perf.get("expectancy_r_high"),
        "sample_warning": perf.get("sample_warning"),
    }
    return out


def pnl(period: str, limit: int) -> dict:
    rows, _ = _load()
    closed = _split(rows)[0]
    return {"period": period, "buckets": pa.pnl_by_period(closed, period, limit), "timezone": "UTC", "start_equity": pa.START_EQUITY}


def trades(limit: int, offset: int, symbol: str | None, exit_reason: str | None) -> dict:
    rows, _ = _load()
    items = pa.journal(_split(rows)[0])
    if symbol:
        items = [t for t in items if t["symbol"] == symbol.upper()]
    if exit_reason:
        items = [t for t in items if t["exit_reason"] == exit_reason]
    limit = min(max(limit, 1), MAX_PAGE)
    offset = max(offset, 0)
    return {"total": len(items), "limit": limit, "offset": offset, "items": items[offset : offset + limit]}


def breakdown(by: str) -> dict:
    rows, _ = _load()
    return pa.breakdown(_split(rows)[0], by)
