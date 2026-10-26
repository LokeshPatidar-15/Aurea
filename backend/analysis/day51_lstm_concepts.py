import numpy as np
import pandas as pd

from analysis.lstm_numpy import LSTMCell
from analysis.ml_features import load_model_frame
from analysis.sequences import build_sequence_sets

print("=== 1. A recurrent net reads a sequence one step at a time and carries a memory ===")
print("plain RNN:  h_t = tanh(W_x x_t + W_h h_(t-1) + b)")
print("every step multiplies the old memory by W_h and squashes it, so after 50 steps almost nothing of step 1 is left")

print("\n=== 2. One LSTM step, with the numbers visible ===")
cell = LSTMCell(n_in=3, n_hidden=4, forget_bias=1.0, seed=0)
x = np.array([0.5, -1.0, 2.0])
h0, c0 = np.zeros(4), np.array([1.0, -1.0, 0.5, 2.0])
h1, c1, g = cell.step(x, h0, c0)
print(f"old cell state c_(t-1): {c0.round(2).tolist()}")
print(f"forget gate f  (0 = erase, 1 = keep):    {g['forget'].round(2).tolist()}")
print(f"input gate  i  (0 = ignore, 1 = write):  {g['input'].round(2).tolist()}")
print(f"candidate   g  (what could be written):  {g['candidate'].round(2).tolist()}")
print(f"output gate o  (what is shown as h):     {g['output'].round(2).tolist()}")
print(f"new cell state c_t = f*c_(t-1) + i*g:    {c1.round(2).tolist()}")
print(f"new hidden state h_t = o*tanh(c_t):      {h1.round(2).tolist()}")
assert np.allclose(c1, g["forget"] * c0 + g["input"] * g["candidate"])
print("the cell state is a conveyor belt: it changes only by multiplying with f and adding i*g")

print("\n=== 3. Why that fixes forgetting: how much of step 1 survives after T steps? ===")
print(f"{'forget gate f':>14} {'T=10':>10} {'T=48':>10} {'T=100':>10}")
for f in (0.5, 0.9, 0.99):
    print(f"{f:14.2f} {f**10:10.2e} {f**48:10.2e} {f**100:10.2e}")
print("a gate near 1 keeps the memory almost intact. That is why PyTorch users often start the forget bias at 1")

print("\n=== 4. Gates on a real-shaped sequence (random 48-step input) ===")
rng = np.random.default_rng(1)
Xseq = rng.normal(size=(48, 3))
hs, cs, gates = LSTMCell(3, 4, forget_bias=1.0, seed=2).run(Xseq)
mean_f = float(np.mean([gt["forget"].mean() for gt in gates]))
print(f"hidden states {hs.shape} | cell states {cs.shape} | average forget gate {mean_f:.2f} (starts high because bias = 1)")

print("\n=== 5. Gradient that reaches the FIRST time step: RNN vs LSTM (PyTorch autograd) ===")
import torch
from torch import nn


def first_step_gradient(make_layer, T: int, seeds: int = 20, features: int = 8, hidden: int = 16) -> float:
    norms = []
    for seed in range(seeds):
        torch.manual_seed(seed)
        layer = make_layer(features, hidden)
        data = torch.randn(1, T, features, requires_grad=True)
        out, _ = layer(data)
        out[:, -1].sum().backward()
        norms.append(data.grad[0, 0].norm().item())
    return float(np.mean(norms))


def lstm_forget_one(features, hidden):
    layer = nn.LSTM(features, hidden, batch_first=True)
    with torch.no_grad():
        layer.bias_ih_l0[hidden:2 * hidden].fill_(1.0)
    return layer


makers = {
    "RNN (tanh)": lambda f, h: nn.RNN(f, h, batch_first=True),
    "LSTM default": lambda f, h: nn.LSTM(f, h, batch_first=True),
    "LSTM forget bias 1": lstm_forget_one,
}
print(f"{'gradient at step 1':22} {'T=5':>10} {'T=25':>10} {'T=100':>10}   (average of 20 random starts)")
for name, maker in makers.items():
    row = [first_step_gradient(maker, T) for T in (5, 25, 100)]
    print(f"{name:22} {row[0]:10.2e} {row[1]:10.2e} {row[2]:10.2e}")
print("the plain RNN signal collapses with length. The LSTM keeps far more of it. This is why we use LSTM, not RNN")

print("\n=== 6. Turning our candles into sequences: shape (samples, 48 steps, features) ===")
X, labels = load_model_frame("BTCUSDT", "1h", 12, 2.0)
sets, Z = build_sequence_sets(X, labels, length=48)
for name in ("fit", "val", "test"):
    part = sets[name]
    counts = np.bincount(part["y"], minlength=3)
    print(f"{name:5} windows {part['X'].shape} | labels sell/hold/buy {counts.tolist()}")
size_mb = sum(sets[n]["X"].nbytes for n in ("fit", "val", "test")) / 1e6
print(f"memory for all windows: {size_mb:.1f} MB (float32). Fine now. With years of data we would cut windows batch by batch instead")

print("\n=== 7. No-lookahead check for sequences ===")
test = sets["test"]
k = len(test["positions"]) // 2
pos = int(test["positions"][k])
Xcut = X.copy()
Xcut.iloc[pos + 1:] = 9999.0
Zcut = sets["prep"].transform(Xcut).astype(np.float32)
window_before = test["X"][k]
window_after = Zcut[pos - 47: pos + 1]
assert np.allclose(window_before, window_after)
print(f"destroyed every row after window {k}: the window is identical, so it only uses the past")
first_test_time = X.index[sets["test"]["positions"][0]]
last_fit_time = X.index[sets["fit"]["positions"][-1]]
print(f"last training sample time {last_fit_time} < first test sample time {first_test_time}")
assert last_fit_time < first_test_time
print("windows of test samples may look back into the training period. Only the LABEL period is purged, because the features are past data")
