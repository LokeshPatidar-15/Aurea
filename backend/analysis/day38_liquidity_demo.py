import numpy as np
import pandas as pd

from analysis.features import compute_features
from analysis.liquidity import confirmed_swing_levels, detect_sweeps, find_swings, rolling_volume_profile


def frame(**cols):
    n = len(next(iter(cols.values())))
    df = pd.DataFrame(cols)
    df.index = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return df


print("=== 1. Swing high is known only n candles later ===")
df = frame(high=[1, 2, 3, 9, 3, 2, 1, 2, 3, 4, 5], low=[0.5] * 3 + [8] + [0.5] * 7, close=[1] * 11, open=[1] * 11, volume=[1] * 11)
swings = find_swings(df, 3)
levels = confirmed_swing_levels(df, 3)
print("pivot candle (index):", int(swings["is_swing_high"].to_numpy().argmax()))
print("last_swing_high per candle:", levels["last_swing_high"].tolist())
assert levels["last_swing_high"].iloc[:6].isna().all() and levels["last_swing_high"].iloc[6] == 9
print("the level 9 appears only at candle 6 = pivot 3 + n 3 (no lookahead)")

print("\n=== 2. Liquidity sweep ===")
levels = pd.DataFrame({"last_swing_high": [10.0] * 5, "last_swing_low": [5.0] * 5})
levels.index = pd.date_range("2026-01-01", periods=5, freq="1h", tz="UTC")
candles = frame(high=[9, 9, 11, 9, 12], low=[6, 6, 6, 4, 6], close=[8, 8, 9.5, 6, 13], open=[8] * 5, volume=[1] * 5)
sweeps = detect_sweeps(candles, levels)
print("bear sweep (wick above 10, close back below):", sweeps["sweep_bear"].tolist())
print("bull sweep (wick below 5, close back above): ", sweeps["sweep_bull"].tolist())
assert sweeps["sweep_bear"].tolist() == [False, False, True, False, False]
assert sweeps["sweep_bull"].tolist() == [False, False, False, True, False]
print("candle 4 breaks 10 and CLOSES above (13): that is a breakout, not a sweep")

print("\n=== 3. Volume profile: POC and value area ===")
n = 120
prices = frame(high=np.full(n, 101.0), low=np.full(n, 99.0), close=np.full(n, 100.0), open=np.full(n, 100.0), volume=np.ones(n))
prices.iloc[:5, [prices.columns.get_loc(c) for c in ["high", "low"]]] = [[110, 90]] * 5
profile = rolling_volume_profile(prices, window=100, bins=20).iloc[-1]
print(f"POC {profile['poc']:.2f} | value area {profile['val']:.2f} to {profile['vah']:.2f}")
assert abs(profile["poc"] - 100) < 1.5 and profile["val"] <= profile["poc"] <= profile["vah"]
print("most volume traded near 100, so POC is near 100 and the value area surrounds it")

print("\n=== 4. No-lookahead test on random data ===")
rng = np.random.default_rng(3)
n = 1500
close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
open_ = np.r_[close[0], close[:-1]]
data = pd.DataFrame(
    {
        "open": open_,
        "high": np.maximum(open_, close) * (1 + rng.uniform(0, 0.002, n)),
        "low": np.minimum(open_, close) * (1 - rng.uniform(0, 0.002, n)),
        "close": close,
        "volume": rng.uniform(1, 10, n),
    },
    index=pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC"),
)
full = compute_features(data)
for cut in (400, 777, 1200):
    truncated = compute_features(data.iloc[:cut])
    pd.testing.assert_frame_equal(full.iloc[:cut].astype(float), truncated.astype(float), check_exact=False, rtol=1e-9, atol=1e-9)
    print(f"cut at {cut}: features for the first {cut} candles are identical with and without the future")
print(f"\nsweeps found: bull {int(full['sweep_bull'].sum())}, bear {int(full['sweep_bear'].sum())} | candles inside value area: {full['in_value_area'].mean():.0%}")
