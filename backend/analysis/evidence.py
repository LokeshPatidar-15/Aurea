import hashlib
import json
import math

import numpy as np
import pandas as pd

from analysis.backtest import performance, random_baseline, run_backtest
from analysis.rules import RuleStrategy, describe, generate_rule_signals
from analysis.strategy import StrategyParams

PARAMS = StrategyParams()
MIN_TRADES = 30
ALPHA = 0.05
COSTS = (0, 10, 20, 30, 40)


def strategy_key(strategy: RuleStrategy) -> str:
    d = strategy.to_dict()
    d.pop("name")
    d["_assumptions"] = {"rr": PARAMS.rr, "max_bars": PARAMS.max_bars, "v": 1}
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]


def jsonable(x):
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, (float, np.floating)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, pd.Timestamp):
        return x.isoformat()
    return x


def time_slices(trades: pd.DataFrame, parts: int = 3) -> list:
    if len(trades) < 2 * parts:
        return []
    edges = np.linspace(0, len(trades), parts + 1).astype(int)
    out = []
    for k in range(parts):
        part = trades.iloc[edges[k]:edges[k + 1]]
        out.append({"start": part["entry_time"].iloc[0].isoformat(), "end": part["exit_time"].iloc[-1].isoformat(), "trades": int(len(part)),
                    "net_bps": float(part["net_ret"].mean() * 1e4), "win_rate": float((part["net_ret"] > 0).mean())})
    return out


def sharpe_report(trades: pd.DataFrame, years: float, n_boot: int = 1000, seed: int = 0) -> dict:
    method = "per-trade return (size x net return) mean/std, scaled by sqrt(trades per year). Not a daily-return Sharpe."
    out = {"value": None, "ci_low": None, "ci_high": None, "method": method, "warnings": []}
    n = len(trades)
    if n < 2 or not years or years <= 0:
        out["warnings"].append("fewer than 2 trades: Sharpe cannot be computed")
        return out
    pnl = (trades["notional"] * trades["net_ret"]).to_numpy(dtype=float)
    if pnl.std(ddof=1) == 0:
        out["warnings"].append("all trades have the same result: Sharpe is undefined")
        return out
    scale = math.sqrt(n / years)
    out["value"] = float(pnl.mean() / pnl.std(ddof=1) * scale)
    rng = np.random.default_rng(seed)
    samples = pnl[rng.integers(0, n, size=(n_boot, n))]
    sds = samples.std(axis=1, ddof=1)
    vals = np.where(sds > 0, samples.mean(axis=1) / np.where(sds > 0, sds, 1) * scale, np.nan)
    out["ci_low"], out["ci_high"] = float(np.nanpercentile(vals, 5)), float(np.nanpercentile(vals, 95))
    if n < MIN_TRADES:
        out["warnings"].append(f"only {n} trades (fewer than {MIN_TRADES}): this Sharpe is mostly noise")
    if out["ci_low"] <= 0 <= out["ci_high"]:
        out["warnings"].append("the 90% bootstrap interval includes 0: the data cannot tell this apart from no edge")
    return out


def decide_verdict(n_trades: int, net_bps, p_adjusted, positive_slices: int, n_slices: int) -> dict:
    if n_trades < MIN_TRADES:
        return {"label": "insufficient_data", "reasons": [f"only {n_trades} trades; at least {MIN_TRADES} are needed before any number means anything"],
                "message": "Too few trades to judge. Not evidence for or against."}
    reasons = []
    if not (net_bps is not None and net_bps > 0):
        reasons.append("average trade is not profitable after cost")
    if p_adjusted is None or not (p_adjusted < ALPHA):
        shown = "n/a" if p_adjusted is None else f"{p_adjusted:.3f}"
        reasons.append(f"not significantly better than random entries after correcting for the strategies tried (adjusted p = {shown}, needs < {ALPHA})")
    if n_slices >= 3 and positive_slices < 2:
        reasons.append(f"result is not stable over time (only {positive_slices} of {n_slices} time slices are profitable)")
    if reasons:
        return {"label": "no_edge", "reasons": reasons, "message": "No evidence of a tradable edge on this data."}
    return {"label": "promising", "reasons": [], "message": "Passes this in-sample screen only. This is not proof: it still needs forward testing (paper trading) and is not trading advice."}


