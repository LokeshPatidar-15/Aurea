import pandas as pd
from sqlalchemy import select

from database import SessionLocal
from models import PriceHistory


def load_from_db(symbol: str, timeframe: str) -> pd.DataFrame:
    columns = ["open_time", "open", "high", "low", "close", "volume"]
    stmt = (
        select(*[getattr(PriceHistory, c) for c in columns])
        .where(PriceHistory.symbol == symbol, PriceHistory.timeframe == timeframe)
        .order_by(PriceHistory.open_time)
    )
    with SessionLocal() as session:
        rows = session.execute(stmt).all()
    if not rows:
        raise ValueError(f"no candles for {symbol} {timeframe}. Run: python3 -m scripts.ingest_history")
    df = pd.DataFrame(rows, columns=columns)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    df = df.set_index("open_time")
    return df.astype(float)
