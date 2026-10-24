import numpy as np
import pandas as pd


def triple_barrier(cleaned: pd.DataFrame, atr_pct: pd.Series, horizon: int = 12, k: float = 1.0) -> pd.DataFrame:
    high = cleaned["high"].to_numpy(dtype=float)
    low = cleaned["low"].to_numpy(dtype=float)
    close = cleaned["close"].to_numpy(dtype=float)
    width = (atr_pct.reindex(cleaned.index) * k).to_numpy(dtype=float)
    times = cleaned.index
    n = len(cleaned)

    label = np.full(n, np.nan)
    ret = np.full(n, np.nan)
    exit_pos = np.full(n, -1)

    for i in range(n - horizon):
        w = width[i]
        if not np.isfinite(w) or w <= 0:
            continue
        entry = close[i]
        window = slice(i + 1, i + 1 + horizon)
        up_hits = np.flatnonzero(high[window] >= entry * (1 + w))
        dn_hits = np.flatnonzero(low[window] <= entry * (1 - w))
        first_up = up_hits[0] if len(up_hits) else horizon
        first_dn = dn_hits[0] if len(dn_hits) else horizon

        if first_up == horizon and first_dn == horizon:
            label[i], exit_pos[i] = 0, i + horizon
            ret[i] = close[i + horizon] / entry - 1
        elif first_up < first_dn:
            label[i], exit_pos[i], ret[i] = 1, i + 1 + first_up, w
        elif first_dn < first_up:
            label[i], exit_pos[i], ret[i] = -1, i + 1 + first_dn, -w
        else:
            exit_at = i + 1 + first_up
            label[i], exit_pos[i] = 0, exit_at
            ret[i] = close[exit_at] / entry - 1

    out = pd.DataFrame({"label": label, "ret": ret}, index=times)
    valid = out["label"].notna()
    exit_time = pd.Series(pd.NaT, index=times, dtype="datetime64[ns, UTC]")
    exit_time[valid.to_numpy()] = times[exit_pos[valid.to_numpy()]]
    out["exit_time"] = exit_time
    out["bars_held"] = np.where(valid, exit_pos - np.arange(n), np.nan)
    return out
