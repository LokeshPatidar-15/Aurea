import numpy as np
import pandas as pd

from analysis import patterns
from analysis.features import compute_features
from analysis.backtest import run_backtest
from analysis.cleaning import clean_candles
from analysis.pattern_stats import forward_returns, pattern_edge
from analysis.rules import (CONDITIONS, And, Cond, Context, Not, Or, RuleError, RuleStrategy, UnknownCondition, condition_names, describe, evaluate,
                            from_dict, generate_rule_signals, names_used, to_dict)
from analysis.strategy import StrategyParams, generate_signals

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def candles(rows):
    a = np.array(rows, dtype=float)
    return pd.DataFrame({"open": a[:, 0], "high": a[:, 1], "low": a[:, 2], "close": a[:, 3]}, index=pd.date_range("2026-01-01", periods=len(a), freq="h", tz="UTC"))


def last(fn, rows, **kw):
    return bool(fn(candles(rows), **kw).iloc[-1])


print("candlestick patterns on hand-made candles (open, high, low, close)")
bear = [10.0, 10.2, 9.0, 9.2]
check("bullish engulfing: big green body covers the previous red body", last(patterns.bullish_engulfing, [bear, [9.1, 10.6, 9.0, 10.5]]))
check("not engulfing when the close stays below the previous open", not last(patterns.bullish_engulfing, [bear, [9.1, 10.0, 9.0, 9.9]]))
check("not engulfing when the new candle is red", not last(patterns.bullish_engulfing, [bear, [10.5, 10.6, 9.0, 9.1]]))
check("a doji-like body is not an engulfing candle", not last(patterns.bullish_engulfing, [bear, [9.1, 10.6, 8.0, 9.15]]))
bull = [9.2, 10.2, 9.0, 10.0]
check("bearish engulfing: big red body covers the previous green body", last(patterns.bearish_engulfing, [bull, [10.1, 10.2, 8.9, 9.1]]))
check("a candle cannot be both bullish and bearish engulfing", not (last(patterns.bullish_engulfing, [bull, [10.1, 10.2, 8.9, 9.1]]) and last(patterns.bearish_engulfing, [bull, [10.1, 10.2, 8.9, 9.1]])))
check("bullish pin (hammer): long lower wick, tiny body", last(patterns.bullish_pin, [[10.0, 10.1, 8.0, 10.05]]))
check("a candle with a long upper wick is not a hammer", not last(patterns.bullish_pin, [[10.0, 12.0, 9.95, 10.05]]))
check("bearish pin (shooting star): long upper wick, tiny body", last(patterns.bearish_pin, [[10.0, 12.0, 9.9, 9.95]]))
check("a big-bodied candle is not a pin bar", not last(patterns.bullish_pin, [[8.5, 10.1, 8.0, 10.0]]))
check("inside bar: range fully inside the previous range", last(patterns.inside_bar, [[10, 12, 8, 11], [10.5, 11.5, 8.5, 11.0]]))
check("touching the previous high is not an inside bar", not last(patterns.inside_bar, [[10, 12, 8, 11], [10.5, 12.0, 8.5, 11.0]]))
flat = candles([[10, 10, 10, 10], [10, 10, 10, 10]])
check("a zero-range candle is never a pattern", not patterns.detect_all(flat).to_numpy().any())
check("the first candle has no previous candle, so no two-candle pattern", not patterns.bullish_engulfing(candles([[9.1, 10.6, 9.0, 10.5]])).iloc[0] and not patterns.inside_bar(candles([[10, 11, 9, 10]])).iloc[0])
nan_rows = candles([bear, [9.1, 10.6, 9.0, 10.5]])
nan_rows.iloc[1, 0] = np.nan
check("missing prices give False, not an error", not patterns.detect_all(nan_rows).iloc[1].any())
try:
    patterns.detect_all(pd.DataFrame({"open": [1.0]}))
    check("missing columns are reported", False)
except ValueError:
    check("missing columns are reported", True)

print("patterns use only the past")
rng = np.random.default_rng(7)
n = 1500
returns = rng.normal(0, 0.004, n) * (1 + 1.5 * (rng.random(n) < 0.03))
close = 100 * np.exp(np.cumsum(returns))
open_ = np.concatenate([[100.0], close[:-1]]) * (1 + rng.normal(0, 0.0007, n))
frame = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n))),
                      "low": np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n))), "close": close, "volume": rng.uniform(50, 150, n)},
                     index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"))
