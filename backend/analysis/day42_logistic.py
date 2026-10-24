import numpy as np
import pandas as pd

from analysis.baseline_models import make_logistic
from analysis.evaluation import CLASS_NAMES
from analysis.ml_features import load_model_frame, purged_split

HORIZON, K = 12, 2.0
X, labels = load_model_frame("BTCUSDT", "1h", HORIZON, K)
X_tr, X_te, lab_tr, lab_te = purged_split(X, labels, test_frac=0.3)
y_tr, y_te = lab_tr["label"], lab_te["label"]

print("=== 1. Data ===")
print(f"train {len(X_tr)} | test {len(X_te)} | features {X.shape[1]}")
mix = y_tr.value_counts(normalize=True).reindex([-1, 0, 1]).fillna(0)
print(f"train label mix: sell {mix[-1]:.1%} | hold {mix[0]:.1%} | buy {mix[1]:.1%}")

print("\n=== 2. Fit: winsorize -> standardize -> multinomial logistic regression ===")
model = make_logistic().fit(X_tr, y_tr)
print("classes the model learned:", [CLASS_NAMES[c] for c in model.classes_])
print("class_weight='balanced': rare classes count more, so the model cannot win by always saying the majority class")

print("\n=== 3. Accuracy against the lazy baseline ===")
pred = model.predict(X_te)
accuracy = (pred == y_te.to_numpy()).mean()
test_mix = y_te.value_counts(normalize=True)
baseline = test_mix.max()
print(f"test accuracy {accuracy:.1%} | always-{CLASS_NAMES[test_mix.idxmax()]} baseline {baseline:.1%} | train accuracy {model.score(X_tr, y_tr):.1%}")
print("predicted mix on test:", {CLASS_NAMES[c]: f"{(pred == c).mean():.1%}" for c in [-1, 0, 1]})

print("\n=== 4. What does one prediction look like? ===")
proba = model.predict_proba(X_te)
sample = pd.DataFrame(proba[:5], columns=[CLASS_NAMES[c] for c in model.classes_], index=X_te.index[:5]).round(3)
sample["pick"] = [CLASS_NAMES[c] for c in pred[:5]]
sample["actual"] = [CLASS_NAMES[c] for c in y_te.iloc[:5]]
print(sample.to_string())

print("\n=== 5. Confidence filter: act only when the model is sure ===")
confidence = proba.max(axis=1)
for threshold in (0.0, 0.40, 0.45, 0.50):
    keep = confidence >= threshold
    if keep.sum() == 0:
        print(f"confidence >= {threshold:.2f}: no predictions left")
        continue
    acc = (pred[keep] == y_te.to_numpy()[keep]).mean()
    print(f"confidence >= {threshold:.2f}: {keep.mean():6.1%} of candles kept | accuracy on those {acc:.1%}")

print("\n=== 6. Strongest standardized coefficients ===")
coefs = pd.DataFrame(model[-1].coef_, index=[CLASS_NAMES[c] for c in model.classes_], columns=X.columns)
for cls in ("buy", "sell"):
    top = coefs.loc[cls].reindex(coefs.loc[cls].abs().sort_values(ascending=False).index).head(4)
    print(cls + ":", ", ".join(f"{name} {value:+.2f}" for name, value in top.items()))
