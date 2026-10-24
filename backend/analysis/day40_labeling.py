import numpy as np
import pandas as pd

from analysis.labeling import triple_barrier
from analysis.ml_features import build_model_frame_from, load_inputs


def check_handcrafted() -> None:
    n = 60
    idx = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    candle = dict(open=100.0, high=100.2, low=99.8, close=100.0, volume=1.0)
    df = pd.DataFrame([candle] * n, index=idx)
    atr_pct = pd.Series(0.01, index=idx)
    df.loc[idx[5], "high"] = 101.5
    df.loc[idx[13], "low"] = 98.0
    df.loc[idx[22], ["high", "low"]] = [101.5, 98.0]
    df.loc[idx[45], "close"] = 100.4
    out = triple_barrier(df, atr_pct, horizon=10, k=1.0)
    assert out["label"].iloc[0] == 1 and out["exit_time"].iloc[0] == idx[5]
    assert out["label"].iloc[10] == -1 and out["exit_time"].iloc[10] == idx[13]
    assert out["label"].iloc[18] == 0 and out["exit_time"].iloc[18] == idx[22]
    assert out["label"].iloc[35] == 0 and abs(out["ret"].iloc[35] - 0.004) < 1e-12
    assert out["label"].iloc[-10:].isna().all() and out["label"].iloc[:-10].notna().all()
    print("candle 0: price touched +1% on candle 5 first        -> label +1 (buy), exit at candle 5")
    print("candle 10: price touched -1% on candle 13 first       -> label -1 (sell), exit at candle 13")
    print("candle 18: +1% and -1% in the SAME candle (ambiguous) -> label 0 (hold), we refuse to guess")
    print("candle 35: no barrier touched in 10 candles           -> label 0 (hold), exit by time, ret +0.4%")
    print("last 10 candles: future not complete                  -> no label (NaN), dropped")


print("=== 1. Triple-barrier logic on hand-made candles ===")
check_handcrafted()

feats, cleaned = load_inputs("BTCUSDT", "1h")

HORIZON, K = 12, 2.0
print(f"\n=== 2. BTCUSDT 1h labels (horizon {HORIZON} candles, barrier = {K} x ATR) ===")
X, labels = build_model_frame_from(feats, cleaned, horizon=HORIZON, k=K)
shares = labels["label"].value_counts(normalize=True).reindex([-1, 0, 1]).fillna(0)
print(f"labelled rows: {len(labels)}")
print(f"sell (-1): {shares[-1]:.1%} | hold (0): {shares[0]:.1%} | buy (+1): {shares[1]:.1%}")
print(f"average barrier width: {K * feats['atr_14_pct'].mean():.2%} of price | median candles until exit: {labels['bars_held'].median():.0f}")
print(f"average realized return of a long on every candle: {labels['ret'].mean() * 10_000:+.1f} bps (before costs)")

print("\n=== 3. How the label mix changes with barrier width k and horizon (share of sell / hold / buy) ===")
print(f"{'k':>4} {'horizon':>8} {'sell':>7} {'hold':>7} {'buy':>7}")
for k in (0.5, 1.0, 1.5, 2.0):
    for horizon in (6, 12, 24):
        _, lab = build_model_frame_from(feats, cleaned, horizon=horizon, k=k)
        s = lab["label"].value_counts(normalize=True).reindex([-1, 0, 1]).fillna(0)
        print(f"{k:>4} {horizon:>8} {s[-1]:>7.1%} {s[0]:>7.1%} {s[1]:>7.1%}")
