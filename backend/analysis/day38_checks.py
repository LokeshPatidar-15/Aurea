import sys

import numpy as np
import pandas as pd
from sqlalchemy import func, select

from analysis.cleaning import clean_candles
from analysis.db_loader import load_from_db
from analysis.features import compute_features
from database import SessionLocal
from models import Feature

EXPECTED_ROWS = {"1h": 365 * 24, "15m": 90 * 96}
SYMBOLS = ["BTCUSDT", "XAUUSD", "EURUSD"]
REQUIRED = ["ret_24", "rsi_14", "bb_pct_b", "atr_14_pct", "vol_z", "dist_poc_atr"]
ROUNDTRIP_COLUMNS = ["rsi_14", "macd_hist", "vol_z", "dist_poc_atr", "dist_swing_high_atr"]

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def check_job(symbol: str, timeframe: str) -> None:
    print(f"{symbol} {timeframe}")
    raw = load_from_db(symbol, timeframe)
    expected = EXPECTED_ROWS[timeframe]
    check("coverage >= 80% of expected candles", len(raw) >= 0.80 * expected, f"{len(raw)} of ~{expected}")

    cleaned, report = clean_candles(raw, timeframe)
    ohlc_ok = (
        cleaned.index.is_unique
        and cleaned.index.is_monotonic_increasing
        and not cleaned[["open", "high", "low", "close", "volume"]].isna().any().any()
        and (cleaned["high"] >= cleaned[["open", "close"]].max(axis=1)).all()
        and (cleaned["low"] <= cleaned[["open", "close"]].min(axis=1)).all()
    )
    check("cleaned data: unique, sorted, no NaN, OHLC consistent", bool(ohlc_ok))
    filled_share = cleaned["is_filled"].mean()
    check("filled candles < 15% of data", filled_share < 0.15, f"{filled_share:.2%}")
    median_move = np.log(cleaned["close"]).diff().abs().median()
    check("median candle move is plausible (< 1%)", median_move < 0.01, f"{median_move:.4%}")

    feats = compute_features(cleaned)
    ready = feats.dropna(subset=REQUIRED)
    sweep_rate = (ready["sweep_bull"] | ready["sweep_bear"]).mean()
    check("sweep rate between 0.5% and 25%", 0.005 < sweep_rate < 0.25, f"{sweep_rate:.2%}")

    leaks = 0
    for fraction in (0.5, 0.8):
        cut = int(len(cleaned) * fraction)
        truncated = compute_features(cleaned.iloc[:cut])
        try:
            pd.testing.assert_frame_equal(
                feats.iloc[:cut].astype(float), truncated.astype(float), check_exact=False, rtol=1e-9, atol=1e-9
            )
        except AssertionError:
            leaks += 1
    check("no lookahead: features unchanged when the future is removed", leaks == 0)

    with SessionLocal() as session:
        stored = session.scalar(
            select(func.count()).select_from(Feature).where(Feature.symbol == symbol, Feature.timeframe == timeframe)
        )
        check("features table row count matches recomputation", stored == len(ready), f"db {stored} vs computed {len(ready)}")
        sample = session.scalars(
            select(Feature).where(Feature.symbol == symbol, Feature.timeframe == timeframe).order_by(func.random()).limit(5)
        ).all()
    mismatches = 0
    for row in sample:
        expected_row = ready.loc[pd.Timestamp(row.open_time)]
        for col in ROUNDTRIP_COLUMNS:
            stored_value = getattr(row, col)
            stored_value = np.nan if stored_value is None else stored_value
            if not np.isclose(stored_value, expected_row[col], rtol=1e-9, atol=1e-12, equal_nan=True):
                mismatches += 1
    check("5 random DB rows equal recomputed values", mismatches == 0 and len(sample) == 5)


def main() -> None:
    for timeframe in ("1h", "15m"):
        for symbol in SYMBOLS:
            check_job(symbol, timeframe)
    print(f"\n{results['passed']} passed, {results['failed']} failed")
    sys.exit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main()
