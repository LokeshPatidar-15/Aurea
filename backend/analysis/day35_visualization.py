import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mplfinance as mpf
import numpy as np
import pandas as pd
import seaborn as sns

from analysis.common import OUTPUT_DIR, load_candles, resample_ohlcv
from analysis.indicators import atr, bollinger, macd, rsi

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

df = resample_ohlcv(load_candles("BTCUSDT", "1m"), "15min")
df["rsi"] = rsi(df["close"])
df = df.join(macd(df["close"])).join(bollinger(df["close"]))
df["atr"] = atr(df["high"], df["low"], df["close"])

view = df.tail(150).copy()
view.index = view.index.tz_convert("Asia/Kolkata").tz_localize(None)

print("=== Chart 1: candlesticks + SMA20/SMA50 + volume ===")
candles = view[["open", "high", "low", "close", "volume"]].rename(columns=str.title)
path1 = OUTPUT_DIR / "01_candles.png"
mpf.plot(
    candles,
    type="candle",
    style="nightclouds",
    mav=(20, 50),
    volume=True,
    title="BTCUSDT 15m (IST)",
    savefig=dict(fname=str(path1), dpi=130, bbox_inches="tight"),
)
print("saved", path1)

print("\n=== Chart 2: indicator dashboard ===")
plt.style.use("dark_background")
x = view.index
fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1.3, 1]})

axes[0].plot(x, view["close"], color="#e8e8e6", linewidth=1.3, label="close")
axes[0].plot(x, view["bb_mid"], color="#d97706", linewidth=1, label="SMA20")
axes[0].fill_between(x, view["bb_lower"], view["bb_upper"], color="#7F77DD", alpha=0.18, label="Bollinger (20, 2)")
axes[0].set_title("BTCUSDT 15m: price and Bollinger Bands")
axes[0].legend(loc="upper left", fontsize=8)

axes[1].plot(x, view["rsi"], color="#7F77DD", linewidth=1.2)
axes[1].axhline(70, color="#ef5350", linestyle="--", linewidth=0.8)
axes[1].axhline(30, color="#26a69a", linestyle="--", linewidth=0.8)
axes[1].set_ylim(0, 100)
axes[1].set_ylabel("RSI 14")

colors = np.where(view["hist"] >= 0, "#26a69a", "#ef5350")
axes[2].bar(x, view["hist"], width=0.008, color=colors)
axes[2].plot(x, view["macd"], color="#e8e8e6", linewidth=1, label="MACD")
axes[2].plot(x, view["signal"], color="#d97706", linewidth=1, label="signal")
axes[2].legend(loc="upper left", fontsize=8)
axes[2].set_ylabel("MACD")

axes[3].plot(x, view["atr"], color="#d97706", linewidth=1.2)
axes[3].set_ylabel("ATR 14")

fig.autofmt_xdate()
fig.tight_layout()
path2 = OUTPUT_DIR / "02_indicators.png"
fig.savefig(path2, dpi=130)
plt.close(fig)
print("saved", path2)

print("\n=== Chart 3: return distribution and feature correlations ===")
returns = np.log(df["close"]).diff().dropna() * 100
features = pd.DataFrame(
    {
        "return": returns,
        "range_pct": (df["high"] - df["low"]) / df["close"] * 100,
        "volume": df["volume"],
        "rsi": df["rsi"],
        "macd_hist": df["hist"],
        "atr_pct": df["atr"] / df["close"] * 100,
        "bb_pct_b": df["bb_pct_b"],
    }
).dropna()

fig, axes = plt.subplots(1, 2, figsize=(14, 5))
sns.histplot(returns, bins=80, kde=True, ax=axes[0], color="#7F77DD")
axes[0].set_title("15m log returns (%): fat tails")
axes[0].set_xlabel("return %")
sns.heatmap(features.corr(), annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=axes[1], cbar=False)
axes[1].set_title("Feature correlations (same candle)")
fig.tight_layout()
path3 = OUTPUT_DIR / "03_distribution_and_correlation.png"
fig.savefig(path3, dpi=130)
plt.close(fig)
print("saved", path3)

std = returns.std()
beyond_3 = (returns.abs() > 3 * std).mean() * 100
print(f"\nskew: {returns.skew():.2f} | excess kurtosis: {returns.kurt():.2f} (normal bell curve = 0)")
print(f"moves beyond 3 standard deviations: {beyond_3:.2f}% of candles (normal bell curve = 0.27%)")
