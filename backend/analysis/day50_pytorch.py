import numpy as np
import torch
from torch import nn

from analysis.baseline_models import make_logistic
from analysis.evaluation import evaluate
from analysis.ml_features import load_model_frame, purged_split
from analysis.nn_numpy import MLP
from analysis.torch_nn import fit_torch

print(f"PyTorch {torch.__version__} | default dtype {torch.get_default_dtype()} | cuda available: {torch.cuda.is_available()}")

print("\n=== 1. Tensors: numpy arrays with a shape, a dtype and (optionally) gradients ===")
a = torch.tensor([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
print(f"a.shape {tuple(a.shape)} | a.dtype {a.dtype}")
print("a @ a.T =", (a @ a.T).tolist())
print("broadcasting a + [10, 20, 30] =", (a + torch.tensor([10.0, 20.0, 30.0])).tolist())
n = np.array([1.0, 2.0, 3.0])
shared = torch.from_numpy(n)
n[0] = 99.0
print(f"torch.from_numpy SHARES memory: after changing the numpy array, the tensor shows {shared.tolist()}")
safe = torch.from_numpy(n).clone()
n[0] = 1.0
print(f"after .clone() the tensor is independent: {safe.tolist()}")
try:
    torch.ones(2, 2, dtype=torch.float64) @ torch.ones(2, 2)
except RuntimeError as exc:
    print("pandas gives float64, torch layers want float32. Mixing them fails:", str(exc).splitlines()[0][:70])

print("\n=== 2. Autograd: PyTorch records operations and differentiates them for you ===")
x = torch.tensor(2.0, requires_grad=True)
y = x**2 + 3 * x
y.backward()
print(f"y = x^2 + 3x at x=2: dy/dx = 2x + 3 = 7. autograd says {x.grad.item()}")
y2 = x**2 + 3 * x
y2.backward()
print(f"calling backward again ADDS to the old value: {x.grad.item()}  (this is why training loops call optimizer.zero_grad())")
with torch.no_grad():
    frozen = x * 2
print(f"inside torch.no_grad() nothing is tracked: requires_grad = {frozen.requires_grad}")

torch.manual_seed(0)
xs = torch.linspace(-2, 2, 50)
ys = 3 * xs + 1 + 0.05 * torch.randn(50)
w = torch.zeros(1, requires_grad=True)
b = torch.zeros(1, requires_grad=True)
for _ in range(200):
    loss = ((w * xs + b - ys) ** 2).mean()
    loss.backward()
    with torch.no_grad():
        w -= 0.1 * w.grad
        b -= 0.1 * b.grad
    w.grad.zero_()
    b.grad.zero_()
print(f"learning y = 3x + 1 by gradient descent: w = {w.item():.2f}, b = {b.item():.2f}, loss {loss.item():.4f}")

print("\n=== 3. Does PyTorch agree with the backprop we wrote by hand on Day 49? ===")
rng = np.random.default_rng(0)
Xs = rng.normal(size=(20, 4))
ys_int = rng.integers(0, 3, 20)
numpy_net = MLP([4, 5, 3], activation="relu", seed=1)
numpy_loss = numpy_net.loss(Xs, ys_int)
numpy_grads = numpy_net.backward(Xs, ys_int)
torch_net = nn.Sequential(nn.Linear(4, 5), nn.ReLU(), nn.Linear(5, 3)).double()
with torch.no_grad():
    for layer, W, bias in zip((torch_net[0], torch_net[2]), numpy_net.W, numpy_net.b):
        layer.weight.copy_(torch.from_numpy(np.ascontiguousarray(W.T)))
        layer.bias.copy_(torch.from_numpy(bias.copy()))
torch_loss = nn.functional.cross_entropy(torch_net(torch.from_numpy(Xs)), torch.from_numpy(ys_int).long())
torch_loss.backward()
assert abs(torch_loss.item() - numpy_loss) < 1e-9
for layer, (dW, db) in zip((torch_net[0], torch_net[2]), numpy_grads):
    np.testing.assert_allclose(layer.weight.grad.numpy(), dW.T, rtol=1e-6, atol=1e-9)
    np.testing.assert_allclose(layer.bias.grad.numpy(), db, rtol=1e-6, atol=1e-9)
print(f"loss: numpy {numpy_loss:.6f} | torch {torch_loss.item():.6f}")
print("every weight and bias gradient matches (our hand-written chain rule == autograd)")

print("\n=== 4. Dropout: random switching-off while training, never while predicting ===")
torch.manual_seed(0)
drop = nn.Dropout(0.5)
ones = torch.ones(1, 8)
drop.train()
print("train mode, two passes:", drop(ones).tolist()[0], drop(ones).tolist()[0])
drop.eval()
print("eval mode, two passes: ", drop(ones).tolist()[0], drop(ones).tolist()[0])
print("always call model.eval() before predicting and model.train() before training")

print("\n=== 5. A real feed-forward network on our trading data (BTCUSDT 1h) ===")
X, labels = load_model_frame("BTCUSDT", "1h", 12, 2.0)
X_tr, X_te, lab_tr, lab_te = purged_split(X, labels, test_frac=0.3)
cut = int(len(X_tr) * 0.85)
X_fit, X_val = X_tr.iloc[: cut - 12], X_tr.iloc[cut:]
y_fit, y_val = lab_tr["label"].iloc[: cut - 12], lab_tr["label"].iloc[cut:]
model = fit_torch(X_fit, y_fit, X_val, y_val, hidden=(32, 16), dropout=0.2, lr=1e-3, weight_decay=1e-4)
parameters = sum(p.numel() for p in model.model.parameters())
print(f"parameters: {parameters} | best epoch {model.best_epoch} (weights restored to it) | train rows {len(X_fit)}")
print(f"rows per parameter: {len(X_fit) / parameters:.1f} (fewer than ~10 is a warning for overfitting)")

pred = model.predict(X_te)
e = evaluate(lab_te["label"], pred, lab_te["ret"])
e_logit = evaluate(lab_te["label"], make_logistic().fit(X_tr, lab_tr["label"]).predict(X_te), lab_te["ret"])
print(f"\n{'model':22} {'bal.acc':>8} {'trades':>7} {'net bps/trade':>14} {'p-value':>8}")
print(f"{'PyTorch feed-forward':22} {e['balanced_accuracy']:8.3f} {e['trades']:7} {e['net_bps_per_trade']:14.1f} {e['p_value']:8.3f}")
print(f"{'logistic (Day 42)':22} {e_logit['balanced_accuracy']:8.3f} {e_logit['trades']:7} {e_logit['net_bps_per_trade']:14.1f} {e_logit['p_value']:8.3f}")
print("a neural network is not automatically better than a simple model: tabular, noisy data is where it usually is not")
