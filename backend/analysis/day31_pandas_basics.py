import time

import pandas as pd

from analysis.common import load_candles

df = load_candles("BTCUSDT", "1m")

print("=== 1. Shape, dtypes, first rows ===")
print("shape:", df.shape)
print(df.dtypes.to_string())
print(df.head(3).to_string())

print("\n=== 2. describe() ===")
print(df[["open", "close", "volume"]].describe().round(2).to_string())

print("\n=== 3. loc (labels) vs iloc (positions) ===")
by_label = df.loc[df.index[10]:df.index[14], ["open", "close"]]
by_position = df.iloc[10:14][["open", "close"]]
print("loc  rows:", len(by_label), "(end label is INCLUDED)")
print("iloc rows:", len(by_position), "(end position is EXCLUDED)")

print("\n=== 4. New columns (vectorized) ===")
df["range"] = df["high"] - df["low"]
df["body"] = (df["close"] - df["open"]).abs()
df["candle_return_pct"] = (df["close"] - df["open"]) / df["open"] * 100
df["is_bullish"] = df["close"] > df["open"]
print(df[["open", "close", "range", "body", "candle_return_pct", "is_bullish"]].tail(3).round(4).to_string())

print("\n=== 5. Filtering with boolean masks ===")
bullish = df[df["is_bullish"]]
print(f"bullish candles: {len(bullish)} / {len(df)} ({len(bullish) / len(df) * 100:.1f}%)")
threshold = df["range"].quantile(0.99)
big_bullish = df[(df["range"] > threshold) & df["is_bullish"]]
print(f"top-1% range threshold: {threshold:.2f} USDT | of those, bullish: {len(big_bullish)}")
print(df.nlargest(3, "range")[["open", "high", "low", "close", "range"]].to_string())

print("\n=== 6. groupby ===")
print(df.groupby("is_bullish")[["volume", "range"]].mean().round(4).to_string())

print("\n=== 7. Data quality checks (every count should be 0) ===")
print("missing values:", int(df.isna().sum().sum()))
print("duplicate timestamps:", int(df.index.duplicated().sum()))
print("index sorted (should be True):", df.index.is_monotonic_increasing)
print("high below open/close:", int((df["high"] < df[["open", "close"]].max(axis=1)).sum()))
print("low above open/close:", int((df["low"] > df[["open", "close"]].min(axis=1)).sum()))
print("non-positive prices:", int((df[["open", "high", "low", "close"]] <= 0).sum().sum()))

print("\n=== 8. Python loop vs vectorized ===")
start = time.perf_counter()
looped = [df["high"].iloc[i] - df["low"].iloc[i] for i in range(len(df))]
loop_seconds = time.perf_counter() - start
start = time.perf_counter()
vectorized = df["high"] - df["low"]
vector_seconds = max(time.perf_counter() - start, 1e-9)
print(f"loop: {loop_seconds:.3f}s | vectorized: {vector_seconds:.5f}s | about {loop_seconds / vector_seconds:,.0f}x faster")
