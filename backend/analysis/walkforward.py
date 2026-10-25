import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score

from analysis.evaluation import evaluate


def walk_forward_splits(labels: pd.DataFrame, n_splits: int = 5, initial_frac: float = 0.4):
    n = len(labels)
    start = int(n * initial_frac)
    edges = np.linspace(start, n, n_splits + 1).astype(int)
    index = labels.index
    for begin, end in zip(edges[:-1], edges[1:]):
        finished_before = (labels["exit_time"] < index[begin]).to_numpy()
        train_idx = np.flatnonzero((np.arange(n) < begin) & finished_before)
        test_idx = np.arange(begin, end)
        yield train_idx, test_idx


def run_walk_forward(X: pd.DataFrame, labels: pd.DataFrame, fit_predict, n_splits: int = 5, initial_frac: float = 0.4):
    rows, all_pred, all_ret, all_true = [], [], [], []
    for fold, (train_idx, test_idx) in enumerate(walk_forward_splits(labels, n_splits, initial_frac), start=1):
        y_tr = labels["label"].iloc[train_idx]
        y_te = labels["label"].iloc[test_idx]
        ret_te = labels["ret"].iloc[test_idx]
        pred = fit_predict(X.iloc[train_idx], y_tr, X.iloc[test_idx])
        e = evaluate(y_te, pred, ret_te)
        rows.append({
            "fold": fold,
            "train_rows": len(train_idx),
            "test_from": X.index[test_idx[0]],
            "test_to": X.index[test_idx[-1]],
            "bal_acc": e["balanced_accuracy"],
            "accuracy": e["accuracy"],
            "trades": e["trades"],
            "win": e["win_rate"],
            "net_bps": e["net_bps_per_trade"],
        })
        all_pred.append(pred)
        all_ret.append(ret_te.to_numpy())
        all_true.append(y_te.to_numpy())
    table = pd.DataFrame(rows)
    pooled = evaluate(np.concatenate(all_true), np.concatenate(all_pred), np.concatenate(all_ret))
    return table, pooled


def summarize(table: pd.DataFrame, pooled: dict) -> dict:
    return {
        "folds": int(len(table)),
        "mean_balanced_accuracy": float(table["bal_acc"].mean()),
        "std_balanced_accuracy": float(table["bal_acc"].std(ddof=1)) if len(table) > 1 else 0.0,
        "mean_net_bps_per_trade": float(table["net_bps"].mean()),
        "folds_with_positive_net": int((table["net_bps"] > 0).sum()),
        "pooled_net_bps_per_trade": float(pooled["net_bps_per_trade"]),
        "pooled_p_value": float(pooled["p_value"]),
    }
