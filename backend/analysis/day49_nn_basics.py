import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_class_weight

from analysis.baseline_models import make_logistic
from analysis.evaluation import evaluate
from analysis.ml_features import Winsorizer, load_model_frame, purged_split
from analysis.nn_numpy import MLP, gradient_check, layer_gradient_norms

print("=== 1. One neuron: weighted sum, then a squashing function ===")
x = np.array([0.5, -1.0, 2.0])
w = np.array([0.8, 0.2, -0.5])
bias = 0.1
z = float(x @ w + bias)
print(f"inputs {x.tolist()} | weights {w.tolist()} | bias {bias}")
print(f"z = 0.5*0.8 + (-1.0)*0.2 + 2.0*(-0.5) + 0.1 = {z:.2f}")
print(f"sigmoid(z) = {1 / (1 + np.exp(-z)):.3f} | tanh(z) = {np.tanh(z):.3f} | relu(z) = {max(z, 0):.3f}")

print("\n=== 2. Why one neuron is not enough: XOR ===")
rng = np.random.default_rng(0)
Xx = rng.integers(0, 2, size=(400, 2)).astype(float)
yx = (Xx[:, 0] != Xx[:, 1]).astype(int)
Xx = Xx + rng.normal(0, 0.1, Xx.shape)
linear = LogisticRegression().fit(Xx, yx)
print(f"logistic regression (a single layer, a straight line) on XOR: accuracy {linear.score(Xx, yx):.1%}")
net_xor = MLP([2, 8, 2], activation="tanh", seed=1)
net_xor.fit(Xx[:300], yx[:300], Xx[300:], yx[300:], epochs=300, lr=0.1, batch=50, patience=300, log_every=100)
print(f"network with one hidden layer (2 -> 8 -> 2) on held-out XOR points: accuracy {(net_xor.predict(Xx[300:]) == yx[300:]).mean():.1%}")
print("the hidden layer bends the space so a straight line can finish the job")

print("\n=== 3. Activation functions and their slope (the slope is what backprop multiplies by) ===")
points = np.array([-5.0, -2.0, 0.0, 2.0, 5.0])
sig = 1 / (1 + np.exp(-points))
print(f"{'z':>6} {'sigmoid':>9} {'slope':>8} {'tanh':>8} {'slope':>8} {'relu':>6} {'slope':>6}")
for zi, s, t, r in zip(points, sig, np.tanh(points), np.maximum(points, 0)):
    print(f"{zi:6.1f} {s:9.4f} {s * (1 - s):8.4f} {t:8.4f} {1 - t**2:8.4f} {r:6.1f} {float(zi > 0):6.1f}")
print("sigmoid and tanh go flat at both ends (slope near 0). relu keeps slope 1 for positive inputs")

print("\n=== 4. Gradient check: is my backpropagation correct? ===")
rng = np.random.default_rng(1)
Xg = rng.normal(size=(30, 6))
yg = rng.integers(0, 3, 30)
for activation in ("relu", "tanh", "sigmoid"):
    error = gradient_check(MLP([6, 8, 5, 3], activation=activation, seed=3), Xg, yg)
    assert error < 1e-5, (activation, error)
    print(f"{activation:8} largest relative difference, backprop vs nudging each weight by hand: {error:.2e}")
print("backprop is just the chain rule. If it matches the slow numerical estimate, the formulas are right")

print("\n=== 5. Vanishing gradients: how much learning signal reaches the FIRST layer of a deep net? ===")
Xd = rng.normal(size=(64, 10))
yd = rng.integers(0, 3, 64)
for activation in ("sigmoid", "relu"):
    norms = layer_gradient_norms(MLP([10] + [16] * 8 + [3], activation=activation, seed=0), Xd, yd)
    print(f"{activation:8} gradient size at first layer {norms[0]:.2e} | at last layer {norms[-1]:.2e} | ratio first/last {norms[0] / norms[-1]:.2e}")
print("with sigmoid the signal shrinks by the slope (<= 0.25) at every layer. This is why plain deep/recurrent nets forget")
print("the distant past, and why LSTMs (Day 51-53) were invented")

print("\n=== 6. Our trading data: 26 features -> 16 hidden -> 3 classes (sell, hold, buy) ===")
X, labels = load_model_frame("BTCUSDT", "1h", 12, 2.0)
X_tr, X_te, lab_tr, lab_te = purged_split(X, labels, test_frac=0.3)
cut = int(len(X_tr) * 0.85)
X_fit, X_val = X_tr.iloc[: cut - 12], X_tr.iloc[cut:]
y_fit, y_val = lab_tr["label"].iloc[: cut - 12].to_numpy() + 1, lab_tr["label"].iloc[cut:].to_numpy() + 1
prep = make_pipeline(Winsorizer(), StandardScaler()).fit(X_fit)
class_weight = compute_class_weight("balanced", classes=np.array([0, 1, 2]), y=y_fit)
net = MLP([X.shape[1], 16, 3], activation="relu", seed=0)
print(f"parameters to learn: {sum(w.size for w in net.W) + sum(b.size for b in net.b)} | train rows {len(X_fit)} | validation rows {len(X_val)} | test rows {len(X_te)}")
history, best_epoch = net.fit(prep.transform(X_fit), y_fit, prep.transform(X_val), y_val, class_weight=class_weight, epochs=150, lr=0.02, batch=256, patience=15)
pred = net.predict(prep.transform(X_te)) - 1
e = evaluate(lab_te["label"], pred, lab_te["ret"])
base_logit = make_logistic().fit(X_tr, lab_tr["label"])
e_logit = evaluate(lab_te["label"], base_logit.predict(X_te), lab_te["ret"])
print(f"best epoch {best_epoch} (weights restored to that epoch)")
print(f"{'model':16} {'bal.acc':>8} {'trades':>7} {'net bps/trade':>14} {'p-value':>8}")
print(f"{'numpy MLP':16} {e['balanced_accuracy']:8.3f} {e['trades']:7} {e['net_bps_per_trade']:14.1f} {e['p_value']:8.3f}")
print(f"{'logistic (Day 42)':16} {e_logit['balanced_accuracy']:8.3f} {e_logit['trades']:7} {e_logit['net_bps_per_trade']:14.1f} {e_logit['p_value']:8.3f}")
first, last = history[0], history[-1]
print(f"train loss {first[1]:.3f} -> {last[1]:.3f} | validation loss {first[2]:.3f} -> {last[2]:.3f}: when validation stops falling, training should stop")
