import time

import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

from analysis.evaluation import evaluate
from analysis.ml_features import load_model_frame
from analysis.tuning import GRID, grid_combinations, save_best_params
from analysis.walkforward import run_walk_forward
from analysis.xgb_model import DEFAULT_PARAMS, fit_xgb, predict_xgb

SYMBOL, TIMEFRAME, HORIZON, K, FOLDS = "BTCUSDT", "1h", 12, 2.0, 4
X, labels = load_model_frame(SYMBOL, TIMEFRAME, HORIZON, K)

cut = int(len(X) * 0.8)
X_dev, lab_dev = X.iloc[:cut], labels.iloc[:cut]
holdout_start = X.index[cut]
train_mask = (labels["exit_time"] < holdout_start).to_numpy() & (np.arange(len(X)) < cut)
X_hold, lab_hold = X.iloc[cut:], labels.iloc[cut:]

print("=== 1. Three-way split ===")
print(f"development (tuning happens here): {len(X_dev)} rows, up to {X_dev.index[-1]:%Y-%m-%d}")
print(f"final holdout (touched ONCE at the end): {len(X_hold)} rows, {X_hold.index[0]:%Y-%m-%d} -> {X_hold.index[-1]:%Y-%m-%d}")
combos = grid_combinations(GRID)
print(f"grid: {len(combos)} parameter combinations x {FOLDS} walk-forward folds = {len(combos) * FOLDS} model fits")

print("\n=== 2. Grid search with walk-forward scoring (higher balanced accuracy is better) ===")
records = []
started = time.time()
for number, params in enumerate(combos, start=1):
    def fp(X_tr, y_tr, X_te, params=params):
        return predict_xgb(fit_xgb(X_tr, y_tr, HORIZON, params), X_te)

    table, pooled = run_walk_forward(X_dev, lab_dev, fp, FOLDS)
    records.append({**params, "cv_mean": table["bal_acc"].mean(), "cv_std": table["bal_acc"].std(ddof=1), "net_bps": table["net_bps"].mean()})
    print(f"  {number:2}/{len(combos)} {params} -> cv {records[-1]['cv_mean']:.4f} ({time.time() - started:.0f}s)")

results = pd.DataFrame(records).sort_values("cv_mean", ascending=False).reset_index(drop=True)
print("\ntop 5 combinations:")
print(results.head(5).round(4).to_string(index=False))
best = results.iloc[0]
best_params = {k: (int(best[k]) if k != "learning_rate" else float(best[k])) for k in GRID}
default_row = results[(results["max_depth"] == DEFAULT_PARAMS["max_depth"]) & (results["min_child_weight"] == DEFAULT_PARAMS["min_child_weight"]) & (results["learning_rate"] == DEFAULT_PARAMS["learning_rate"])].iloc[0]

print("\n=== 3. Is tuning even helping? ===")
print(f"best cv score {best['cv_mean']:.4f} | default settings cv score {default_row['cv_mean']:.4f} | gain {100 * (best['cv_mean'] - default_row['cv_mean']):+.2f} points")
print(f"typical fold-to-fold spread (std) of the best setting: {best['cv_std']:.4f} | spread between best and median combination: {results['cv_mean'].iloc[0] - results['cv_mean'].median():.4f}")
if best["cv_mean"] - default_row["cv_mean"] < best["cv_std"]:
    print("the gain is smaller than the fold-to-fold noise: the 'best' setting may just be the luckiest one")

print("\n=== 4. Final holdout: untouched data, one look ===")
def holdout_score(params):
    train_idx = np.flatnonzero(train_mask)
    model = fit_xgb(X.iloc[train_idx], labels["label"].iloc[train_idx], HORIZON, params)
    pred = predict_xgb(model, X_hold)
    e = evaluate(lab_hold["label"], pred, lab_hold["ret"])
    return e

default_eval = holdout_score(DEFAULT_PARAMS)
best_eval = holdout_score(best_params)
print(f"{'':16} {'cv score':>9} {'holdout bal.acc':>16} {'holdout net bps/trade':>22}")
print(f"{'default params':16} {default_row['cv_mean']:9.4f} {default_eval['balanced_accuracy']:16.4f} {default_eval['net_bps_per_trade']:22.1f}")
print(f"{'tuned params':16} {best['cv_mean']:9.4f} {best_eval['balanced_accuracy']:16.4f} {best_eval['net_bps_per_trade']:22.1f}")
print(f"optimism gap (tuned cv minus tuned holdout): {100 * (best['cv_mean'] - best_eval['balanced_accuracy']):+.2f} points")
print(f"the best of {len(combos)} tries always looks better in cv than it really is. The holdout is the honest number.")

path = save_best_params(SYMBOL, TIMEFRAME, {
    "params": best_params,
    "cv_mean_balanced_accuracy": float(best["cv_mean"]),
    "holdout_balanced_accuracy": float(best_eval["balanced_accuracy"]),
    "holdout_net_bps_per_trade": float(best_eval["net_bps_per_trade"]),
    "trials": len(combos),
})
print(f"\nbest params saved: {path}")
