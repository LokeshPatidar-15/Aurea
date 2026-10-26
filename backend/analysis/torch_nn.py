import copy

import numpy as np
import pandas as pd
import torch
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_class_weight
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from analysis.ml_features import Winsorizer


class FeedForward(nn.Module):
    def __init__(self, n_in: int, hidden: tuple = (32, 16), n_out: int = 3, dropout: float = 0.2):
        super().__init__()
        layers, previous = [], n_in
        for width in hidden:
            layers += [nn.Linear(previous, width), nn.ReLU(), nn.Dropout(dropout)]
            previous = width
        layers.append(nn.Linear(previous, n_out))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def as_float_tensor(values) -> torch.Tensor:
    return torch.as_tensor(np.asarray(values, dtype=np.float32))


def as_label_tensor(values) -> torch.Tensor:
    return torch.as_tensor(np.asarray(values, dtype=np.int64))


class TorchSignalModel:
    def __init__(self, prep, model: nn.Module, history: pd.DataFrame, best_epoch: int):
        self.prep = prep
        self.model = model
        self.history = history
        self.best_epoch = best_epoch

    def predict_proba(self, X) -> np.ndarray:
        self.model.eval()
        with torch.no_grad():
            logits = self.model(as_float_tensor(self.prep.transform(X)))
        return torch.softmax(logits, dim=1).numpy()

    def predict(self, X) -> np.ndarray:
        return self.predict_proba(X).argmax(axis=1) - 1


def fit_torch(
    X_fit, y_fit, X_val, y_val,
    hidden: tuple = (32, 16), dropout: float = 0.2, lr: float = 1e-3, weight_decay: float = 1e-4,
    batch: int = 256, epochs: int = 200, patience: int = 15, seed: int = 0, log_every: int = 10,
) -> TorchSignalModel:
    torch.manual_seed(seed)
    y_fit = np.asarray(y_fit) + 1
    y_val = np.asarray(y_val) + 1
    prep = make_pipeline(Winsorizer(), StandardScaler()).fit(X_fit)
    Xf, Xv = as_float_tensor(prep.transform(X_fit)), as_float_tensor(prep.transform(X_val))
    yf, yv = as_label_tensor(y_fit), as_label_tensor(y_val)

    model = FeedForward(Xf.shape[1], hidden, 3, dropout)
    weights = torch.as_tensor(compute_class_weight("balanced", classes=np.array([0, 1, 2]), y=y_fit), dtype=torch.float32)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    loader = DataLoader(TensorDataset(Xf, yf), batch_size=batch, shuffle=True, generator=torch.Generator().manual_seed(seed))

    rows, best_loss, best_state, best_epoch = [], float("inf"), copy.deepcopy(model.state_dict()), 0
    for epoch in range(1, epochs + 1):
        model.train()
        for xb, yb in loader:
            optimizer.zero_grad()
            loss = loss_fn(model(xb), yb)
            loss.backward()
            optimizer.step()
        model.eval()
        with torch.no_grad():
            train_loss = loss_fn(model(Xf), yf).item()
            val_loss = loss_fn(model(Xv), yv).item()
        rows.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        if val_loss < best_loss - 1e-5:
            best_loss, best_state, best_epoch = val_loss, copy.deepcopy(model.state_dict()), epoch
        if log_every and (epoch % log_every == 0 or epoch == 1):
            print(f"  epoch {epoch:4} | train loss {train_loss:.4f} | validation loss {val_loss:.4f}")
        if epoch - best_epoch >= patience:
            print(f"  early stop at epoch {epoch}: validation loss has not improved since epoch {best_epoch}")
            break
    model.load_state_dict(best_state)
    return TorchSignalModel(prep, model, pd.DataFrame(rows), best_epoch)
