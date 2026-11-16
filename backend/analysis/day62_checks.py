import json
import tempfile
import threading
from pathlib import Path

import numpy as np
import pandas as pd

from analysis import patterns
from analysis.backtest import random_baseline, run_backtest
from analysis.cleaning import clean_candles
from analysis.evidence import ALPHA, MIN_TRADES, decide_verdict, evaluate_strategy, jsonable, run_evidence, sharpe_report, strategy_key
from analysis.features import compute_features
from analysis.rule_builder import build_strategy
from analysis.rules import Cond, RuleStrategy, generate_rule_signals
from analysis.strategy import StrategyParams
from analysis.templates import TEMPLATES
from analysis.trial_log import TrialLog

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def make_frame(n, seed):
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.004, n) * (1 + 1.5 * (rng.random(n) < 0.03))
    close = 100 * np.exp(np.cumsum(returns))
    open_ = np.concatenate([[100.0], close[:-1]]) * (1 + rng.normal(0, 0.0007, n))
    return pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n))),
                         "low": np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n))), "close": close, "volume": rng.uniform(50, 150, n)},
                        index=pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC"))


def prepare(frame):
    cleaned, _ = clean_candles(frame, "1h")
    feats = compute_features(cleaned).dropna(subset=["ret_24", "rsi_14", "bb_pct_b", "atr_14_pct", "vol_z", "dist_poc_atr"])
    return cleaned, feats


def planted_frame(n=6000, seed=5, d=0.02):
    frame = make_frame(n, seed)
    idx = np.flatnonzero(patterns.bullish_pin(frame).to_numpy())
    idx = idx[(idx > 250) & (idx < n - 3)]
    o, h, l, c = (frame[k].to_numpy().copy() for k in ("open", "high", "low", "close"))
    for j in idx + 1:
        c[j] *= 1 + d
        h[j] = max(h[j], c[j])
        for arr in (o, h, l, c):
            arr[j + 1:] *= 1 + d
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": frame["volume"].to_numpy()}, index=frame.index)


