import pandas as pd
from sqlalchemy import text

from analysis.common import load_candles, resample_ohlcv
from database import engine

df = load_candles("BTCUSDT", "1m")

print("=== 1. Datetime index ===")
print("dtype:", df.index.dtype)
print("from:", df.index.min(), "| to:", df.index.max())
print("span:", df.index.max() - df.index.min())

print("\n=== 2. Slicing by date and time ===")
last_day = df.index[-1].strftime("%Y-%m-%d")
print(f"candles on {last_day} (UTC):", len(df.loc[last_day]))
last_two_hours = df.loc[df.index[-1] - pd.Timedelta(hours=2):]
print("candles in the last 2 hours:", len(last_two_hours))

print("\n=== 3. Gaps ===")
step = df.index.to_series().diff().dropna()
print("most common step between candles:")
print(step.value_counts().head(3).to_string())
full_range = pd.date_range(df.index.min(), df.index.max(), freq="1min")
print("missing minutes:", len(full_range.difference(df.index)))

print("\n=== 4. Resampling 1m into bigger candles ===")
for rule in ["5min", "15min", "1h", "4h", "1D"]:
    print(f"{rule:>6}: {len(resample_ohlcv(df, rule))} candles")

print("\n=== 5. Why mean() is the wrong way to resample ===")
right = resample_ohlcv(df, "1h")["close"]
wrong = df["close"].resample("1h").mean().dropna()
print(f"max difference between last-close and mean-close: {(right - wrong).abs().max():.2f} USDT")

print("\n=== 6. Timezones: store UTC, show IST ===")
print("first candle UTC:", df.index[0])
print("first candle IST:", df.index[0].tz_convert("Asia/Kolkata"))
volume_by_hour = df.groupby(df.index.hour)["volume"].mean().sort_values(ascending=False)
print("busiest UTC hours (average 1m volume):")
print(volume_by_hour.head(3).round(2).to_string())

print("\n=== 7. Proof: our 1h candles vs Binance's own 1h candles from the database ===")
with engine.connect() as conn:
    theirs = pd.read_sql(
        text(
            "SELECT open_time, open, high, low, close, volume FROM price_history "
            "WHERE symbol = 'BTCUSDT' AND timeframe = '1h' ORDER BY open_time"
        ),
        conn,
        index_col="open_time",
    )

if theirs.empty:
    print("skipped: no 1h candles in price_history (run python3 -m scripts.seed)")
else:
    theirs.index = pd.to_datetime(theirs.index, utc=True)
    theirs = theirs.astype(float)
    ours = resample_ohlcv(df, "1h")
    common = ours.index.intersection(theirs.index)
    common = common.difference([ours.index[0], ours.index[-1], theirs.index[-1]])
    if len(common) == 0:
        print("skipped: no fully closed hours overlap between the two datasets")
    else:
        price_cols = ["open", "high", "low", "close"]
        price_diff = (ours.loc[common, price_cols] - theirs.loc[common, price_cols]).abs().max().max()
        volume_rel = ((ours.loc[common, "volume"] - theirs.loc[common, "volume"]).abs() / theirs.loc[common, "volume"]).max()
        print(f"compared {len(common)} fully closed hourly candles")
        print(f"max OHLC difference: {price_diff:.8f}")
        print(f"max relative volume difference: {volume_rel:.2e}")
