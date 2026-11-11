import numpy as np
import pandas as pd

from analysis.ml_features import load_inputs
from analysis.patterns import detect_all
from analysis.pattern_stats import pattern_edge
from analysis.rules import Cond, Context, evaluate

SYMBOLS = ("BTCUSDT", "XAUUSD", "EURUSD")
HORIZONS = (1, 4, 12)

print("=== Do candlestick patterns have an edge? (1h, whole history, nothing tuned) ===")
print("entry at the NEXT candle's open after the pattern, exit after N candles, cost 20 bps round trip")
print("baseline = the same number of random candles. p = share of random draws that did as well\n")

tests = []
inside = {}
for symbol in SYMBOLS:
    feats, cleaned = load_inputs(symbol, "1h")
    cleaned = cleaned.loc[feats.index]
    ctx = Context(cleaned, feats)
    flags = {
        "bullish_engulfing": (evaluate(Cond("bullish_engulfing"), ctx), 1),
        "bearish_engulfing": (evaluate(Cond("bearish_engulfing"), ctx), -1),
        "bullish_pin": (evaluate(Cond("bullish_pin"), ctx), 1),
        "bearish_pin": (evaluate(Cond("bearish_pin"), ctx), -1),
        "sweep_bull": (evaluate(Cond("sweep_bull"), ctx), 1),
        "sweep_bear": (evaluate(Cond("sweep_bear"), ctx), -1),
        "sweep_bull + bullish_engulfing": (evaluate(Cond("sweep_bull") & Cond("bullish_engulfing"), ctx), 1),
        "sweep_bear + bearish_engulfing": (evaluate(Cond("sweep_bear") & Cond("bearish_engulfing"), ctx), -1),
    }
    inside[symbol] = float(detect_all(cleaned)["inside_bar"].mean())
    for name, (flag, direction) in flags.items():
        for h in HORIZONS:
            r = pattern_edge(cleaned, flag.to_numpy(), direction, h)
            tests.append({"symbol": symbol, "pattern": name, "dir": "long" if direction == 1 else "short", "horizon": h, **r})

table = pd.DataFrame(tests)
n_tests = int(table["p"].notna().sum())
threshold = 0.05 / max(n_tests, 1)
for symbol in SYMBOLS:
    print(f"--- {symbol} ---")
    part = table[table["symbol"] == symbol].drop(columns="symbol")
    print(part.to_string(index=False, float_format=lambda v: f"{v:8.2f}"))
    print()

print(f"tests run: {n_tests}. With this many tests some p-values below 0.05 appear by pure luck.")
print(f"Bonferroni threshold: p must be below 0.05 / {n_tests} = {threshold:.5f} to count")
print("inside bar is only a condition (no direction), so only its frequency is shown: " + ", ".join(f"{k} {v:.1%}" for k, v in inside.items()))

gross_ok = table[(table["gross_bps"] > 0) & (table["p"] < 0.05)]
net_ok = table[table["net_bps"] > 0]
passed = table[(table["p"] < threshold) & (table["net_bps"] > 0)]
print(f"\nrows with positive gross edge and p < 0.05 (before correction): {len(gross_ok)}")
print(f"rows with positive NET edge after the 20 bps cost: {len(net_ok)} of {n_tests}")
print(f"rows that survive Bonferroni AND are profitable after cost: {len(passed)}")
if len(passed):
    print(passed.to_string(index=False, float_format=lambda v: f"{v:8.2f}"))
else:
    print("verdict: no pattern shows a tradable edge. Patterns stay what they are: readable conditions to combine and to explain, not a reason to trade.")
