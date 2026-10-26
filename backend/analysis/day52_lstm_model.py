import numpy as np

from analysis.baseline_models import make_logistic
from analysis.evaluation import evaluate
from analysis.ml_features import load_model_frame, purged_split
from analysis.sequences import build_sequence_sets
from analysis.torch_lstm import LSTMClassifier, fit_lstm
from analysis.torch_nn import fit_torch

LENGTH = 48
X, labels = load_model_frame("BTCUSDT", "1h", 12, 2.0)
sets, _ = build_sequence_sets(X, labels, length=LENGTH)
test_labels = sets["test"]["labels"]
test_index = test_labels.index

print("=== 1. The model and its size ===")
probe = LSTMClassifier(X.shape[1], hidden=32)
parameters = sum(p.numel() for p in probe.parameters())
print(f"LSTM(26 -> 32) + dropout + linear(32 -> 3): {parameters} parameters")
print(f"training windows {len(sets['fit']['y'])} | rows per parameter {len(sets['fit']['y']) / parameters:.1f}")
print("each LSTM layer has 4 blocks (forget, input, candidate, output), each with weights for the input, the old hidden state and a bias")

print("\n=== 2. Training (gradient clipping at 1.0, early stopping on validation loss) ===")
model = fit_lstm(sets, hidden=32, dropout=0.3, lr=1e-3, weight_decay=1e-4, seed=0)
history = model.history
print(f"best epoch {model.best_epoch} of {len(history)} run | train loss {history['train_loss'].iloc[-1]:.3f} | validation loss {history['val_loss'].min():.3f} (best)")
gap = history["val_loss"].iloc[-1] - history["train_loss"].iloc[-1]
print(f"validation minus train loss at the end: {gap:+.3f}. A growing positive gap means the network is memorising")

print("\n=== 3. Fair comparison on the SAME test rows ===")
X_tr, X_te, lab_tr, lab_te = purged_split(X, labels, test_frac=0.3)
logit = make_logistic().fit(X_tr, lab_tr["label"])
fit_index = sets["fit"]["labels"].index
val_index = sets["val"]["labels"].index
ff = fit_torch(X.loc[fit_index], labels.loc[fit_index, "label"], X.loc[val_index], labels.loc[val_index, "label"], log_every=0)

rows = {
    "logistic": logit.predict(X.loc[test_index]),
    "feed-forward (Day 50)": ff.predict(X.loc[test_index]),
    f"LSTM ({LENGTH} steps)": model.predict(sets["test"]["X"]),
}
print(f"test rows: {len(test_index)}")
print(f"{'model':24} {'bal.acc':>8} {'trades':>7} {'net bps/trade':>14} {'p-value':>8}")
for name, pred in rows.items():
    e = evaluate(test_labels["label"], pred, test_labels["ret"])
    print(f"{name:24} {e['balanced_accuracy']:8.3f} {e['trades']:7} {e['net_bps_per_trade']:14.1f} {e['p_value']:8.3f}")
print("the sequence model sees more context. Whether that is signal or noise is decided by the net bps column, not by accuracy")

print("\n=== 4. Is the result stable? Same model, 5 random starts ===")
results = []
for seed in range(5):
    m = fit_lstm(sets, hidden=32, dropout=0.3, seed=seed, log_every=0, epochs=40)
    e = evaluate(test_labels["label"], m.predict(sets["test"]["X"]), test_labels["ret"])
    results.append((seed, m.best_epoch, e["balanced_accuracy"], e["net_bps_per_trade"]))
    print(f"  seed {seed}: best epoch {m.best_epoch:2} | balanced accuracy {e['balanced_accuracy']:.3f} | net {e['net_bps_per_trade']:6.1f} bps/trade")
net = np.array([r[3] for r in results])
print(f"mean net {net.mean():.1f} bps/trade, std {net.std():.1f}, positive in {(net > 0).sum()} of 5 seeds")
if (net > 0).sum() >= 4 and net.mean() > 0:
    print("promising: now it must survive walk-forward folds and a permutation test before anyone trusts it")
else:
    print("not a tradable edge. If a single seed looked good, that was luck: pick models by the average, never by the best seed")
