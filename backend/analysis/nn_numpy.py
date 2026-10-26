import numpy as np


def _activation(name: str):
    if name == "relu":
        return (lambda z: np.maximum(z, 0.0)), (lambda z, a: (z > 0).astype(float))
    if name == "tanh":
        return np.tanh, (lambda z, a: 1.0 - a**2)
    if name == "sigmoid":
        return (lambda z: 1.0 / (1.0 + np.exp(-z))), (lambda z, a: a * (1.0 - a))
    raise ValueError(f"unknown activation {name!r}")


def softmax(logits: np.ndarray) -> np.ndarray:
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    return exp / exp.sum(axis=1, keepdims=True)


class MLP:
    def __init__(self, sizes: list[int], activation: str = "relu", seed: int = 0):
        rng = np.random.default_rng(seed)
        self.sizes = sizes
        self.activation = activation
        self.act, self.dact = _activation(activation)
        self.W, self.b = [], []
        for n_in, n_out in zip(sizes[:-1], sizes[1:]):
            scale = np.sqrt(2.0 / n_in) if activation == "relu" else np.sqrt(1.0 / n_in)
            self.W.append(rng.normal(0.0, scale, (n_in, n_out)))
            self.b.append(np.zeros(n_out))

    def forward(self, X: np.ndarray):
        a = np.asarray(X, dtype=float)
        zs, activations = [], [a]
        last = len(self.W) - 1
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            z = a @ W + b
            zs.append(z)
            a = z if i == last else self.act(z)
            activations.append(a)
        return softmax(zs[-1]), zs, activations

    def loss(self, X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None) -> float:
        probs, _, _ = self.forward(X)
        nll = -np.log(probs[np.arange(len(y)), y] + 1e-12)
        w = np.ones(len(y)) if sample_weight is None else sample_weight
        return float((w * nll).sum() / w.sum())

    def backward(self, X: np.ndarray, y: np.ndarray, sample_weight: np.ndarray | None = None):
        probs, zs, activations = self.forward(X)
        n = len(y)
        w = np.ones(n) if sample_weight is None else sample_weight
        dz = probs.copy()
        dz[np.arange(n), y] -= 1.0
        dz *= (w / w.sum())[:, None]
        grads = [None] * len(self.W)
        for i in reversed(range(len(self.W))):
            grads[i] = (activations[i].T @ dz, dz.sum(axis=0))
            if i > 0:
                da = dz @ self.W[i].T
                dz = da * self.dact(zs[i - 1], activations[i])
        return grads

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.forward(X)[0]

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.predict_proba(X).argmax(axis=1)

    def get_params(self):
        return [w.copy() for w in self.W], [b.copy() for b in self.b]

    def set_params(self, params) -> None:
        self.W, self.b = [w.copy() for w in params[0]], [b.copy() for b in params[1]]

    def fit(self, X, y, X_val, y_val, class_weight=None, epochs=150, lr=0.05, momentum=0.9, batch=256, patience=15, seed=0, log_every=25):
        rng = np.random.default_rng(seed)
        X, X_val = np.asarray(X, dtype=float), np.asarray(X_val, dtype=float)
        sw = None if class_weight is None else class_weight[y]
        sw_val = None if class_weight is None else class_weight[y_val]
        vW = [np.zeros_like(w) for w in self.W]
        vb = [np.zeros_like(b) for b in self.b]
        history, best = [], (np.inf, None, 0)
        for epoch in range(1, epochs + 1):
            order = rng.permutation(len(X))
            for start in range(0, len(X), batch):
                idx = order[start:start + batch]
                grads = self.backward(X[idx], y[idx], None if sw is None else sw[idx])
                for i, (dW, db) in enumerate(grads):
                    vW[i] = momentum * vW[i] - lr * dW
                    vb[i] = momentum * vb[i] - lr * db
                    self.W[i] += vW[i]
                    self.b[i] += vb[i]
            train_loss = self.loss(X, y, sw)
            val_loss = self.loss(X_val, y_val, sw_val)
            history.append((epoch, train_loss, val_loss))
            if val_loss < best[0] - 1e-5:
                best = (val_loss, self.get_params(), epoch)
            if log_every and (epoch % log_every == 0 or epoch == 1):
                print(f"  epoch {epoch:4} | train loss {train_loss:.4f} | validation loss {val_loss:.4f}")
            if epoch - best[2] >= patience:
                print(f"  early stop at epoch {epoch}: validation loss has not improved since epoch {best[2]}")
                break
        self.set_params(best[1])
        return history, best[2]


def gradient_check(net: MLP, X, y, eps: float = 1e-5, n_checks: int = 12, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    analytic = net.backward(X, y)
    worst = 0.0
    for _ in range(n_checks):
        layer = int(rng.integers(len(net.W)))
        is_weight = bool(rng.integers(2))
        target = net.W[layer] if is_weight else net.b[layer]
        index = tuple(int(rng.integers(s)) for s in target.shape)
        original = target[index]
        target[index] = original + eps
        up = net.loss(X, y)
        target[index] = original - eps
        down = net.loss(X, y)
        target[index] = original
        numeric = (up - down) / (2 * eps)
        exact = analytic[layer][0 if is_weight else 1][index]
        worst = max(worst, abs(exact - numeric) / max(abs(exact) + abs(numeric), 1e-12))
    return worst


def layer_gradient_norms(net: MLP, X, y) -> list[float]:
    return [float(np.linalg.norm(dW)) for dW, _ in net.backward(X, y)]
