import numpy as np
import pandas as pd

from analysis.indicators import atr, bollinger, ema, macd, rsi
from analysis.liquidity import confirmed_swing_levels, detect_sweeps, rolling_volume_profile

SWING_N = 5
PROFILE_WINDOW = 100
FEATURE_COLUMNS = [
    "ret_1", "ret_4", "ret_24", "rsi_14", "macd_hist", "bb_pct_b", "bb_width",
    "ema_20_dist", "atr_14_pct", "vol_z", "hour_utc", "day_of_week",
    "dist_swing_high_atr", "dist_swing_low_atr", "sweep_bull", "sweep_bear",
    "dist_poc_atr", "in_value_area", "is_filled", "is_outlier",
]


def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"]
    feats = pd.DataFrame(index=df.index)
    log_close = np.log(close)
    feats["ret_1"] = log_close.diff(1)
    feats["ret_4"] = log_close.diff(4)
    feats["ret_24"] = log_close.diff(24)
    feats["rsi_14"] = rsi(close, 14)
    feats["macd_hist"] = macd(close)["hist"] / close
    bb = bollinger(close)
    feats["bb_pct_b"] = bb["bb_pct_b"]
    feats["bb_width"] = bb["bb_width"]
    feats["ema_20_dist"] = (close - ema(close, 20)) / close
    atr14 = atr(df["high"], df["low"], close, 14)
    feats["atr_14_pct"] = atr14 / close
    vol = df["volume"]
    feats["vol_z"] = (vol - vol.rolling(50).mean()) / vol.rolling(50).std(ddof=0).replace(0, np.nan)
    feats["hour_utc"] = df.index.hour
    feats["day_of_week"] = df.index.dayofweek

    levels = confirmed_swing_levels(df, SWING_N)
    sweeps = detect_sweeps(df, levels)
    feats["dist_swing_high_atr"] = (levels["last_swing_high"] - close) / atr14
    feats["dist_swing_low_atr"] = (close - levels["last_swing_low"]) / atr14
    feats["sweep_bull"] = sweeps["sweep_bull"]
    feats["sweep_bear"] = sweeps["sweep_bear"]

    profile = rolling_volume_profile(df, PROFILE_WINDOW)
    feats["dist_poc_atr"] = (close - profile["poc"]) / atr14
    feats["in_value_area"] = (close <= profile["vah"]) & (close >= profile["val"])
    feats.loc[profile["poc"].isna(), "in_value_area"] = False

    feats["is_filled"] = df.get("is_filled", False)
    feats["is_outlier"] = df.get("is_outlier", False)
    return feats[FEATURE_COLUMNS]
