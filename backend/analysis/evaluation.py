import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, confusion_matrix

CLASS_ORDER = [-1, 0, 1]
CLASS_NAMES = {-1: "sell", 0: "hold", 1: "buy"}
COST_BPS = 20.0


def trade_returns(pred: np.ndarray, ret: np.ndarray, cost_bps: float = COST_BPS) -> np.ndarray:
    traded = pred != 0
    gross = pred[traded] * ret[traded]
    return gross - cost_bps / 10_000


def permutation_pvalue(pred: np.ndarray, ret: np.ndarray, cost_bps: float = COST_BPS, n: int = 500, seed: int = 0, min_shift: int = 50) -> float:
    traded = trade_returns(pred, ret, cost_bps)
    if len(traded) == 0 or len(pred) <= 2 * min_shift:
        return float("nan")
    observed = traded.mean()
    rng = np.random.default_rng(seed)
    better = 0
    for _ in range(n):
        shift = int(rng.integers(min_shift, len(pred) - min_shift))
        if trade_returns(np.roll(pred, shift), ret, cost_bps).mean() >= observed:
            better += 1
    return (better + 1) / (n + 1)


def evaluate(y_true, y_pred, ret, cost_bps: float = COST_BPS) -> dict:
    y_true, y_pred, ret = np.asarray(y_true), np.asarray(y_pred), np.asarray(ret, dtype=float)
    counts = pd.Series(y_true).value_counts(normalize=True)
    net = trade_returns(y_pred, ret, cost_bps)
    return {
        "accuracy": float((y_true == y_pred).mean()),
        "baseline": float(counts.max()),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "trades": int(len(net)),
        "trade_share": float((y_pred != 0).mean()),
        "win_rate": float((net > 0).mean()) if len(net) else float("nan"),
        "net_bps_per_trade": float(net.mean() * 10_000) if len(net) else float("nan"),
        "p_value": permutation_pvalue(y_pred, ret, cost_bps),
        "confusion": confusion_matrix(y_true, y_pred, labels=CLASS_ORDER),
    }
