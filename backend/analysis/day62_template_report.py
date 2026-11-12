import pandas as pd

from analysis.evidence import ALPHA, evaluate_strategy, strategy_key
from analysis.ml_features import load_inputs
from analysis.rule_builder import build_strategy
from analysis.rules import describe
from analysis.templates import TEMPLATES
from analysis.trial_log import TrialLog

SYMBOLS = ("BTCUSDT", "XAUUSD", "EURUSD")

print("=== Do the 5 templates have an edge? (1h, whole history, fixed rules, cost 20 bps) ===")
print("every template x symbol test is written to the trial log FIRST, so all 15 are judged with the same multiple-testing count\n")

log = TrialLog()
inputs = {symbol: load_inputs(symbol, "1h") for symbol in SYMBOLS}
plan = [(tid, symbol, build_strategy(t["strategy"])) for tid, t in TEMPLATES.items() for symbol in SYMBOLS]
count = 0
for tid, symbol, strategy in plan:
    count = log.record(strategy_key(strategy), symbol, strategy.name, describe(strategy.long) if strategy.long else None, describe(strategy.short) if strategy.short else None)["count"]
print(f"strategies tried so far (including these 15): {count}. Bonferroni threshold: p must be below {ALPHA} / {count} = {ALPHA / count:.5f}\n")

rows = []
for tid, symbol, strategy in plan:
    feats, cleaned = inputs[symbol]
    ev = evaluate_strategy(cleaned, feats, strategy, strategies_tried=count)
    r, b = ev["result"], ev["random_baseline"]
    rows.append({"template": tid, "symbol": symbol, "trades": r["trades"], "win": r.get("win_rate"), "gross_bps": r.get("gross_bps"), "net_bps": r.get("net_bps"),
                 "p": b["p"] if b else None, "p_adj": b["p_adjusted"] if b else None, "slices+": f"{ev['positive_slices']}/{len(ev['slices'])}",
                 "sharpe": ev["sharpe"]["value"], "verdict": ev["verdict"]["label"]})
table = pd.DataFrame(rows)
print(table.to_string(index=False, float_format=lambda v: f"{v:8.3f}", na_rep="   -"))
print("\nverdict counts:", {k: int(v) for k, v in table["verdict"].value_counts().items()})
promising = table[table["verdict"] == "promising"]
if len(promising):
    print("\nrows that pass the in-sample screen (still NOT proof: they need forward testing in paper trading):")
    print(promising.to_string(index=False, float_format=lambda v: f"{v:8.3f}"))
else:
    print("\nverdict: no template passes the in-sample screen on this data.")
print("win rate alone says nothing: a 2R target with a 45% win rate can still lose after cost. Read net_bps and p_adj.")
