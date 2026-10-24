import pandas as pd

from analysis.common import load_candles, resample_ohlcv
from analysis.indicators import ema, rsi, sma


def check_synthetic() -> None:
    rising = pd.Series(range(1, 60), dtype=float)
    falling = pd.Series(range(60, 1, -1), dtype=float)
    assert abs(rsi(rising).iloc[-1] - 100) < 1e-9, "RSI of a straight rise must be 100"
    assert abs(rsi(falling).iloc[-1] - 0) < 1e-9, "RSI of a straight fall must be 0"

    values = pd.Series([10, 11, 12, 11, 13, 14, 13, 15, 16, 15, 17, 18], dtype=float)
    window = 5
    alpha = 2 / (window + 1)
    manual = [values.iloc[0]]
    for x in values.iloc[1:]:
        manual.append(alpha * x + (1 - alpha) * manual[-1])
    assert max(abs(a - b) for a, b in zip(manual, ema(values, window))) < 1e-9, "EMA must match the recursion"
    print("synthetic checks passed: RSI=100 on a rise, RSI=0 on a fall, EMA equals the manual recursion")


def compare_with_ta(close: pd.Series, mine: dict) -> None:
    try:
        from ta.momentum import RSIIndicator
        from ta.trend import EMAIndicator, SMAIndicator

        pairs = {
            "SMA 20": (mine["sma20"], SMAIndicator(close, window=20).sma_indicator()),
            "EMA 20": (mine["ema20"], EMAIndicator(close, window=20).ema_indicator()),
            "RSI 14": (mine["rsi14"], RSIIndicator(close, window=14).rsi()),
        }
        for name, (ours, theirs) in pairs.items():
            diff = (ours - theirs).abs().iloc[300:].max()
            print(f"{name}: max difference vs ta library (after warmup) = {diff:.2e}")
    except Exception as e:
        print(f"ta cross-check skipped ({type(e).__name__}: {e})")


print("=== 1. Synthetic checks (answers known in advance) ===")
check_synthetic()

df = resample_ohlcv(load_candles("BTCUSDT", "1m"), "15min")
close = df["close"]
df["sma20"] = sma(close, 20)
df["sma50"] = sma(close, 50)
df["ema20"] = ema(close, 20)
df["rsi14"] = rsi(close, 14)

print("\n=== 2. Hand check: last SMA(20) equals the plain mean of the last 20 closes ===")
manual_sma = close.iloc[-20:].mean()
assert abs(df["sma20"].iloc[-1] - manual_sma) < 1e-9
print(f"sma20 = {df['sma20'].iloc[-1]:.2f} | manual mean = {manual_sma:.2f} | match")

print("\n=== 3. Warmup: NaN values at the start (expected 19, 49, 14) ===")
print(df[["sma20", "sma50", "rsi14"]].isna().sum().to_string())

print("\n=== 4. Latest values (15m candles) ===")
print(df[["close", "sma20", "sma50", "ema20", "rsi14"]].tail(5).round(2).to_string())

print("\n=== 5. SMA20 / SMA50 crossovers ===")
cross_up = (df["sma20"] > df["sma50"]) & (df["sma20"].shift(1) <= df["sma50"].shift(1))
cross_down = (df["sma20"] < df["sma50"]) & (df["sma20"].shift(1) >= df["sma50"].shift(1))
print("bullish crossovers (20 above 50):", int(cross_up.sum()))
print("bearish crossovers (20 below 50):", int(cross_down.sum()))
print("last 3 crossovers (IST):")
events = pd.concat([cross_up[cross_up].rename("signal").map(lambda _: "bullish"),
                    cross_down[cross_down].rename("signal").map(lambda _: "bearish")]).sort_index()
for ts, kind in events.tail(3).items():
    print(f"  {ts.tz_convert('Asia/Kolkata'):%Y-%m-%d %H:%M} IST  {kind}")

print("\n=== 6. RSI zones ===")
valid = df["rsi14"].dropna()
print(f"overbought (RSI > 70): {(valid > 70).mean() * 100:.1f}% of the time")
print(f"oversold   (RSI < 30): {(valid < 30).mean() * 100:.1f}% of the time")
print(f"RSI range seen: {valid.min():.1f} to {valid.max():.1f}")

print("\n=== 7. Cross-check with the ta library ===")
compare_with_ta(close, {"sma20": df["sma20"], "ema20": df["ema20"], "rsi14": df["rsi14"]})