print("the strategy key and the trial counter")
a = RuleStrategy("one name", long=Cond("bullish_pin") & Cond("trend_up"))
b = RuleStrategy("another name", long=Cond("bullish_pin") & Cond("trend_up"))
c = RuleStrategy("one name", long=Cond("bullish_pin") & Cond("trend_up"), stop_buffer_atr=0.5)
check("the key ignores the name, so renaming a strategy does not reset the count", strategy_key(a) == strategy_key(b))
check("changing any setting gives a new key", strategy_key(a) != strategy_key(c) and strategy_key(a) != strategy_key(RuleStrategy("x", long=Cond("bullish_pin"))))
with tempfile.TemporaryDirectory() as tmp:
    log = TrialLog(Path(tmp) / "t.jsonl")
    check("an empty log counts zero", log.count() == 0)
    r1 = log.record("k1", "BTCUSDT", "first", "(a)", None)
    check("the first trial is counted", r1 == {"count": 1, "new": True})
    check("the same strategy on the same symbol is not counted twice", log.record("k1", "BTCUSDT", "renamed") == {"count": 1, "new": False})
    check("the same strategy on another symbol is a new test", log.record("k1", "XAUUSD", "first") == {"count": 2, "new": True})
    check("a different strategy is a new test", log.record("k2", "BTCUSDT", "second")["count"] == 3)
    with open(Path(tmp) / "t.jsonl", "a") as f:
        f.write("this is not json\n{\"x\": 1}\n")
    check("damaged or foreign lines are ignored, not fatal", log.count() == 3)
    check("the log survives a restart (a new object reads the same file)", TrialLog(Path(tmp) / "t.jsonl").count() == 3)
    threads = [threading.Thread(target=lambda i=i: TrialLog(Path(tmp) / "t.jsonl").record(f"c{i}", "BTCUSDT", "x")) for i in range(25)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    check("25 simultaneous writers lose no entries and corrupt none", log.count() == 28, f"{log.count()} entries")
    check("a very long name is cut to 60 characters", len(TrialLog(Path(tmp) / "t2.jsonl").record("z", "BTCUSDT", "n" * 500) and TrialLog(Path(tmp) / "t2.jsonl").entries()[0]["name"]) == 60)

print("Sharpe with its warnings")
rng = np.random.default_rng(1)


def fake_trades(pnl):
    pnl = np.asarray(pnl, dtype=float)
    return pd.DataFrame({"notional": np.ones(len(pnl)), "net_ret": pnl})


noise = sharpe_report(fake_trades(rng.normal(0, 0.01, 200)), years=2.0)
check("zero-mean noise: the interval includes 0 and the warning says so", noise["ci_low"] <= 0 <= noise["ci_high"] and any("includes 0" in w for w in noise["warnings"]), f"{noise['value']:.2f} [{noise['ci_low']:.2f}, {noise['ci_high']:.2f}]")
strong = sharpe_report(fake_trades(rng.normal(0.01, 0.01, 200)), years=2.0)
check("a real edge: large Sharpe, interval above 0, no 'includes 0' warning", strong["ci_low"] > 0 and strong["value"] > 3 and not any("includes 0" in w for w in strong["warnings"]), f"{strong['value']:.1f}")
few = sharpe_report(fake_trades(rng.normal(0.01, 0.01, 12)), years=1.0)
check("fewer than 30 trades always carries a noise warning", any("mostly noise" in w for w in few["warnings"]))
check("identical trades give no Sharpe instead of infinity", sharpe_report(fake_trades([0.01] * 40), years=1.0)["value"] is None)
check("one trade gives no Sharpe", sharpe_report(fake_trades([0.01]), years=1.0)["value"] is None)
same = rng.normal(0.002, 0.01, 100)
check("Sharpe scales with sqrt(trades per year): same trades over 1 year vs 4 years differ by exactly 2x", abs(sharpe_report(fake_trades(same), years=1.0)["value"] / sharpe_report(fake_trades(same), years=4.0)["value"] - 2) < 1e-9)
check("the method is stated in the output", "per-trade" in noise["method"])

print("the verdict rules")
check("fewer than 30 trades is 'insufficient_data', never a verdict either way", decide_verdict(12, 500.0, 0.001, 3, 3)["label"] == "insufficient_data")
check("a losing strategy is 'no_edge'", decide_verdict(100, -15.0, 0.9, 1, 3)["label"] == "no_edge")
check("profitable but not significant is 'no_edge' and says why", "random entries" in " ".join(decide_verdict(100, 8.0, 0.2, 3, 3)["reasons"]))
check("profitable and significant but unstable over time is 'no_edge'", decide_verdict(100, 20.0, 0.01, 1, 3)["label"] == "no_edge")
v = decide_verdict(100, 20.0, 0.01, 3, 3)
check("passing everything is only 'promising', and the message warns it is not proof", v["label"] == "promising" and "not proof" in v["message"])
check("there is no verdict called 'confirmed' or 'profitable'", all(decide_verdict(n, bps, p, s, 3)["label"] in ("insufficient_data", "no_edge", "promising") for n in (5, 100) for bps in (-5, 20) for p in (0.001, 0.5) for s in (0, 3)))
check("a missing p-value cannot pass", decide_verdict(100, 20.0, None, 3, 3)["label"] == "no_edge")

print("evaluation on a random walk (no edge exists)")
frame = make_frame(6000, 21)
cleaned, feats = prepare(frame)
sweep = build_strategy(TEMPLATES["sweep_reversal"]["strategy"])
ev = evaluate_strategy(cleaned, feats, sweep, strategies_tried=1)
signals = generate_rule_signals(cleaned.loc[feats.index], feats, sweep)
direct = run_backtest(cleaned.loc[feats.index], signals, StrategyParams())
check("the trade count equals a direct run of the backtester", ev["result"]["trades"] == len(direct), f"{len(direct)} trades")
check("net bps equals gross bps minus the 20 bps cost", abs(ev["result"]["net_bps"] - (ev["result"]["gross_bps"] - 20)) < 1e-6)
check("the cost table is consistent with the headline number", next(r for r in ev["cost_sensitivity"] if r["cost_bps"] == 20)["net_bps"] == ev["result"]["net_bps"] and [r["net_bps"] for r in ev["cost_sensitivity"]] == sorted((r["net_bps"] for r in ev["cost_sensitivity"]), reverse=True))
means, p = random_baseline(cleaned.loc[feats.index], signals, direct, StrategyParams(), n_runs=ev["random_baseline"]["runs"], seed=0)
check("the p-value is the same as calling the random baseline directly (fixed seed, no re-rolling)", abs(p - ev["random_baseline"]["p"]) < 1e-12, f"p {p:.3f}")
check("running it twice gives the identical answer", json.dumps(evaluate_strategy(cleaned, feats, sweep, 1), sort_keys=True) == json.dumps(ev, sort_keys=True))
check("no edge is found on a random walk", ev["verdict"]["label"] in ("no_edge", "insufficient_data") and ev["result"]["net_bps"] < 10, f"{ev['verdict']['label']}, net {ev['result']['net_bps']:.1f} bps")
check("three time slices that add up to all trades", len(ev["slices"]) == 3 and sum(s["trades"] for s in ev["slices"]) == ev["result"]["trades"])
try:
    json.dumps(ev, allow_nan=False)
    check("the output serialises with allow_nan=False", True)
except ValueError:
    check("the output serialises with allow_nan=False", False)
rare = RuleStrategy("rare", long=Cond("sweep_bull") & Cond("bullish_engulfing") & Cond("clean_bar"))
few = evaluate_strategy(cleaned, feats, rare, 1)
print(f"  info: the rare strategy has {few['result']['trades']} trades on this data -> {few['verdict']['label']}")
check("a rare strategy with fewer than 30 trades is called insufficient_data", 0 < few["result"]["trades"] < MIN_TRADES and few["verdict"]["label"] == "insufficient_data")
none = evaluate_strategy(cleaned, feats, RuleStrategy("never", long=Cond("rsi_oversold") & Cond("rsi_overbought")), 1)
check("a strategy that never trades is handled without errors", none["result"]["trades"] == 0 and none["verdict"]["label"] == "insufficient_data" and none["random_baseline"] is None and none["sharpe"]["value"] is None)
check("jsonable turns NaN and infinity into null", jsonable({"a": float("nan"), "b": float("inf"), "c": np.int64(3), "d": [np.float64(1.5)]}) == {"a": None, "b": None, "c": 3, "d": [1.5]})

print("evaluation when an edge really exists (planted after every bullish pin)")
pf = planted_frame()
pc, pfeats = prepare(pf)
pin = RuleStrategy("pin long", long=Cond("bullish_pin"))
good = evaluate_strategy(pc, pfeats, pin, strategies_tried=1)
print(f"  info: {good['result']['trades']} trades, net {good['result']['net_bps']:.0f} bps/trade, p {good['random_baseline']['p']:.4f}, slices {[round(s['net_bps']) for s in good['slices']]}")
check("a planted edge is found: profitable after cost, small p, stable slices, verdict promising", good["result"]["net_bps"] > 0 and good["random_baseline"]["p"] < 0.05 and good["positive_slices"] == 3 and good["verdict"]["label"] == "promising")
many = evaluate_strategy(pc, pfeats, pin, strategies_tried=200)
check("the same result is NOT significant once 200 strategies have been tried", many["random_baseline"]["p_adjusted"] >= ALPHA and many["verdict"]["label"] == "no_edge", f"adjusted p {many['random_baseline']['p_adjusted']:.2f}, threshold {ALPHA / 200:.5f}")
check("the random-entry test gets more draws when more strategies were tried", many["random_baseline"]["runs"] > good["random_baseline"]["runs"])

print("the full evidence flow with the trial log")
with tempfile.TemporaryDirectory() as tmp:
    log = TrialLog(Path(tmp) / "t.jsonl")
    first = run_evidence(cleaned, feats, sweep, "BTCUSDT", "1h", log)
    again = run_evidence(cleaned, feats, sweep, "BTCUSDT", "1h", log)
    check("a first run is counted as a new trial", first["multiple_testing"]["strategies_tried"] == 1 and first["multiple_testing"]["new_trial"] is True)
    check("a repeat is not counted and gives the same numbers", again["multiple_testing"]["strategies_tried"] == 1 and again["multiple_testing"]["new_trial"] is False and again["result"] == first["result"] and again["random_baseline"] == first["random_baseline"])
    other = run_evidence(cleaned, feats, build_strategy(TEMPLATES["pin_bar_with_trend"]["strategy"]), "BTCUSDT", "1h", log)
    check("a second strategy raises the count and tightens the threshold", other["multiple_testing"]["strategies_tried"] == 2 and abs(other["multiple_testing"]["bonferroni_threshold"] - 0.025) < 1e-12)
    renamed = RuleStrategy("renamed", long=sweep.long, short=sweep.short, stop_mode=sweep.stop_mode, stop_buffer_atr=sweep.stop_buffer_atr)
    check("renaming a strategy does not make it a new trial", run_evidence(cleaned, feats, renamed, "BTCUSDT", "1h", log)["multiple_testing"]["strategies_tried"] == 2)
    check("the response says what the guard does not count", "not counted" in first["multiple_testing"]["note"])
    check("the response states every assumption", all(k in first["assumptions"] for k in ("cost_bps", "rr", "max_bars", "entry", "stop_vs_target_same_candle")))
    check("the response is research only", first["research_only"] is True and "not" in first["note"])

print(f"\n{results['passed']} passed, {results['failed']} failed")
raise SystemExit(1 if results["failed"] else 0)
