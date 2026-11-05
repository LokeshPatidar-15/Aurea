import numpy as np
import pandas as pd

from analysis.strategy import StrategyParams


def simulate_trade(open_, high, low, close, i_entry: int, side: int, stop: float, rr: float, max_bars: int):
    entry = float(open_[i_entry])
    risk = side * (entry - stop)
    if not np.isfinite(risk) or risk <= 0:
        return None
    target = entry + side * rr * risk
    last = min(i_entry + max_bars - 1, len(open_) - 1)
    for j in range(i_entry, last + 1):
        if side == 1:
            gapped = j > i_entry and open_[j] <= stop
            if gapped or low[j] <= stop:
                return {"exit_idx": j, "exit": float(open_[j]) if gapped else stop, "reason": "stop", "entry": entry, "risk": risk}
            if high[j] >= target:
                return {"exit_idx": j, "exit": target, "reason": "target", "entry": entry, "risk": risk}
        else:
            gapped = j > i_entry and open_[j] >= stop
            if gapped or high[j] >= stop:
                return {"exit_idx": j, "exit": float(open_[j]) if gapped else stop, "reason": "stop", "entry": entry, "risk": risk}
            if low[j] <= target:
                return {"exit_idx": j, "exit": target, "reason": "target", "entry": entry, "risk": risk}
    reason = "time" if last == i_entry + max_bars - 1 else "end"
    return {"exit_idx": last, "exit": float(close[last]), "reason": reason, "entry": entry, "risk": risk}


def run_backtest(cleaned: pd.DataFrame, signals: pd.DataFrame, p: StrategyParams = StrategyParams()) -> pd.DataFrame:
    o, h, l, c = (cleaned[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    side, stop, atr = signals["side"].to_numpy(), signals["stop"].to_numpy(), signals["atr"].to_numpy()
    index = cleaned.index
    rows, equity, next_free = [], 1.0, 0
    for i in range(len(cleaned) - 1):
        if i < next_free or side[i] == 0:
            continue
        entry_open = o[i + 1]
        risk_atr = side[i] * (entry_open - stop[i]) / atr[i]
        if not (p.min_risk_atr <= risk_atr <= p.max_risk_atr):
            continue
        result = simulate_trade(o, h, l, c, i + 1, int(side[i]), float(stop[i]), p.rr, p.max_bars)
        if result is None:
            continue
        entry, risk = result["entry"], result["risk"]
        gross = side[i] * (result["exit"] - entry) / entry
        net = gross - p.cost_bps / 10_000
        risk_pct = risk / entry
        notional = min(p.risk_frac / risk_pct, p.max_leverage)
        equity *= 1 + notional * net
        rows.append({
            "signal_time": index[i], "entry_time": index[i + 1], "exit_time": index[result["exit_idx"]],
            "side": int(side[i]), "entry": entry, "stop": float(stop[i]), "exit": result["exit"], "reason": result["reason"],
            "bars": result["exit_idx"] - i, "risk_pct": risk_pct, "risk_atr": risk_atr,
            "gross_ret": gross, "net_ret": net, "net_R": net / risk_pct, "notional": notional, "equity": equity,
        })
        next_free = result["exit_idx"] + p.cooldown
    return pd.DataFrame(rows)


def performance(trades: pd.DataFrame, n_bars: int) -> dict:
    if trades.empty:
        return {"trades": 0}
    pnl = trades["notional"] * trades["net_ret"]
    wins, losses = pnl[pnl > 0].sum(), -pnl[pnl < 0].sum()
    curve = np.concatenate([[1.0], trades["equity"].to_numpy()])
    drawdown = curve / np.maximum.accumulate(curve) - 1
    return {
        "trades": int(len(trades)),
        "win_rate": float((trades["net_ret"] > 0).mean()),
        "gross_bps": float(trades["gross_ret"].mean() * 1e4),
        "net_bps": float(trades["net_ret"].mean() * 1e4),
        "expectancy_R": float(trades["net_R"].mean()),
        "profit_factor": float(wins / losses) if losses > 0 else float("inf"),
        "total_return": float(curve[-1] - 1),
        "max_drawdown": float(drawdown.min()),
        "exposure": float(trades["bars"].sum() / n_bars),
        "target_share": float((trades["reason"] == "target").mean()),
        "stop_share": float((trades["reason"] == "stop").mean()),
    }


def random_baseline(cleaned: pd.DataFrame, signals: pd.DataFrame, trades: pd.DataFrame, p: StrategyParams = StrategyParams(), n_runs: int = 300, seed: int = 0, warmup: int = 200):
    o, h, l, c = (cleaned[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    atr = signals["atr"].to_numpy()
    risk_atr = trades["risk_atr"].to_numpy()
    rng = np.random.default_rng(seed)
    candidates = np.flatnonzero(np.isfinite(atr))
    candidates = candidates[(candidates >= warmup) & (candidates < len(o) - 1)]
    means = np.empty(n_runs)
    for run in range(n_runs):
        picks = rng.choice(candidates, size=len(risk_atr))
        sides = rng.choice([-1, 1], size=len(risk_atr))
        nets = []
        for i, side, r in zip(picks, sides, risk_atr):
            entry = o[i + 1]
            stop = entry - side * r * atr[i]
            result = simulate_trade(o, h, l, c, i + 1, int(side), stop, p.rr, p.max_bars)
            if result is not None:
                nets.append(side * (result["exit"] - entry) / entry - p.cost_bps / 10_000)
        means[run] = np.mean(nets) * 1e4
    actual = trades["net_ret"].mean() * 1e4
    return means, float((np.sum(means >= actual) + 1) / (n_runs + 1))
