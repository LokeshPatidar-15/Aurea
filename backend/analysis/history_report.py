from analysis.cleaning import clean_candles
from analysis.db_loader import load_from_db

JOBS = [(s, tf) for tf in ["1h", "15m"] for s in ["BTCUSDT", "XAUUSD", "EURUSD"]]

print(f"{'symbol':8} {'tf':3} {'rows':>6} {'dups':>5} {'invalid':>7} {'gaps':>5} {'filled':>6} {'open':>5} {'outliers':>8}")
for symbol, timeframe in JOBS:
    raw = load_from_db(symbol, timeframe)
    _, r = clean_candles(raw, timeframe)
    print(
        f"{symbol:8} {timeframe:3} {r.rows_in:6} {r.duplicates_removed:5} {r.invalid_rows_removed:7} "
        f"{r.gaps_found:5} {r.candles_filled:6} {r.gaps_left_open:5} {r.outliers_flagged:8}"
    )
