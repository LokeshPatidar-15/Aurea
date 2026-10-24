import numpy as np
import pandas as pd

from analysis.cleaning import clean_candles

rng = np.random.default_rng(1)
n = 2000
idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC", name="open_time")
close = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
open_ = np.r_[close[0], close[:-1]]
high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.001, n))
low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.001, n))
df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": rng.uniform(1, 10, n)}, index=idx)

print("=== 1. Damage a clean dataset on purpose ===")
df = pd.concat([df, df.iloc[[50, 51]]])
df.iloc[100, df.columns.get_loc("high")] = df.iloc[100]["low"] - 1
df = df.drop(df.index[200:202])
df = df.drop(df.index[500:510])
df.loc[idx[900], ["high", "close"]] *= 1.2
print("2 duplicate rows | 1 row with high < low | a 2-candle gap | a 10-candle gap | one 20% price spike")

cleaned, report = clean_candles(df, "1h", max_fill=3)

print("\n=== 2. Cleaning report ===")
for key, value in report.as_dict().items():
    print(f"{key:22} {value}")

print("\n=== 3. Invariants that must always hold after cleaning ===")
assert report.duplicates_removed == 2
assert report.invalid_rows_removed == 1
assert report.candles_filled == 3 and report.gaps_left_open == 1
assert cleaned.index.is_unique and cleaned.index.is_monotonic_increasing
assert cleaned.loc[cleaned["is_filled"], "volume"].eq(0).all()
assert bool(cleaned.loc[idx[900], "is_outlier"])
print("duplicates gone, invalid row gone, short gaps filled (flat, volume 0), long gap left open, spike flagged (not deleted)")
print("\nflagged outliers:", [t.strftime("%Y-%m-%d %H:%M") for t in cleaned.index[cleaned["is_outlier"]]])