full = patterns.detect_all(frame)
same = all((patterns.detect_all(frame.iloc[: i + 1]).iloc[-1] == full.iloc[i]).all() for i in range(5, n, 37))
check("the flag at a candle is the same whether or not later candles exist", same)
scaled = patterns.detect_all(frame[["open", "high", "low", "close"]] * 7.3)
check("flags do not depend on the price scale (BTC at 60000 or EUR at 1.1)", (scaled == full).all().all())
rates = full.mean()
print("  info: share of candles flagged: " + ", ".join(f"{k} {v:.1%}" for k, v in rates.items()))
check("every pattern fires sometimes but not constantly", ((rates > 0.001) & (rates < 0.35)).all())

print("rule engine: conditions and AND / OR / NOT")
cleaned, _ = clean_candles(frame, "1h")
feats = compute_features(cleaned)
ctx = Context(cleaned, feats)
all_ok = True
for name in condition_names():
    s = evaluate(Cond(name), ctx)
    all_ok &= bool(s.dtype == bool and len(s) == len(cleaned) and not s.isna().any())
check(f"all {len(CONDITIONS)} conditions give a clean true/false series", all_ok)
a, b = Cond("sweep_bull"), Cond("volume_ok")
sa, sb = evaluate(a, ctx), evaluate(b, ctx)
check("AND, OR and NOT behave like boolean logic", (evaluate(a & b, ctx) == (sa & sb)).all() and (evaluate(a | b, ctx) == (sa | sb)).all() and (evaluate(~a, ctx) == ~sa).all())
check("adding an AND never adds signals; adding an OR never removes any", evaluate(a & b, ctx).sum() <= sa.sum() <= evaluate(a | b, ctx).sum())
check("operators flatten: (a & b) & c has three children", len((a & b & Cond("trend_up")).children) == 3)
expr = (Cond("sweep_bull") & Cond("bullish_engulfing")) | ~Cond("inside_bar")
check("a rule can be described in words", describe(expr) == "((sweep_bull AND bullish_engulfing) OR NOT inside_bar)", describe(expr))
check("the conditions a rule uses are listed", names_used(expr) == {"sweep_bull", "bullish_engulfing", "inside_bar"})
try:
    evaluate(Cond("moon_phase"), ctx)
    check("an unknown condition is refused with the valid names", False)
except UnknownCondition as exc:
    check("an unknown condition is refused with the valid names", "sweep_bull" in str(exc))
try:
    And(())
    check("an empty AND is refused", False)
except RuleError:
    check("an empty AND is refused", True)

print("rules as data (the base of the Day 61 builder)")
check("a rule survives to_dict -> from_dict", from_dict(to_dict(expr)) == expr, str(to_dict(expr)))
bad = [{"all": []}, {"xor": ["sweep_bull"]}, {"all": "sweep_bull"}, {"all": ["sweep_bull"], "any": ["inside_bar"]}, 5, ["sweep_bull"], "no_such_condition", {"not": {"not": {"not": None}}}]
refused = 0
for item in bad:
    try:
        from_dict(item)
    except (RuleError, UnknownCondition):
        refused += 1
check("malformed or unknown rules are refused", refused == len(bad), f"{refused}/{len(bad)}")
deep = "sweep_bull"
for _ in range(12):
    deep = {"not": deep}
try:
    from_dict(deep)
    check("absurdly deep rules are refused", False)
except RuleError:
    check("absurdly deep rules are refused", True)

print("a rule strategy reproduces the Day 54 strategy exactly")
day54 = RuleStrategy("sweep reversal", long=Cond("sweep_bull") & Cond("volume_ok") & Cond("trend_up") & Cond("clean_bar"),
                     short=Cond("sweep_bear") & Cond("volume_ok") & Cond("trend_down") & Cond("clean_bar"), stop_mode="candle", stop_buffer_atr=0.25)
mine = generate_rule_signals(cleaned, feats, day54)
theirs = generate_signals(cleaned, feats, StrategyParams())
check("same side on every candle", (mine["side"].to_numpy() == theirs["side"].to_numpy()).all(), f"{int((mine['side'] != 0).sum())} signals")
check("same stop and ATR on every candle", np.allclose(mine["stop"], theirs["stop"], equal_nan=True) and np.allclose(mine["atr"], theirs["atr"], equal_nan=True))
t_mine, t_theirs = run_backtest(cleaned, mine, StrategyParams()), run_backtest(cleaned, theirs, StrategyParams())
check("the backtester gives identical trades for both", len(t_mine) == len(t_theirs) and (len(t_mine) == 0 or np.allclose(t_mine["net_ret"], t_theirs["net_ret"])), f"{len(t_mine)} trades")
rt = RuleStrategy.from_dict(day54.to_dict())
check("a strategy survives to_dict -> from_dict", rt == day54)

