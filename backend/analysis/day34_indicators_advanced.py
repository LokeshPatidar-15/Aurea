import pandas as pd

from analysis.common import load_candles, resample_ohlcv
from analysis.indicators import atr, bollinger, macd, true_range

df = resample_ohlcv(load_candles("BTCUSDT", "1m"), "15min")
close, high, low = df["close"], df["high"], df["low"]

m = macd(close)
bb = bollinger(close)
df = df.join(m).join(bb)
df["atr14"] = atr(high, low, close)

print("=== 1. MACD identity: histogram = macd - signal ===")
assert ((df["macd"] - df["signal"]) - df["hist"]).abs().max() < 1e-9
print("identity holds")
signs = (df["hist"].dropna() > 0).astype(int).diff().abs().sum()
print("histogram sign flips (momentum changes):", int(signs))

print("\n=== 2. Bollinger %b ===")
pct_b = df["bb_pct_b"].dropna()
inside = ((pct_b >= 0) & (pct_b <= 1)).mean() * 100
print(f"price inside the bands: {inside:.1f}% of the time (about 95% expected for a bell-shaped world)")
print(f"closes above upper band: {(pct_b > 1).sum()} | below lower band: {(pct_b < 0).sum()}")
print(f"narrowest band width: {df['bb_width'].min() * 100:.2f}% of price | widest: {df['bb_width'].max() * 100:.2f}%")

print("\n=== 3. True Range catches gaps that high-low misses ===")
tr = true_range(high, low, close)
gap_candles = (tr > (high - low) + 1e-9).sum()
print(f"candles where true range is bigger than high-low: {int(gap_candles)}")

print("\n=== 4. ATR ===")
atr_pct = (df["atr14"] / close * 100).dropna()
print(f"ATR14 as % of price: average {atr_pct.mean():.3f}% | max {atr_pct.max():.3f}%")
print(df[["close", "atr14"]].tail(3).round(2).to_string())

print("\n=== 5. Preview of Phase 11: ATR-based position size ===")
account, risk_pct = 10_000, 1.0
last_close, last_atr = close.iloc[-1], df["atr14"].iloc[-1]
stop_distance = 1.5 * last_atr
risk_amount = account * risk_pct / 100
quantity = risk_amount / stop_distance
notional = quantity * last_close
print(f"account {account:,} USDT, risk {risk_pct}% = {risk_amount:.2f} USDT")
print(f"BTC price {last_close:,.2f} | ATR14 {last_atr:.2f} | stop distance (1.5 x ATR) {stop_distance:.2f}")
print(f"position size: {quantity:.5f} BTC = {notional:,.2f} USDT notional ({notional / account:.1f}x the account)")

print("\n=== 6. Cross-check with the ta library ===")
try:
    from ta.trend import MACD
    from ta.volatility import AverageTrueRange, BollingerBands

    ta_macd = MACD(close)
    ta_bb = BollingerBands(close, window=20, window_dev=2)
    ta_atr = AverageTrueRange(high, low, close, window=14)
    pairs = {
        "MACD line": (df["macd"], ta_macd.macd()),
        "MACD signal": (df["signal"], ta_macd.macd_signal()),
        "MACD histogram": (df["hist"], ta_macd.macd_diff()),
        "Bollinger upper": (df["bb_upper"], ta_bb.bollinger_hband()),
        "Bollinger lower": (df["bb_lower"], ta_bb.bollinger_lband()),
        "Bollinger %b": (df["bb_pct_b"], ta_bb.bollinger_pband()),
        "ATR 14": (df["atr14"], ta_atr.average_true_range()),
    }
    for name, (ours, theirs) in pairs.items():
        diff = (ours - theirs).abs().iloc[300:].max()
        print(f"{name}: max difference after warmup = {diff:.2e}")
except Exception as e:
    print(f"ta cross-check skipped ({type(e).__name__}: {e})")
