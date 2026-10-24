import argparse

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from analysis.cleaning import clean_candles
from analysis.db_loader import load_from_db
from analysis.features import FEATURE_COLUMNS, compute_features
from database import SessionLocal
from models import Feature

CHUNK_SIZE = 2000
REQUIRED = ["ret_24", "rsi_14", "bb_pct_b", "atr_14_pct", "vol_z", "dist_poc_atr"]


def to_records(feats, symbol: str, timeframe: str) -> list[dict]:
    clean = feats.astype(object).where(feats.notna(), None)
    records = clean.to_dict("records")
    for record, ts in zip(records, feats.index):
        record["symbol"] = symbol
        record["timeframe"] = timeframe
        record["open_time"] = ts.to_pydatetime()
    return records


def count_features(session, symbol: str, timeframe: str) -> int:
    stmt = select(func.count()).select_from(Feature).where(Feature.symbol == symbol, Feature.timeframe == timeframe)
    return session.scalar(stmt) or 0


def build(symbol: str, timeframe: str) -> None:
    cleaned, report = clean_candles(load_from_db(symbol, timeframe), timeframe)
    feats = compute_features(cleaned)
    ready = feats.dropna(subset=REQUIRED)
    records = to_records(ready, symbol, timeframe)

    with SessionLocal() as session:
        before = count_features(session, symbol, timeframe)
        for start in range(0, len(records), CHUNK_SIZE):
            stmt = pg_insert(Feature).values(records[start:start + CHUNK_SIZE])
            update = {col: stmt.excluded[col] for col in FEATURE_COLUMNS}
            session.execute(stmt.on_conflict_do_update(index_elements=["symbol", "timeframe", "open_time"], set_=update))
        session.commit()
        after = count_features(session, symbol, timeframe)

    print(
        f"{symbol:8} {timeframe:3} candles {report.rows_out:5} | warmup dropped {len(feats) - len(ready):3} | "
        f"stored {len(records):5} | new {after - before:5} | updated {len(records) - (after - before):5} | "
        f"sweeps bull {int(ready['sweep_bull'].sum())} bear {int(ready['sweep_bear'].sum())}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute features and store them in the features table.")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "XAUUSD", "EURUSD"])
    parser.add_argument("--timeframes", nargs="+", default=["1h", "15m"])
    args = parser.parse_args()
    for timeframe in args.timeframes:
        for symbol in args.symbols:
            build(symbol, timeframe)


if __name__ == "__main__":
    main()
