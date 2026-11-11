import json

import numpy as np
import pandas as pd

from analysis.cleaning import clean_candles
from analysis.features import compute_features
from analysis.rule_builder import MAX_CHILDREN, MAX_NAME, MAX_NODES, build_strategy, validate_payload
from analysis.rules import CONDITIONS, RuleError, generate_rule_signals
from analysis.strategy import StrategyParams, generate_signals
from analysis.templates import TEMPLATES, get_template, template_ids
from services.builder_service import list_templates, preview_from_candles, template_detail
from services.strategy_service import compute_signal

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


rng = np.random.default_rng(11)
n = 3000
returns = rng.normal(0, 0.004, n) * (1 + 1.5 * (rng.random(n) < 0.03))
close = 100 * np.exp(np.cumsum(returns))
open_ = np.concatenate([[100.0], close[:-1]]) * (1 + rng.normal(0, 0.0007, n))
frame = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n))),
                      "low": np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n))), "close": close, "volume": rng.uniform(50, 150, n)},
                     index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"))
cleaned, _ = clean_candles(frame, "1h")
feats = compute_features(cleaned)

print("templates")
check("five templates exist", len(template_ids()) == 5, ", ".join(template_ids()))
check("every template passes the validator", all(validate_payload(t["strategy"])["valid"] for t in TEMPLATES.values()))
check("every template has a title, an idea and an honest evidence line", all(t["title"] and t["idea"] and t["evidence"] for t in TEMPLATES.values()))
used = set()
for t in TEMPLATES.values():
    used |= set(validate_payload(t["strategy"])["conditions_used"])
check("template conditions all exist in the catalog", used <= set(CONDITIONS), f"{len(used)} conditions used")
counts = {}
for tid, t in TEMPLATES.items():
    sig = generate_rule_signals(cleaned, feats, build_strategy(t["strategy"]))
    counts[tid] = int((sig["side"] != 0).sum())
