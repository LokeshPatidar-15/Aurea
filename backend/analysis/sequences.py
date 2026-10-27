import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from analysis.ml_features import Winsorizer, purged_split


def make_windows(Z: np.ndarray, positions: np.ndarray, length: int) -> np.ndarray:
    positions = np.asarray(positions)
    idx = positions[:, None] + np.arange(-length + 1, 1)[None, :]
    return Z[idx]


def contiguous_mask(index: pd.DatetimeIndex, positions: np.ndarray, length: int) -> np.ndarray:
    values = index.asi8
    step = int(np.median(np.diff(values)))
    span = values[positions] - values[positions - length + 1]
    return span == step * (length - 1)


def _select(index, X_index, length):
    positions = X_index.get_indexer(index)
    keep = positions >= length - 1
    positions = positions[keep]
    ok = contiguous_mask(X_index, positions, length)
    return positions[ok], np.asarray(index)[keep][ok]


def build_sequence_sets(X: pd.DataFrame, labels: pd.DataFrame, length: int = 48, test_frac: float = 0.3, val_frac: float = 0.15, horizon: int = 12):
    X_tr, X_te, lab_tr, lab_te = purged_split(X, labels, test_frac)
    cut = int(len(X_tr) * (1 - val_frac))
    fit_index, val_index = X_tr.index[: cut - horizon], X_tr.index[cut:]
    prep = make_pipeline(Winsorizer(), StandardScaler()).fit(X.loc[fit_index])
    Z = prep.transform(X).astype(np.float32)
    out = {"prep": prep, "length": length, "n_features": X.shape[1]}
    for name, index, lab in (("fit", fit_index, lab_tr), ("val", val_index, lab_tr), ("test", X_te.index, lab_te)):
        positions, kept = _select(index, X.index, length)
        kept_labels = lab.loc[kept]
        out[name] = {
            "X": make_windows(Z, positions, length),
            "y": kept_labels["label"].to_numpy().astype(np.int64) + 1,
            "labels": kept_labels,
            "positions": positions,
        }
    return out, Z


def windows_with_mask(Z: np.ndarray, index: pd.DatetimeIndex, positions: np.ndarray, length: int):
    positions = np.asarray(positions)
    ok = positions >= length - 1
    ok[ok] = contiguous_mask(index, positions[ok], length)
    return make_windows(Z, positions[ok], length), ok


def build_fold_sets(X: pd.DataFrame, labels: pd.DataFrame, train_positions, length: int = 48, horizon: int = 12, val_frac: float = 0.15) -> dict:
    train_positions = np.asarray(train_positions)
    cut = int(len(train_positions) * (1 - val_frac))
    fit_pos, val_pos = train_positions[: cut - horizon], train_positions[cut:]
    prep = make_pipeline(Winsorizer(), StandardScaler()).fit(X.iloc[fit_pos])
    Z = prep.transform(X).astype(np.float32)
    y_all = labels["label"].to_numpy()
    sets = {"prep": prep, "Z": Z, "length": length}
    for name, pos in (("fit", fit_pos), ("val", val_pos)):
        windows, ok = windows_with_mask(Z, X.index, pos, length)
        sets[name] = {"X": windows, "y": y_all[pos][ok].astype(np.int64) + 1}
    return sets
