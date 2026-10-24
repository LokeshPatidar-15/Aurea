import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

from analysis.common import OUTPUT_DIR
from analysis.ml_data import chronological_split, load_dataset_from_db

SYMBOL, TIMEFRAME, HORIZON = "BTCUSDT", "1h", 4

X, y = load_dataset_from_db(SYMBOL, TIMEFRAME, HORIZON)

print("=== 1. Features (X) and label (y) ===")
print(f"X shape: {X.shape} | {X.index[0]:%Y-%m-%d} -> {X.index[-1]:%Y-%m-%d}")
print("label y = 1 if close is higher {} candles later, else 0 (toy label: Day 40 designs the real one)".format(HORIZON))
share_up = y.mean()
baseline = max(share_up, 1 - share_up)
print(f"share of y=1: {share_up:.1%} | majority-class baseline accuracy: {baseline:.1%}")

print("\n=== 2. Two ways to split the same data ===")
X_tr, X_te, y_tr, y_te = chronological_split(X, y, test_frac=0.3, embargo=HORIZON)
print(f"chronological: train {len(X_tr)} (oldest) | test {len(X_te)} (newest) | {HORIZON}-candle embargo between them")
Xr_tr, Xr_te, yr_tr, yr_te = train_test_split(X, y, test_size=0.3, shuffle=True, random_state=0)
print(f"random shuffle: train {len(Xr_tr)} | test {len(Xr_te)} (test rows sit right next to train rows)")

tree_chrono = DecisionTreeClassifier(random_state=0).fit(X_tr, y_tr)
tree_random = DecisionTreeClassifier(random_state=0).fit(Xr_tr, yr_tr)
acc_chrono = tree_chrono.score(X_te, y_te)
acc_random = tree_random.score(Xr_te, yr_te)
print(f"\nunlimited-depth tree, test accuracy | chronological split: {acc_chrono:.1%} | random split: {acc_random:.1%}")
print(f"difference (random minus chronological): {100 * (acc_random - acc_chrono):+.1f} points")
print("a positive difference is leakage: neighbouring candles let the tree 'recognise' test rows it has effectively seen")

print("\n=== 3. Overfitting: train vs test accuracy as the tree gets deeper ===")
depths = [1, 2, 3, 5, 8, 12, 20, None]
rows = []
for depth in depths:
    model = DecisionTreeClassifier(max_depth=depth, random_state=0).fit(X_tr, y_tr)
    rows.append({"max_depth": "None" if depth is None else depth, "train_acc": model.score(X_tr, y_tr), "test_acc": model.score(X_te, y_te)})
curve = pd.DataFrame(rows)
curve["gap"] = curve["train_acc"] - curve["test_acc"]
print(curve.round(3).to_string(index=False))
test_baseline = max(y_te.mean(), 1 - y_te.mean())
print(f"majority baseline on the test period: {test_baseline:.3f}")

print("\n=== 4. A simple honest model: scaled logistic regression ===")
logit = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000)).fit(X_tr, y_tr)
logit_acc = logit.score(X_te, y_te)
print(f"logistic regression test accuracy: {logit_acc:.1%} | majority baseline: {test_baseline:.1%} | edge over baseline: {100 * (logit_acc - test_baseline):+.1f} points")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
fig, ax = plt.subplots(figsize=(8, 4))
positions = range(len(curve))
ax.plot(positions, curve["train_acc"], color="#2a78d6", linewidth=1.6, marker="o", markersize=4, label="train accuracy")
ax.plot(positions, curve["test_acc"], color="#eb6834", linewidth=1.6, marker="o", markersize=4, label="test accuracy (newest 30%)")
ax.axhline(test_baseline, color="#52514e", linewidth=0.9, linestyle="--", label="majority baseline")
ax.set_xticks(list(positions), curve["max_depth"].astype(str))
ax.set_xlabel("tree max_depth", color="#52514e", fontsize=9)
ax.set_ylabel("accuracy", color="#52514e", fontsize=9)
ax.set_title("Train vs test accuracy by tree depth", loc="left", fontsize=12)
ax.legend(frameon=False, fontsize=9, labelcolor="#52514e")
ax.grid(axis="y", color="#e3e2de", linewidth=0.6)
ax.set_axisbelow(True)
for side in ["top", "right", "left"]:
    ax.spines[side].set_visible(False)
fig.set_facecolor("#fcfcfb")
ax.set_facecolor("#fcfcfb")
fig.tight_layout()
path = OUTPUT_DIR / "day39_overfitting.png"
fig.savefig(path, dpi=140, facecolor=fig.get_facecolor())
print(f"\nchart saved: {path}")
