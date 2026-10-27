import json
import sys
from pathlib import Path

import pandas as pd

from analysis.ml_features import load_model_frame
from analysis.walkforward import run_walk_forward, summarize

USAGE = "usage: python3 -m analysis.day53_model_comparison SYMBOL logistic|xgboost|lstm|report"
if len(sys.argv) < 3:
    print(USAGE)
    sys.exit(1)
SYMBOL, WHAT = sys.argv[1], sys.argv[2]
HORIZON, K, FOLDS, LENGTH = 12, 2.0, 5, 48
OUT = Path("artifacts")
OUT.mkdir(exist_ok=True)
NAMES = {"logistic": "logistic", "xgboost": "xgboost", "lstm": "lstm (3 seeds)"}


def result_path(name: str) -> Path:
    return OUT / f"wf_{SYMBOL}_{name}.json"


def save_result(name: str, table: pd.DataFrame, pooled: dict) -> None:
    records = table.assign(test_from=table["test_from"].astype(str), test_to=table["test_to"].astype(str)).to_dict(orient="records")
    result_path(name).write_text(json.dumps({"table": records, "pooled": {"net_bps_per_trade": pooled["net_bps_per_trade"], "p_value": pooled["p_value"]}}, indent=2))
    s = summarize(table, pooled)
    print(f"saved {result_path(name)} | mean net {s['mean_net_bps_per_trade']:.1f} bps/trade, folds > 0: {s['folds_with_positive_net']}/{s['folds']}")


if WHAT == "logistic":
    from analysis.baseline_models import make_logistic

    X, labels = load_model_frame(SYMBOL, "1h", HORIZON, K)
    table, pooled = run_walk_forward(X, labels, lambda a, b, c: make_logistic().fit(a, b).predict(c), FOLDS)
    save_result("logistic", table, pooled)
elif WHAT == "xgboost":
    from analysis.tuning import load_best_params
    from analysis.xgb_model import DEFAULT_PARAMS, fit_xgb, predict_xgb

    X, labels = load_model_frame(SYMBOL, "1h", HORIZON, K)
    params = {**DEFAULT_PARAMS, **(load_best_params(SYMBOL, "1h") or {})}
    table, pooled = run_walk_forward(X, labels, lambda a, b, c: predict_xgb(fit_xgb(a, b, HORIZON, params), c), FOLDS)
    save_result("xgboost", table, pooled)
elif WHAT == "lstm":
    from analysis.walkforward_lstm import run_walk_forward_lstm

    X, labels = load_model_frame(SYMBOL, "1h", HORIZON, K)
    table, pooled = run_walk_forward_lstm(X, labels, FOLDS, length=LENGTH, seeds=(0, 1, 2), horizon=HORIZON, epochs=30, patience=5)
    save_result("lstm", table, pooled)
elif WHAT == "report":
    runs = {}
    for key, label in NAMES.items():
        path = result_path(key)
        if not path.exists():
            print(f"missing {path.name}. Run: python3 -m analysis.day53_model_comparison {SYMBOL} {key}")
            continue
        data = json.loads(path.read_text())
        runs[label] = (pd.DataFrame(data["table"]), data["pooled"])
    if not runs:
        sys.exit(1)

    print(f"=== Net bps per trade in each fold, after 20 bps cost ({SYMBOL}, 1h, {FOLDS} walk-forward folds) ===")
    first = next(iter(runs.values()))[0]
    folds = pd.DataFrame({name: table["net_bps"].round(1).to_numpy() for name, (table, _) in runs.items()},
                         index=[f"fold {i} ({d[:10]})" for i, d in enumerate(first["test_from"], start=1)])
    print(folds.to_string())

    print("\n=== Summary ===")
    rows = []
    for name, (table, pooled) in runs.items():
        s = summarize(table, {"net_bps_per_trade": pooled["net_bps_per_trade"], "p_value": pooled["p_value"]})
        rows.append({"model": name, "bal.acc": s["mean_balanced_accuracy"], "mean net bps": s["mean_net_bps_per_trade"],
                     "folds > 0": f"{s['folds_with_positive_net']}/{s['folds']}", "pooled net bps": s["pooled_net_bps_per_trade"], "pooled p": s["pooled_p_value"]})
    summary = pd.DataFrame(rows)
    print(summary.to_string(index=False, formatters={"bal.acc": "{:.3f}".format, "mean net bps": "{:.1f}".format, "pooled net bps": "{:.1f}".format, "pooled p": "{:.3f}".format}))

    print("\n=== Selection rule ===")
    best = summary.sort_values("mean net bps", ascending=False).iloc[0]
    positive_folds = int(best["folds > 0"].split("/")[0])
    qualifies = positive_folds >= 3 and best["pooled p"] < 0.10 and best["mean net bps"] > 0
    print(f"best by mean net bps: {best['model']} ({best['mean net bps']:.1f} bps/trade, folds > 0: {best['folds > 0']}, pooled p {best['pooled p']:.3f})")
    if qualifies:
        print("it passes the gate (net > 0, at least 3 folds positive, pooled p < 0.10). Still research_only until paper trading confirms it")
    else:
        print("no model passes the gate (net > 0, at least 3 folds positive, pooled p < 0.10). Default stays xgboost, flagged research_only")
    print("the choice is made on walk-forward folds only. The 'best' model here is the least-bad one, not a profitable one")
    report = {"symbol": SYMBOL, "folds": FOLDS, "cost_bps": 20, "passes_gate": bool(qualifies), "models": summary.to_dict(orient="records")}
    (OUT / f"model_comparison_{SYMBOL}.json").write_text(json.dumps(report, indent=2))
    print(f"saved artifacts/model_comparison_{SYMBOL}.json")
else:
    print(USAGE)
    sys.exit(1)
