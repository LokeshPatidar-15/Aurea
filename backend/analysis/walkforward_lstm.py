import time

import numpy as np
import pandas as pd

from analysis.evaluation import evaluate
from analysis.sequences import build_fold_sets, windows_with_mask
from analysis.walkforward import walk_forward_splits


def run_walk_forward_lstm(X: pd.DataFrame, labels: pd.DataFrame, n_splits: int = 5, initial_frac: float = 0.4,
                          length: int = 48, seeds: tuple = (0, 1, 2), horizon: int = 12, fit_fn=None, verbose: bool = True, **fit_kwargs):
    if fit_fn is None:
        from analysis.torch_lstm import fit_lstm as fit_fn
    started = time.time()
    rows, all_pred, all_ret, all_true = [], [], [], []
    for fold, (train_idx, test_idx) in enumerate(walk_forward_splits(labels, n_splits, initial_frac), start=1):
        sets = build_fold_sets(X, labels, train_idx, length, horizon)
        windows, ok = windows_with_mask(sets["Z"], X.index, test_idx, length)
        probs = np.zeros((len(windows), 3))
        for seed in seeds:
            model = fit_fn(sets, seed=seed, log_every=0, **fit_kwargs)
            probs += model.predict_proba(windows)
            if verbose:
                print(f"  fold {fold}/{n_splits} seed {seed} done | best epoch {getattr(model, 'best_epoch', '?')} | {time.time() - started:.0f}s elapsed", flush=True)
        pred = np.zeros(len(test_idx), dtype=int)
        pred[ok] = probs.argmax(axis=1) - 1
        y_te = labels["label"].iloc[test_idx]
        ret_te = labels["ret"].iloc[test_idx]
        e = evaluate(y_te, pred, ret_te)
        rows.append({
            "fold": fold, "train_rows": len(train_idx),
            "test_from": X.index[test_idx[0]], "test_to": X.index[test_idx[-1]],
            "bal_acc": e["balanced_accuracy"], "accuracy": e["accuracy"], "trades": e["trades"],
            "win": e["win_rate"], "net_bps": e["net_bps_per_trade"],
        })
        all_pred.append(pred)
        all_ret.append(ret_te.to_numpy())
        all_true.append(y_te.to_numpy())
    table = pd.DataFrame(rows)
    pooled = evaluate(np.concatenate(all_true), np.concatenate(all_pred), np.concatenate(all_ret))
    return table, pooled
