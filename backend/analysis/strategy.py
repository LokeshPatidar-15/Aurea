from dataclasses import dataclass

import numpy as np
import pandas as pd

from analysis.indicators import ema


@dataclass(frozen=True)
class StrategyParams:
    rr: float = 2.0
    stop_buffer_atr: float = 0.25
    min_risk_atr: float = 0.5
    max_risk_atr: float = 3.0
    vol_min: float = 0.0
    trend: str = "with"
    max_bars: int = 24
    cooldown: int = 1
    risk_frac: float = 0.01
    max_leverage: float = 1.0
    cost_bps: float = 20.0


def generate_signals(cleaned: pd.DataFrame, feats: pd.DataFrame, p: StrategyParams = StrategyParams()) -> pd.DataFrame:
    close = cleaned["close"]
    atr = feats["atr_14_pct"] * close
    fast, slow = ema(close, 50), ema(close, 200)
    trend_up = (fast > slow).fillna(False)
    trend_down = (fast < slow).fillna(False)
    clean_bar = ~(feats["is_filled"].astype(bool) | feats["is_outlier"].astype(bool))
    volume_ok = (feats["vol_z"] >= p.vol_min).fillna(False)

    long_setup = feats["sweep_bull"].astype(bool) & volume_ok & clean_bar
    short_setup = feats["sweep_bear"].astype(bool) & volume_ok & clean_bar
    if p.trend == "with":
        long_setup &= trend_up
        short_setup &= trend_down
    both = long_setup & short_setup
    long_setup &= ~both
    short_setup &= ~both

    out = pd.DataFrame(index=cleaned.index)
    out["side"] = np.where(long_setup, 1, np.where(short_setup, -1, 0))
    out["stop"] = np.where(long_setup, cleaned["low"] - p.stop_buffer_atr * atr, np.where(short_setup, cleaned["high"] + p.stop_buffer_atr * atr, np.nan))
    out["atr"] = atr
    out.loc[~atr.notna(), "side"] = 0
    return out
