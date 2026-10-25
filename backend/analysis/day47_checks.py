import sys
import warnings

import joblib
import numpy as np
import pandas as pd

from analysis.cleaning import clean_candles
from analysis.db_loader import load_from_db
from analysis.features import compute_features
from analysis.ml_features import make_features
from services.model_store import artifact_path
from services.prediction_service import (
    ModelNotFoundError,
    UnsupportedSymbolError,
    load_artifact,
    predict_from_candles,
    proba_for,
)

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def expect_error(error_type, fn, *args) -> bool:
    try:
        fn(*args)
    except error_type:
        return True
    except Exception:
        return False
    return False


for symbol in ("BTCUSDT", "XAUUSD", "EURUSD"):
    print(f"{symbol} 1h")
    path = artifact_path(symbol, "1h")
    check("model file exists", path.exists(), f"{path.stat().st_size / 1024:.0f} KB" if path.exists() else "run: python3 -m scripts.train_model")
    if not path.exists():
        continue

    artifact = joblib.load(path)
    needed = {"model", "model_type", "class_order", "feature_names", "trained_through", "trained_rows", "walk_forward", "versions", "created_at"}
    check("artifact carries its own metadata", needed <= set(artifact), f"{len(artifact['feature_names'])} features, trained through {artifact['trained_through'][:10]}")

    raw = load_from_db(symbol, "1h")
    cleaned, _ = clean_candles(raw, "1h")
    offline = make_features(compute_features(cleaned))
    offline = offline.dropna()
    positions = np.linspace(len(raw) - 900, len(raw) - 1, 5).astype(int)
    worst_gap = 0.0
    for pos in positions:
        last_time = raw.index[pos]
        if last_time not in offline.index:
            continue
        expected = proba_for(artifact, offline.loc[[last_time]])[0]
        online = predict_from_candles(artifact, raw.iloc[: pos + 1])
        got = np.array([online["probabilities"][name] for name in ("sell", "hold", "buy")])
        order = [-1, 0, 1]
        expected = np.array([expected[artifact["class_order"].index(c)] for c in order])
        worst_gap = max(worst_gap, float(np.abs(expected - got).max()))
    check("serving matches training: 5 candles, 600-candle window vs full history", worst_gap < 2e-3, f"largest probability difference {worst_gap:.5f}")

    out = predict_from_candles(artifact, raw)
    check("probabilities sum to about 1 and signal is valid", abs(sum(out["probabilities"].values()) - 1) < 0.01 and out["signal"] in {"sell", "hold", "buy"}, f"{out['signal']} {out['confidence']:.2f}")

print("\nerror handling")
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    check("unsupported symbol raises UnsupportedSymbolError", expect_error(UnsupportedSymbolError, load_artifact, "DOGEUSDT", "1h"))
    check("missing model raises ModelNotFoundError", expect_error(ModelNotFoundError, load_artifact, "BTCUSDT", "15m"))

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