print("  info: signals on 3000 synthetic candles: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
check("the common templates produce signals and none crashes", counts["sweep_reversal"] > 0 and counts["engulfing_with_trend"] > 0 and counts["pin_bar_with_trend"] > 0)
sweep = build_strategy(TEMPLATES["sweep_reversal"]["strategy"])
mine, theirs = generate_rule_signals(cleaned, feats, sweep), generate_signals(cleaned, feats, StrategyParams())
check("the sweep_reversal template equals the Day 54 strategy on every candle", (mine["side"].to_numpy() == theirs["side"].to_numpy()).all() and np.allclose(mine["stop"], theirs["stop"], equal_nan=True))
mutated = get_template("sweep_reversal")
mutated["strategy"]["long"] = "inside_bar"
check("changing a returned template does not change the stored one", TEMPLATES["sweep_reversal"]["strategy"]["long"] != "inside_bar")
try:
    get_template("nope")
    check("an unknown template id is refused", False)
except KeyError:
    check("an unknown template id is refused", True)
check("the template list and detail agree", [t["id"] for t in list_templates()] == template_ids() and template_detail("pin_bar_with_trend")["long_text"] == "(bullish_pin AND trend_up AND clean_bar)")
live_ok = True
for tid, t in TEMPLATES.items():
    strat = build_strategy(t["strategy"])
    full = generate_rule_signals(cleaned, feats, strat)
    for i in range(700, len(cleaned), 211):
        window = cleaned.iloc[i + 1 - 600: i + 1]
        if int(generate_rule_signals(window, compute_features(window), strat).iloc[-1]["side"]) != int(full["side"].iloc[i]):
            live_ok = False
check("no template changes its answer when later candles are absent", live_ok)

print("the validator accepts good rules and explains them")
good = {"name": "my idea", "long": {"all": ["bullish_engulfing", {"any": ["trend_up", "volume_high"]}]}, "short": None, "stop_mode": "two_candle", "stop_buffer_atr": 0.5}
r = validate_payload(good)
check("a valid custom strategy is accepted and described in words", r["valid"] and r["long_text"] == "(bullish_engulfing AND (trend_up OR volume_high))" and r["short_text"] is None, str(r["long_text"]))
check("the validator reports the conditions used and the size", r["conditions_used"] == ["bullish_engulfing", "trend_up", "volume_high"] and r["nodes"] == 5, f"nodes {r['nodes']}")
check("the normalised strategy round-trips through JSON", build_strategy(json.loads(json.dumps(r["strategy"]))) == build_strategy(good))
check("defaults fill in: only a long rule is enough", validate_payload({"long": "bullish_pin"})["valid"])
check("a name with spaces is trimmed", validate_payload({"name": "  spaced  ", "long": "bullish_pin"})["strategy"]["name"] == "spaced")

print("the validator refuses bad input with a reason (and never executes anything)")
cases = {
    "not an object": ["bullish_pin"],
    "no rule at all": {"name": "empty"},
    "unknown field": {"long": "bullish_pin", "leverage": 10},
    "unknown condition": {"long": "moon_phase"},
    "python code as a condition": {"long": "__import__('os').system('ls')"},
    "python code as a key": {"long": {"__import__('os').system('ls')": ["trend_up"]}},
    "empty all": {"long": {"all": []}},
    "two keys in one rule": {"long": {"all": ["trend_up"], "any": ["trend_down"]}},
    "a number as a rule": {"long": 5},
    "bad stop mode": {"long": "bullish_pin", "stop_mode": "magic"},
    "stop buffer too big": {"long": "bullish_pin", "stop_buffer_atr": 9},
    "stop buffer as text": {"long": "bullish_pin", "stop_buffer_atr": "0.25"},
    "stop buffer as boolean": {"long": "bullish_pin", "stop_buffer_atr": True},
    "stop buffer NaN": {"long": "bullish_pin", "stop_buffer_atr": float("nan")},
    "name too long": {"long": "bullish_pin", "name": "x" * (MAX_NAME + 1)},
    "name with a control character": {"long": "bullish_pin", "name": "bad\nname"},
    "name not a string": {"long": "bullish_pin", "name": 7},
}
for label, payload in cases.items():
    out = validate_payload(payload)
    check(f"refused: {label}", (not out["valid"]) and len(out["errors"]) >= 1 and out["strategy"] is None, out["errors"][0][:70] if out["errors"] else "")
check("both sides can report separate errors", len(validate_payload({"long": "nope", "short": "also_nope"})["errors"]) == 2)
check("an unknown condition error lists the valid names", "sweep_bull" in validate_payload({"long": "moon_phase"})["errors"][0])
long_name = "y" * 5000
msg = validate_payload({"long": long_name})["errors"][0]
check("an error message about a giant string stays short", len(msg) < 400, f"{len(msg)} characters")

print("size limits")
deep = "trend_up"
for _ in range(12):
    deep = {"not": deep}
check("too deep is refused", not validate_payload({"long": deep})["valid"])
wide = {"all": ["trend_up"] * (MAX_CHILDREN + 1)}
check("too many conditions in one list is refused", not validate_payload({"long": wide})["valid"])
big = {"all": [{"any": ["trend_up"] * MAX_CHILDREN} for _ in range(MAX_CHILDREN)]}
check("a rule with too many parts is refused", not validate_payload({"long": big})["valid"], f"limit {MAX_NODES} parts")
hostile = {"all": [{"any": [{"all": ["trend_up"] * 12}] * 12}] * 12}
check("a hostile wide-and-deep rule is refused quickly", not validate_payload({"long": hostile})["valid"])
exact = {"all": ["trend_up"] * MAX_CHILDREN}
check("a rule exactly at the limit is accepted", validate_payload({"long": exact})["valid"])

print("preview on the latest candle")
now = frame.index[-1] + pd.Timedelta(minutes=70)
p = preview_from_candles(frame, TEMPLATES["sweep_reversal"]["strategy"], "BTCUSDT", now=now)
s = compute_signal(frame, "BTCUSDT", now=now)
check("sweep_reversal preview equals the Day 56 /strategy/signal logic", (p["status"], p["side"], p["reason"], p["as_of"]) == (s["status"], s["side"], s["reason"], s["as_of"]) and p["stop_price"] == s["stop_price"], f"{p['status']} / {p['reason']}")
check("the preview reports window size and signal count", p["window_candles"] > 500 and p["signals_in_window"] >= 0, f"{p['signals_in_window']} signals in {p['window_candles']} candles")
check("the preview is research only and says nothing is traded", p["research_only"] is True and "nothing is traded" in p["note"])
check("old data is flagged stale", preview_from_candles(frame, good, "BTCUSDT", now=frame.index[-1] + pd.Timedelta(hours=9))["stale"] is True)
try:
    preview_from_candles(frame, {"long": "moon_phase"}, "BTCUSDT")
    check("a preview of an invalid strategy raises RuleError", False)
except RuleError:
    check("a preview of an invalid strategy raises RuleError", True)
hits = [i for i in range(700, len(cleaned)) if int(mine["side"].iloc[i]) != 0]
agree, seen_signal = True, 0
for i in hits[:40]:
    cut = frame.iloc[: i + 1]
    t = cut.index[-1] + pd.Timedelta(minutes=70)
    a, b = preview_from_candles(cut, TEMPLATES["sweep_reversal"]["strategy"], "BTCUSDT", now=t), compute_signal(cut, "BTCUSDT", now=t)
    seen_signal += a["status"] == "signal"
    agree &= (a["status"], a["side"], a["reason"], a["stop_price"]) == (b["status"], b["side"], b["reason"], b["stop_price"])
check("on candles WITH a setup the preview and /strategy/signal agree on status, side, reason and stop", agree and seen_signal > 0, f"{len(hits[:40])} setups compared, {seen_signal} full signals")

print(f"\n{results['passed']} passed, {results['failed']} failed")
raise SystemExit(1 if results["failed"] else 0)
