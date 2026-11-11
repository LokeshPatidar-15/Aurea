import numpy as np
import pandas as pd

WARMUP = 200


def forward_returns(cleaned: pd.DataFrame, horizon: int) -> np.ndarray:
    if horizon < 1:
        raise ValueError("horizon must be at least 1 candle")
    o = cleaned["open"].to_numpy(dtype=float)
    c = cleaned["close"].to_numpy(dtype=float)
    out = np.full(len(c), np.nan)
    last = len(c) - horizon
    if last > 0:
        i = np.arange(last)
        out[:last] = c[i + horizon] / o[i + 1] - 1
    return out


def pattern_edge(cleaned: pd.DataFrame, flags, direction: int, horizon: int, cost_bps: float = 20.0, n_draws: int = 3000, seed: int = 0) -> dict:
    fr = forward_returns(cleaned, horizon) * direction
    flags = np.asarray(flags, dtype=bool)
    valid = np.isfinite(fr)
    idx = np.flatnonzero(flags & valid)
    idx = idx[idx >= WARMUP]
    pool = np.flatnonzero(valid)
    pool = pool[pool >= WARMUP]
    if len(idx) < 10 or len(pool) < len(idx):
        return {"n": int(len(idx)), "gross_bps": np.nan, "net_bps": np.nan, "baseline_bps": np.nan, "p": np.nan}
    observed = fr[idx].mean()
    rng = np.random.default_rng(seed)
    draws = fr[rng.choice(pool, size=(n_draws, len(idx)))].mean(axis=1)
    p = (1 + int((draws >= observed).sum())) / (1 + n_draws)
    return {"n": int(len(idx)), "gross_bps": float(observed * 1e4), "net_bps": float(observed * 1e4 - cost_bps),
            "baseline_bps": float(draws.mean() * 1e4), "p": float(p)}
