import itertools

import numpy as np
import pandas as pd

from analysis.backtest import performance, random_baseline, run_backtest
from analysis.ml_features import load_inputs
from analysis.strategy import StrategyParams, generate_signals

SYMBOLS = ("BTCUSDT", "XAUUSD", "EURUSD")
P = StrategyParams()

print("=== 1. The rules (all decided at the CLOSE of the signal candle, entry at the NEXT candle's open) ===")
print("long : liquidity sweep of the last swing low (wick below, close back above) + volume not below average + EMA50 > EMA200")
print("short: mirror image at the last swing high, with EMA50 < EMA200")
print(f"stop : sweep candle extreme -/+ {P.stop_buffer_atr} ATR | target: {P.rr}R | time stop: {P.max_bars} bars | skip if risk is outside {P.min_risk_atr}-{P.max_risk_atr} ATR")
print(f"size : risk {P.risk_frac:.0%} of equity per trade, leverage capped at {P.max_leverage:.0f}x | cost {P.cost_bps:.0f} bps round trip | one position at a time")

data, results = {}, {}
print("\n=== 2. Results per symbol (1h, whole history, no parameters fitted) ===")
rows = []
for symbol in SYMBOLS:
    feats, cleaned = load_inputs(symbol, "1h")
    cleaned = cleaned.loc[feats.index]
    signals = generate_signals(cleaned, feats, P)
    trades = run_backtest(cleaned, signals, P)
    data[symbol] = (cleaned, feats, signals, trades)
    perf = performance(trades, len(cleaned))
    results[symbol] = perf
    longs, shorts = int((signals["side"] == 1).sum()), int((signals["side"] == -1).sum())
    rows.append({
        "symbol": symbol, "long/short signals": f"{longs}/{shorts}", "trades": perf["trades"],
        "win rate": perf.get("win_rate", np.nan), "gross bps": perf.get("gross_bps", np.nan), "net bps": perf.get("net_bps", np.nan),
        "expect. R": perf.get("expectancy_R", np.nan), "profit factor": perf.get("profit_factor", np.nan),
        "return": perf.get("total_return", np.nan), "max DD": perf.get("max_drawdown", np.nan),
    })
table = pd.DataFrame(rows)
print(table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
print("gross bps = before the 20 bps cost. net bps = after. expectancy R = average profit in units of the initial risk")

print("\n=== 3. Is it better than random entries with the same stops and targets? ===")
for symbol in SYMBOLS:
    cleaned, feats, signals, trades = data[symbol]
    if len(trades) < 10:
        print(f"{symbol:8} only {len(trades)} trades, too few to test")
        continue
    means, p_value = random_baseline(cleaned, signals, trades, P, n_runs=300)
    actual = trades["net_ret"].mean() * 1e4
    print(f"{symbol:8} strategy {actual:6.1f} bps/trade | random entries: median {np.median(means):6.1f}, 5%-95% range {np.percentile(means, 5):6.1f} to {np.percentile(means, 95):6.1f} | p = {p_value:.3f}")
print("p is the share of random runs that did as well. A small p (under 0.05) means the entry rule adds something. A large p means the stops/targets and luck explain the result")

print("\n=== 4. Stability: BTCUSDT in three time slices ===")
cleaned, feats, signals, trades = data["BTCUSDT"]
if len(trades) >= 6:
    edges = np.linspace(0, len(trades), 4).astype(int)
    for k in range(3):
        part = trades.iloc[edges[k]:edges[k + 1]]
        print(f"  slice {k + 1}: {part['entry_time'].iloc[0]:%Y-%m-%d} to {part['exit_time'].iloc[-1]:%Y-%m-%d} | {len(part):3} trades | net {part['net_ret'].mean() * 1e4:6.1f} bps/trade | win rate {(part['net_ret'] > 0).mean():.2f}")
print("a real edge shows up in every slice. One good slice and two bad ones is luck")

print("\n=== 5. Robustness grid on BTCUSDT (we look at the SHAPE, we do not pick the best cell) ===")
cleaned, feats, _, _ = data["BTCUSDT"]
grid = []
for rr, vol_min, trend in itertools.product((1.5, 2.0, 3.0), (0.0, 0.5, 1.0), ("with", "none")):
    params = StrategyParams(rr=rr, vol_min=vol_min, trend=trend)
    t = run_backtest(cleaned, generate_signals(cleaned, feats, params), params)
    grid.append({"rr": rr, "vol_min": vol_min, "trend": trend, "trades": len(t), "net bps": t["net_ret"].mean() * 1e4 if len(t) else np.nan,
                 "win rate": (t["net_ret"] > 0).mean() if len(t) else np.nan})
grid = pd.DataFrame(grid)
print(grid.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
positive = int((grid["net bps"] > 0).sum())
print(f"{positive} of {len(grid)} parameter cells have positive net bps")
print("trying 18 settings and keeping the winner would overfit. If only a few cells are positive and they are scattered, the strategy has no stable edge")
