import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score
from sklearn.model_selection import KFold

from analysis.baseline_models import make_logistic
from analysis.ml_features import load_model_frame, purged_split
from analysis.walkforward import run_walk_forward, summarize, walk_forward_splits
from analysis.xgb_model import fit_xgb, predict_xgb

HORIZON, K, FOLDS = 12, 2.0, 5
X, labels = load_model_frame("BTCUSDT", "1h", HORIZON, K)


def logistic_fp(X_tr, y_tr, X_te):
    return make_logistic().fit(X_tr, y_tr).predict(X_te)


def xgb_fp(X_tr, y_tr, X_te):
    return predict_xgb(fit_xgb(X_tr, y_tr, HORIZON), X_te)


print("=== 1. How the folds are cut (expanding window, purged) ===")
for fold, (train_idx, test_idx) in enumerate(walk_forward_splits(labels, FOLDS), start=1):
    print(f"fold {fold}: train {len(train_idx):5} rows (up to {X.index[train_idx[-1]]:%Y-%m-%d}) | "
          f"test {len(test_idx):4} rows ({X.index[test_idx[0]]:%Y-%m-%d} -> {X.index[test_idx[-1]]:%Y-%m-%d})")
print("each test block is always LATER than its training data; rows whose label ends inside the block are dropped from training")

results = {}
for name, fp in (("logistic", logistic_fp), ("xgboost", xgb_fp)):
    table, pooled = run_walk_forward(X, labels, fp, FOLDS)
    results[name] = (table, pooled)
    print(f"\n=== 2. {name}: score in every fold ===")
    show = table[["fold", "test_from", "test_to", "bal_acc", "trades", "win", "net_bps"]].copy()
    show["test_from"] = show["test_from"].dt.strftime("%Y-%m-%d")
    show["test_to"] = show["test_to"].dt.strftime("%Y-%m-%d")
    print(show.to_string(index=False, formatters={"bal_acc": "{:.3f}".format, "win": "{:.3f}".format, "net_bps": "{:.1f}".format}))
    s = summarize(table, pooled)
    print(f"balanced accuracy: mean {s['mean_balanced_accuracy']:.3f}, std across folds {s['std_balanced_accuracy']:.3f}, "
          f"range {table['bal_acc'].min():.3f} to {table['bal_acc'].max():.3f}")
    print(f"net bps/trade: mean {s['mean_net_bps_per_trade']:.1f}, positive in {s['folds_with_positive_net']} of {s['folds']} folds | "
          f"pooled out-of-sample {s['pooled_net_bps_per_trade']:.1f} bps, p-value {s['pooled_p_value']:.3f}")

print("\n=== 3. One lucky split vs the whole story ===")
X_tr, X_te, lab_tr, lab_te = purged_split(X, labels, test_frac=0.3)
single = balanced_accuracy_score(lab_te["label"], xgb_fp(X_tr, lab_tr["label"], X_te))
table = results["xgboost"][0]
print(f"xgboost on ONE split (newest 30%): balanced accuracy {single:.3f}")
print(f"xgboost across {FOLDS} walk-forward folds: {table['bal_acc'].min():.3f} to {table['bal_acc'].max():.3f}")
print("a single split is one draw from that range. Never judge a model by one test period.")

print("\n=== 4. The wrong way: shuffled K-fold (what many tutorials do) ===")
scores = []
for train_idx, test_idx in KFold(FOLDS, shuffle=True, random_state=0).split(X):
    y_tr = labels["label"].iloc[train_idx]
    pred = xgb_fp(X.iloc[train_idx], y_tr, X.iloc[test_idx])
    scores.append(balanced_accuracy_score(labels["label"].iloc[test_idx], pred))
wf_mean = table["bal_acc"].mean()
print(f"shuffled K-fold balanced accuracy: {np.mean(scores):.3f} | walk-forward: {wf_mean:.3f} | inflation: {100 * (np.mean(scores) - wf_mean):+.1f} points")
print("shuffled folds put neighbouring candles (almost identical features and overlapping labels) on both sides of the split")
