import numpy as np
import pandas as pd


def find_swings(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    window = 2 * n + 1
    roll_max = df["high"].rolling(window, center=True).max()
    roll_min = df["low"].rolling(window, center=True).min()
    out = pd.DataFrame(index=df.index)
    out["is_swing_high"] = (df["high"] == roll_max) & roll_max.notna()
    out["is_swing_low"] = (df["low"] == roll_min) & roll_min.notna()
    return out


def confirmed_swing_levels(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    swings = find_swings(df, n)
    high_level = df["high"].where(swings["is_swing_high"]).shift(n)
    low_level = df["low"].where(swings["is_swing_low"]).shift(n)
    out = pd.DataFrame(index=df.index)
    out["last_swing_high"] = high_level.ffill()
    out["last_swing_low"] = low_level.ffill()
    return out


def detect_sweeps(df: pd.DataFrame, levels: pd.DataFrame) -> pd.DataFrame:
    prev_high = levels["last_swing_high"].shift(1)
    prev_low = levels["last_swing_low"].shift(1)
    out = pd.DataFrame(index=df.index)
    out["sweep_bear"] = (df["high"] > prev_high) & (df["close"] < prev_high)
    out["sweep_bull"] = (df["low"] < prev_low) & (df["close"] > prev_low)
    return out


def _profile_one(high, low, close, volume, bins: int, value_area: float):
    lo, hi = low.min(), high.max()
    if not (np.isfinite(lo) and np.isfinite(hi) and hi > lo):
        return np.nan, np.nan, np.nan
    typical = (high + low + close) / 3
    hist, edges = np.histogram(typical, bins=bins, range=(lo, hi), weights=volume)
    total = hist.sum()
    if total <= 0:
        return np.nan, np.nan, np.nan
    centers = (edges[:-1] + edges[1:]) / 2
    poc = int(hist.argmax())
    left = right = poc
    covered = hist[poc]
    while covered < value_area * total and (left > 0 or right < bins - 1):
        below = hist[left - 1] if left > 0 else -1.0
        above = hist[right + 1] if right < bins - 1 else -1.0
        if above >= below:
            right += 1
            covered += hist[right]
        else:
            left -= 1
            covered += hist[left]
    return centers[poc], edges[right + 1], edges[left]


def rolling_volume_profile(df: pd.DataFrame, window: int = 100, bins: int = 24, value_area: float = 0.7) -> pd.DataFrame:
    high, low, close, volume = (df[c].to_numpy(dtype=float) for c in ["high", "low", "close", "volume"])
    n = len(df)
    result = np.full((n, 3), np.nan)
    for i in range(window - 1, n):
        s = slice(i - window + 1, i + 1)
        result[i] = _profile_one(high[s], low[s], close[s], volume[s], bins, value_area)
    return pd.DataFrame(result, index=df.index, columns=["poc", "vah", "val"])
