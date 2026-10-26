import numpy as np


def sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


class LSTMCell:
    def __init__(self, n_in: int, n_hidden: int, forget_bias: float = 1.0, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.n_in, self.n_hidden = n_in, n_hidden
        scale = 1.0 / np.sqrt(n_hidden)
        self.W = rng.uniform(-scale, scale, (n_in + n_hidden, 4 * n_hidden))
        self.b = np.zeros(4 * n_hidden)
        self.b[n_hidden:2 * n_hidden] = forget_bias

    def step(self, x: np.ndarray, h: np.ndarray, c: np.ndarray):
        H = self.n_hidden
        z = np.concatenate([x, h]) @ self.W + self.b
        i, f, g, o = sigmoid(z[:H]), sigmoid(z[H:2 * H]), np.tanh(z[2 * H:3 * H]), sigmoid(z[3 * H:])
        c_new = f * c + i * g
        h_new = o * np.tanh(c_new)
        return h_new, c_new, {"input": i, "forget": f, "candidate": g, "output": o}

    def run(self, X: np.ndarray):
        h, c = np.zeros(self.n_hidden), np.zeros(self.n_hidden)
        hs, cs, gates = [], [], []
        for x in X:
            h, c, g = self.step(x, h, c)
            hs.append(h)
            cs.append(c)
            gates.append(g)
        return np.array(hs), np.array(cs), gates
