import numpy as np
import pandas as pd

from analysis.backtest import performance, run_backtest, simulate_trade
from analysis.strategy import StrategyParams, generate_signals

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def bars(rows):
    a = np.array(rows, dtype=float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3]


print("trade mechanics on hand-made candles (open, high, low, close)")
o, h, l, c = bars([[100, 101, 99, 100], [100, 103, 99.5, 102], [102, 106, 101, 105], [105, 106, 104, 105]])
r = simulate_trade(o, h, l, c, 1, 1, stop=98.0, rr=2.0, max_bars=24)
check("long hits target at entry + 2R", r["reason"] == "target" and abs(r["exit"] - 104.0) < 1e-9, f"exit {r['exit']}")
o, h, l, c = bars([[100, 101, 99, 100], [100, 101, 97, 99], [99, 100, 98, 99]])
r = simulate_trade(o, h, l, c, 1, 1, stop=98.0, rr=2.0, max_bars=24)
check("long stopped out at the stop price", r["reason"] == "stop" and r["exit"] == 98.0)
o, h, l, c = bars([[100, 101, 99, 100], [100, 110, 95, 100]])
r = simulate_trade(o, h, l, c, 1, 1, stop=98.0, rr=2.0, max_bars=24)
check("stop and target in the same candle: stop wins (pessimistic)", r["reason"] == "stop")
o, h, l, c = bars([[100, 101, 99, 100], [100, 101, 99.5, 100], [95, 96, 94, 95]])
r = simulate_trade(o, h, l, c, 1, 1, stop=98.0, rr=2.0, max_bars=24)
check("gap through the stop exits at the (worse) open", r["reason"] == "stop" and r["exit"] == 95.0, f"exit {r['exit']}")
o, h, l, c = bars([[100, 101, 99, 100]] + [[100, 100.5, 99.5, 100.2]] * 6)
r = simulate_trade(o, h, l, c, 1, 1, stop=98.0, rr=3.0, max_bars=4)
check("time stop exits at the close of bar max_bars", r["reason"] == "time" and r["exit_idx"] == 4)
o, h, l, c = bars([[100, 101, 99, 100], [100, 100.5, 96, 97]])
r = simulate_trade(o, h, l, c, 1, -1, stop=102.0, rr=2.0, max_bars=24)
check("short hits target below entry", r["reason"] == "target" and abs(r["exit"] - 96.0) < 1e-9, f"exit {r['exit']}")
check("stop on the wrong side of entry is rejected", simulate_trade(o, h, l, c, 1, 1, stop=105.0, rr=2.0, max_bars=24) is None)

print("backtest accounting")
idx = pd.date_range("2026-01-01", periods=8, freq="h", tz="UTC")
candles = pd.DataFrame({"open": [100] * 8, "high": [100.2] * 8, "low": [99.8] * 8, "close": [100] * 8, "volume": [1.0] * 8}, index=idx)
signals = pd.DataFrame({"side": [1, 0, 0, 0, 0, 0, 0, 0], "stop": [98.0] + [np.nan] * 7, "atr": [2.0] * 8}, index=idx)
p = StrategyParams(max_bars=3, rr=3.0, risk_frac=0.01, cost_bps=20.0)
trades = run_backtest(candles, signals, p)
t = trades.iloc[0]
check("entry is the OPEN of the candle after the signal", t["entry"] == 100.0 and t["entry_time"] == idx[1] and t["signal_time"] == idx[0])
check("a flat trade loses exactly the 20 bps cost", abs(t["net_ret"] + 0.0020) < 1e-12, f"{t['net_ret'] * 1e4:.1f} bps")
check("risk 1% with a 2% stop gives half-size position", abs(t["notional"] - 0.5) < 1e-9, f"notional {t['notional']:.2f}")
check("equity reflects notional x net return", abs(t["equity"] - (1 - 0.5 * 0.002)) < 1e-12)
tight = StrategyParams(max_bars=3, min_risk_atr=1.5)
check("risk smaller than min_risk_atr is skipped", run_backtest(candles, signals, tight).empty)
perf = performance(trades, len(candles))
check("performance reports one losing trade", perf["trades"] == 1 and perf["win_rate"] == 0.0 and abs(perf["net_bps"] + 20) < 1e-9)

print("no look-ahead in the signal rules")
rng = np.random.default_rng(3)
n = 900
close = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
frame = pd.DataFrame({"open": close * (1 + rng.normal(0, 0.001, n)), "high": close * 1.004, "low": close * 0.996, "close": close, "volume": rng.uniform(50, 150, n)},
                     index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"))
from analysis.features import compute_features

full_feats = compute_features(frame)
full = generate_signals(frame, full_feats)
cut = 600
part = generate_signals(frame.iloc[:cut], compute_features(frame.iloc[:cut]))
same = (full["side"].iloc[:cut].to_numpy() == part["side"].to_numpy()).all()
check("signals up to bar 600 are identical when the future is deleted", same, f"{int((full['side'] != 0).sum())} signals in total")

print(f"\n{results['passed']} passed, {results['failed']} failed")
raise SystemExit(1 if results["failed"] else 0)