def evaluate_strategy(cleaned: pd.DataFrame, feats: pd.DataFrame, strategy: RuleStrategy, strategies_tried: int = 1, params: StrategyParams = PARAMS, seed: int = 0) -> dict:
    cleaned = cleaned.loc[feats.index]
    signals = generate_rule_signals(cleaned, feats, strategy)
    trades = run_backtest(cleaned, signals, params)
    k = max(1, int(strategies_tried))
    years = (cleaned.index[-1] - cleaned.index[0]).total_seconds() / (365.25 * 86400)
    perf = performance(trades, len(cleaned))
    n_trades = int(len(trades))
    baseline, p_adjusted = None, None
    if n_trades >= 10:
        n_runs = min(2000, max(300, 40 * k))
        means, p = random_baseline(cleaned, signals, trades, params, n_runs=n_runs, seed=seed)
        p_adjusted = min(1.0, p * k)
        baseline = {"runs": n_runs, "median_bps": float(np.median(means)), "p05_bps": float(np.percentile(means, 5)), "p95_bps": float(np.percentile(means, 95)),
                    "p": p, "p_adjusted": p_adjusted, "smallest_possible_p": 1 / (n_runs + 1)}
    slices = time_slices(trades)
    positive = sum(1 for s in slices if s["net_bps"] > 0)
    out = {
        "data": {"first": cleaned.index[0].isoformat(), "last": cleaned.index[-1].isoformat(), "candles": int(len(cleaned)), "years": float(years)},
        "signals": {"long": int((signals["side"] == 1).sum()), "short": int((signals["side"] == -1).sum())},
        "result": perf,
        "trades_per_year": float(n_trades / years) if years > 0 else None,
        "cost_sensitivity": [{"cost_bps": c, "net_bps": float(perf["gross_bps"] - c)} for c in COSTS] if n_trades else [],
        "random_baseline": baseline,
        "slices": slices,
        "positive_slices": positive,
        "sharpe": sharpe_report(trades, years),
        "verdict": decide_verdict(n_trades, perf.get("net_bps"), p_adjusted, positive, len(slices)),
        "assumptions": {"cost_bps": params.cost_bps, "rr": params.rr, "max_bars": params.max_bars, "risk_per_trade": params.risk_frac, "max_leverage": params.max_leverage,
                        "entry": "next candle open", "positions": "one at a time", "stop_vs_target_same_candle": "stop wins", "gaps": "filled at the worse open"},
    }
    return jsonable(out)


def run_evidence(cleaned: pd.DataFrame, feats: pd.DataFrame, strategy: RuleStrategy, symbol: str, timeframe: str, log) -> dict:
    key = strategy_key(strategy)
    trial = log.record(key, symbol, strategy.name, describe(strategy.long) if strategy.long else None, describe(strategy.short) if strategy.short else None)
    k = trial["count"]
    out = evaluate_strategy(cleaned, feats, strategy, strategies_tried=k)
    out.update({
        "symbol": symbol, "timeframe": timeframe, "strategy_name": strategy.name, "strategy_key": key,
        "long_text": describe(strategy.long) if strategy.long else None, "short_text": describe(strategy.short) if strategy.short else None,
        "stop_mode": strategy.stop_mode, "stop_buffer_atr": strategy.stop_buffer_atr,
        "multiple_testing": {"strategies_tried": k, "new_trial": trial["new"], "bonferroni_threshold": ALPHA / k,
                             "note": "Counts distinct strategy x symbol tests run through this system. Earlier research on the same data (Day 54, Day 60) is not counted, so this guard is lenient. Re-running the same test does not change the count or the p-value."},
        "research_only": True,
        "note": "In-sample backtest on stored history. Passing it would still not be proof and nothing here is trading advice.",
    })
    return jsonable(out)
