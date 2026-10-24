from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from models import PriceHistory

CHUNK_SIZE = 3000


def count_rows(session: Session, symbol: str, timeframe: str) -> int:
    stmt = select(func.count()).select_from(PriceHistory).where(
        PriceHistory.symbol == symbol, PriceHistory.timeframe == timeframe
    )
    return session.scalar(stmt) or 0


def upsert_candles(session: Session, symbol: str, timeframe: str, candles: list[dict]) -> int:
    before = count_rows(session, symbol, timeframe)
    for start in range(0, len(candles), CHUNK_SIZE):
        rows = [
            {
                "symbol": symbol,
                "timeframe": timeframe,
                "open_time": c["open_time"],
                "open": Decimal(c["open"]),
                "high": Decimal(c["high"]),
                "low": Decimal(c["low"]),
                "close": Decimal(c["close"]),
                "volume": Decimal(c["volume"]),
            }
            for c in candles[start:start + CHUNK_SIZE]
        ]
        session.execute(pg_insert(PriceHistory).values(rows).on_conflict_do_nothing())
    session.commit()
    return count_rows(session, symbol, timeframe) - before
