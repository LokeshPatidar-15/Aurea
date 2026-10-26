import copy

import numpy as np
import pandas as pd
import torch
from sklearn.utils.class_weight import compute_class_weight
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


class LSTMClassifier(nn.Module):
    def __init__(self, n_in: int, hidden: int = 32, n_out: int = 3, dropout: float = 0.3):
        super().__init__()
        self.hidden = hidden
        self.lstm = nn.LSTM(n_in, hidden, batch_first=True)
        self.drop = nn.Dropout(dropout)
        self.head = nn.Linear(hidden, n_out)
        with torch.no_grad():
            self.lstm.bias_ih_l0[hidden:2 * hidden].fill_(1.0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (h_last, _) = self.lstm(x)
        return self.head(self.drop(h_last[-1]))


def batched_logits(model: nn.Module, X: torch.Tensor, batch: int = 1024) -> torch.Tensor:
    model.eval()
    parts = []
    with torch.no_grad():
        for start in range(0, len(X), batch):
            parts.append(model(X[start:start + batch]))
    return torch.cat(parts)


class LSTMSignalModel:
    def __init__(self, model: nn.Module, history: pd.DataFrame, best_epoch: int):
        self.model = model
        self.history = history
        self.best_epoch = best_epoch

    def predict_proba(self, windows: np.ndarray) -> np.ndarray:
        logits = batched_logits(self.model, torch.as_tensor(np.asarray(windows, dtype=np.float32)))
        return torch.softmax(logits, dim=1).numpy()

    def predict(self, windows: np.ndarray) -> np.ndarray:
        return self.predict_proba(windows).argmax(axis=1) - 1


def fit_lstm(
    sets: dict, hidden: int = 32, dropout: float = 0.3, lr: float = 1e-3, weight_decay: float = 1e-4,
    batch: int = 128, epochs: int = 60, patience: int = 8, clip: float = 1.0, seed: int = 0, log_every: int = 5,
) -> LSTMSignalModel:
    torch.manual_seed(seed)
    Xf = torch.as_tensor(sets["fit"]["X"])
    yf = torch.as_tensor(sets["fit"]["y"])
    Xv = torch.as_tensor(sets["val"]["X"])
    yv = torch.as_tensor(sets["val"]["y"])
    model = LSTMClassifier(Xf.shape[2], hidden, 3, dropout)
    weights = torch.as_tensor(compute_class_weight("balanced", classes=np.array([0, 1, 2]), y=sets["fit"]["y"]), dtype=torch.float32)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    loader = DataLoader(TensorDataset(Xf, yf), batch_size=batch, shuffle=True, generator=torch.Generator().manual_seed(seed))

    rows, best_loss, best_state, best_epoch = [], float("inf"), copy.deepcopy(model.state_dict()), 0
    for epoch in range(1, epochs + 1):
        model.train()
        for xb, yb in loader:
            optimizer.zero_grad()
            loss_fn(model(xb), yb).backward()
            nn.utils.clip_grad_norm_(model.parameters(), clip)
            optimizer.step()
        train_loss = loss_fn(batched_logits(model, Xf), yf).item()
        val_loss = loss_fn(batched_logits(model, Xv), yv).item()
        rows.append({"epoch": epoch, "train_loss": train_loss, "val_loss": val_loss})
        if val_loss < best_loss - 1e-5:
            best_loss, best_state, best_epoch = val_loss, copy.deepcopy(model.state_dict()), epoch
        if log_every and (epoch % log_every == 0 or epoch == 1):
            print(f"  epoch {epoch:3} | train loss {train_loss:.4f} | validation loss {val_loss:.4f}")
        if epoch - best_epoch >= patience:
            print(f"  early stop at epoch {epoch}: validation loss has not improved since epoch {best_epoch}")
            break
    model.load_state_dict(best_state)
    return LSTMSignalModel(model, pd.DataFrame(rows), best_epoch)