print("stops, conflicts and look-ahead")
engulf = RuleStrategy("engulfing", long=Cond("bullish_engulfing"), short=Cond("bearish_engulfing"), stop_mode="two_candle")
engulf1 = RuleStrategy("engulfing", long=Cond("bullish_engulfing"), short=Cond("bearish_engulfing"), stop_mode="candle")
s2, s1 = generate_rule_signals(cleaned, feats, engulf), generate_rule_signals(cleaned, feats, engulf1)
longs = s2["side"] == 1
check("the two-candle stop is never above the one-candle stop for longs", (s2.loc[longs, "stop"] <= s1.loc[longs, "stop"] + 1e-12).all() and longs.sum() > 0)
shorts = s2["side"] == -1
check("the two-candle stop is never below the one-candle stop for shorts", (s2.loc[shorts, "stop"] >= s1.loc[shorts, "stop"] - 1e-12).all() and shorts.sum() > 0)
check("a long stop is below its signal candle and a short stop above", (s1.loc[s1["side"] == 1, "stop"] < cleaned.loc[s1["side"] == 1, "low"]).all() and (s1.loc[s1["side"] == -1, "stop"] > cleaned.loc[s1["side"] == -1, "high"]).all())
conflict = RuleStrategy("both", long=Cond("clean_bar"), short=Cond("clean_bar"))
check("when long and short fire together the strategy stays out", (generate_rule_signals(cleaned, feats, conflict)["side"] == 0).all())
for bad_kw in ({"stop_mode": "magic"}, {"stop_buffer_atr": 9.0}):
    try:
        RuleStrategy("x", long=Cond("clean_bar"), **bad_kw)
        check(f"strategy setting {bad_kw} is refused", False)
    except RuleError:
        check(f"strategy setting {bad_kw} is refused", True)
try:
    RuleStrategy("empty")
    check("a strategy without any rule is refused", False)
except RuleError:
    check("a strategy without any rule is refused", True)
live_ok = True
sample = [i for i in range(700, len(cleaned), 61)]
for i in sample:
    window = cleaned.iloc[max(0, i + 1 - 600): i + 1]
    w_sig = generate_rule_signals(window, compute_features(window), day54).iloc[-1]
    if int(w_sig["side"]) != int(mine["side"].iloc[i]):
        live_ok = False
check("the signal at a candle does not change when later candles are absent (live equals batch)", live_ok, f"{len(sample)} candles checked")

print("evidence tools for patterns")
fr = forward_returns(cleaned, 4)
i = 300
check("forward return = close 4 candles later divided by the NEXT candle's open", abs(fr[i] - (cleaned['close'].iloc[i + 4] / cleaned['open'].iloc[i + 1] - 1)) < 1e-12)
check("the last candles have no forward return yet", np.isnan(fr[-4:]).all() and np.isfinite(fr[-5]))
rng = np.random.default_rng(3)
m = 6000
flat_ret = rng.normal(0, 0.003, m)
price = 100 * np.exp(np.cumsum(flat_ret))
op = np.concatenate([[100.0], price[:-1]])
base = pd.DataFrame({"open": op, "high": np.maximum(op, price), "low": np.minimum(op, price), "close": price})
flags = rng.random(m) < 0.03
noise_edge = pattern_edge(base, flags, 1, 1, n_draws=2000)
check("random flags on a random walk show no edge", noise_edge["p"] > 0.01 and abs(noise_edge["gross_bps"]) < 10, f"{noise_edge['n']} events, {noise_edge['gross_bps']:.1f} bps, p {noise_edge['p']:.2f}")
planted = flat_ret.copy()
for k in np.flatnonzero(flags):
    if k + 1 < m:
        planted[k + 1] += 0.004
price2 = 100 * np.exp(np.cumsum(planted))
op2 = np.concatenate([[100.0], price2[:-1]])
edge_df = pd.DataFrame({"open": op2, "high": np.maximum(op2, price2), "low": np.minimum(op2, price2), "close": price2})
found = pattern_edge(edge_df, flags, 1, 1, n_draws=2000)
check("a planted +40 bps edge is detected (p small, gross near 40, net after 20 bps cost near 20)", found["p"] < 0.01 and 25 < found["gross_bps"] < 55 and 5 < found["net_bps"] < 35, f"gross {found['gross_bps']:.1f}, net {found['net_bps']:.1f}, p {found['p']:.4f}")
short_side = pattern_edge(edge_df, flags, -1, 1, n_draws=500)
check("the same flags traded the other way lose", short_side["gross_bps"] < 0 and short_side["p"] > 0.5)
check("too few events give no verdict instead of a made-up one", np.isnan(pattern_edge(base, np.arange(m) == 500, 1, 1)["p"]))

print(f"\n{results['passed']} passed, {results['failed']} failed")
raise SystemExit(1 if results["failed"] else 0)
