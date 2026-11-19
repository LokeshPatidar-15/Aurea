from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from database import SessionLocal
from models import PriceHistory
from models.signal_log import SignalLog
from services import signal_accountability as sa

MAX_SIGNALS = 5000
MAX_PAGE = 200


def record_events(events) -> int:
    rows = [row for event in events for row in sa.rows_from_event(event)]
    if not rows:
        return 0
    with SessionLocal() as session:
        result = session.execute(pg_insert(SignalLog).values(rows).on_conflict_do_nothing(constraint="uq_signal_log_candle"))
        session.commit()
        return max(0, result.rowcount or 0)


def _signals(session, symbol, kind, limit) -> list:
    stmt = select(SignalLog).where(SignalLog.timeframe == "1h").order_by(SignalLog.candle_time.desc(), SignalLog.id.desc()).limit(limit)
    if symbol:
        stmt = stmt.where(SignalLog.symbol == symbol)
    if kind:
        stmt = stmt.where(SignalLog.kind == kind)
    return [
        {"id": r.id, "symbol": r.symbol, "kind": r.kind, "candle_time": r.candle_time, "direction": r.direction, "signal": r.signal,
         "status": r.status, "confidence": r.confidence, "reference_price": r.reference_price}
        for r in session.execute(stmt).scalars().all()
    ]


def _candles(session, signals: list) -> dict:
    out = {}
    for symbol in {s["symbol"] for s in signals}:
        first = min(s["candle_time"] for s in signals if s["symbol"] == symbol)
        rows = session.execute(
            select(PriceHistory.open_time, PriceHistory.open, PriceHistory.close)
            .where(PriceHistory.symbol == symbol, PriceHistory.timeframe == "1h", PriceHistory.open_time >= first)
            .order_by(PriceHistory.open_time)
        ).all()
        out[symbol] = [(sa.to_ms(r[0]), float(r[1]), float(r[2])) for r in rows]
    return out


def history(limit: int, offset: int, symbol: str | None, kind: str | None) -> dict:
    limit = min(max(limit, 1), MAX_PAGE)
    offset = max(offset, 0)
    with SessionLocal() as session:
        signals = _signals(session, symbol, kind, MAX_SIGNALS)
        page = signals[offset : offset + limit]
        items = sa.history(page, _candles(session, page)) if page else []
    return {"total": len(signals), "limit": limit, "offset": offset, "items": items}


def accountability(symbol: str | None, kind: str | None) -> dict:
    with SessionLocal() as session:
        signals = _signals(session, symbol, kind, MAX_SIGNALS)
        candles = _candles(session, signals) if signals else {}
    return sa.accountability(signals, candles)
