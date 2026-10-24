import argparse
import sys
import time

from database import SessionLocal
from services.binance_history import INTERVAL_MS, SOURCE_SYMBOL, HistoryError, fetch_range
from services.history_store import count_rows, upsert_candles

PLAN = {"1h": 365, "15m": 90}


def floor_to_interval(now_ms: int, timeframe: str) -> int:
    step = INTERVAL_MS[timeframe]
    return now_ms - now_ms % step


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill historical candles into price_history.")
    parser.add_argument("--symbols", nargs="+", default=list(SOURCE_SYMBOL))
    parser.add_argument("--timeframes", nargs="+", default=list(PLAN))
    parser.add_argument("--days", type=int, default=None, help="override the lookback for every timeframe")
    args = parser.parse_args()

    failures = 0
    for timeframe in args.timeframes:
        days = args.days or PLAN[timeframe]
        end_ms = floor_to_interval(int(time.time() * 1000), timeframe)
        start_ms = end_ms - days * 86_400_000
        for symbol in args.symbols:
            started = time.time()
            try:
                candles = fetch_range(symbol, timeframe, start_ms, end_ms)
            except HistoryError as exc:
                failures += 1
                print(f"{symbol:8} {timeframe:3} FAILED: {exc}")
                continue
            if not candles:
                failures += 1
                print(f"{symbol:8} {timeframe:3} FAILED: Binance returned no candles")
                continue
            with SessionLocal() as session:
                inserted = upsert_candles(session, symbol, timeframe, candles)
                total = count_rows(session, symbol, timeframe)
            print(
                f"{symbol:8} {timeframe:3} fetched {len(candles):5} | inserted {inserted:5} | "
                f"already present {len(candles) - inserted:5} | table total {total:5} | "
                f"{candles[0]['open_time']:%Y-%m-%d} -> {candles[-1]['open_time']:%Y-%m-%d} | {time.time() - started:.1f}s"
            )
    if failures:
        print(f"{failures} job(s) failed. Re-running is safe: inserts are idempotent.")
        sys.exit(1)


if __name__ == "__main__":
    main()
