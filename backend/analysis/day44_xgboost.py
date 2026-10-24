import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from analysis.baseline_models import make_logistic
from analysis.common import OUTPUT_DIR
from analysis.evaluation import evaluate
from analysis.ml_features import load_model_frame, purged_split

HORIZON, K = 12, 2.0
SYMBOLS = ("BTCUSDT", "XAUUSD", "EURUSD")


def fit_xgb(X_tr: pd.DataFrame, y_tr: pd.Series) -> XGBClassifier:
    cut = int(len(X_tr) * 0.85)
    X_fit, y_fit = X_tr.iloc[: cut - HORIZON], y_tr.iloc[: cut - HORIZON] + 1
    X_val, y_val = X_tr.iloc[cut:], y_tr.iloc[cut:] + 1
    model = XGBClassifier(
        objective="multi:softprob",
        n_estimators=500,
        learning_rate=0.03,
        max_depth=3,
        min_child_weight=20,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_lambda=5.0,
        eval_metric="mlogloss",
        early_stopping_rounds=30,
        random_state=0,
        n_jobs=-1,
    )
    model.fit(X_fit, y_fit, sample_weight=compute_sample_weight("balanced", y_fit), eval_set=[(X_val, y_val)], verbose=False)
    return model


def predict_xgb(model: XGBClassifier, X: pd.DataFrame) -> np.ndarray:
    return model.predict(X).astype(int) - 1


def permutation_drop(model, X: pd.DataFrame, y: np.ndarray, repeats: int = 5, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    base = balanced_accuracy_score(y, predict_xgb(model, X))
    drops = {}
    for col in X.columns:
        scores = []
        for _ in range(repeats):
            shuffled = X.copy()
            shuffled[col] = rng.permutation(shuffled[col].to_numpy())
            scores.append(balanced_accuracy_score(y, predict_xgb(model, shuffled)))
        drops[col] = base - float(np.mean(scores))
    return pd.Series(drops)


rows = []
btc = None
for symbol in SYMBOLS:
    X, labels = load_model_frame(symbol, "1h", HORIZON, K)
    X_tr, X_te, lab_tr, lab_te = purged_split(X, labels, test_frac=0.3)
    y_tr, y_te = lab_tr["label"], lab_te["label"]

    logit = make_logistic().fit(X_tr, y_tr)
    xgb = fit_xgb(X_tr, y_tr)
    for name, pred, train_pred in (
        ("logistic", logit.predict(X_te), logit.predict(X_tr)),
        ("xgboost", predict_xgb(xgb, X_te), predict_xgb(xgb, X_tr)),
    ):
        e = evaluate(y_te, pred, lab_te["ret"])
        rows.append({
            "symbol": symbol, "model": name,
            "train_bal": balanced_accuracy_score(y_tr, train_pred), "test_bal": e["balanced_accuracy"],
            "trades": e["trades"], "win": e["win_rate"], "net_bps": e["net_bps_per_trade"], "p": e["p_value"],
        })
    if symbol == "BTCUSDT":
        btc = (xgb, X_te, y_te)
        print("=== 1. XGBoost training (BTCUSDT) ===")
        print(f"trees kept after early stopping: {xgb.best_iteration + 1} of 500 | train rows {len(X_tr)} | test rows {len(X_te)}")
        print("early stopping watches a validation slice taken from the END of the training period (never the test set)\n")

print("=== 2. Logistic regression vs XGBoost (same data, same split, same costs) ===")
table = pd.DataFrame(rows)
print(f"{'symbol':8} {'model':9} {'train bal.acc':>13} {'test bal.acc':>12} {'trades':>7} {'win%':>6} {'net bps/trade':>14} {'p-value':>8}")
for r in table.itertuples():
    print(f"{r.symbol:8} {r.model:9} {r.train_bal:13.1%} {r.test_bal:12.1%} {r.trades:7} {r.win:6.1%} {r.net_bps:14.1f} {r.p:8.3f}")
print("random guessing = 33.3% balanced accuracy. A big train-vs-test gap means the model is memorising.")

xgb, X_te, y_te = btc
gain = pd.Series(xgb.feature_importances_, index=X_te.columns).sort_values(ascending=False)
perm = permutation_drop(xgb, X_te, y_te.to_numpy())

print("\n=== 3. Feature importance (BTCUSDT) ===")
print(f"{'feature':22} {'gain share':>10} {'test drop when shuffled':>25}")
for name in gain.head(8).index:
    print(f"{name:22} {gain[name]:10.3f} {perm[name]:+25.4f}")
print("gain = how much the trees used the feature while TRAINING. 'test drop' = how much test balanced accuracy falls if the")
print("feature is scrambled. A feature with high gain but ~0 drop was used for memorising, not for predicting.")

top = gain.head(10)[::-1]
fig, ax = plt.subplots(figsize=(7.5, 4.5))
ax.barh(top.index, top.values, color="#2a78d6", height=0.6)
ax.set_xlabel("share of total gain (training)", color="#52514e", fontsize=9)
ax.set_title("BTCUSDT XGBoost: top 10 features by gain", loc="left", fontsize=12)
ax.tick_params(colors="#52514e", labelsize=9)
ax.grid(axis="x", color="#e3e2de", linewidth=0.6)
ax.set_axisbelow(True)
for side in ["top", "right", "left"]:
    ax.spines[side].set_visible(False)
fig.set_facecolor("#fcfcfb")
ax.set_facecolor("#fcfcfb")
fig.tight_layout()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
path = OUTPUT_DIR / "day44_importance.png"
fig.savefig(path, dpi=140, facecolor=fig.get_facecolor())
print(f"\nchart saved: {path}")
