import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from sklearn.metrics import classification_report

from analysis.baseline_models import make_logistic
from analysis.common import OUTPUT_DIR
from analysis.evaluation import CLASS_NAMES, CLASS_ORDER, COST_BPS, evaluate
from analysis.ml_features import load_model_frame, purged_split

HORIZON, K = 12, 2.0
results = {}
for symbol in ("BTCUSDT", "XAUUSD", "EURUSD"):
    X, labels = load_model_frame(symbol, "1h", HORIZON, K)
    X_tr, X_te, lab_tr, lab_te = purged_split(X, labels, test_frac=0.3)
    model = make_logistic().fit(X_tr, lab_tr["label"])
    pred = model.predict(X_te)
    results[symbol] = (lab_te, pred, evaluate(lab_te["label"], pred, lab_te["ret"]))

lab_te, pred, ev = results["BTCUSDT"]
print("=== 1. BTCUSDT confusion matrix (rows = what really happened, columns = what the model said) ===")
names = [CLASS_NAMES[c] for c in CLASS_ORDER]
print(pd.DataFrame(ev["confusion"], index=[f"true {n}" for n in names], columns=[f"pred {n}" for n in names]).to_string())

print("\n=== 2. Precision and recall per class ===")
print(classification_report(lab_te["label"], pred, labels=CLASS_ORDER, target_names=names, digits=3, zero_division=0))
print(f"accuracy {ev['accuracy']:.1%} | baseline {ev['baseline']:.1%} | balanced accuracy {ev['balanced_accuracy']:.1%} (random guessing = 33.3%)")

print("\n=== 3. The money question: expectancy per signal (not accuracy) ===")
print(f"a buy or sell signal is treated as a trade held until its barrier or timeout; cost {COST_BPS:.0f} bps per round trip")
print("p-value: the signals are slid to 500 random wrong positions in time (keeping their streaks); p = share of slides that did at least as well (small = skill, large = luck)\n")
header = f"{'symbol':8} {'acc':>6} {'base':>6} {'bal.acc':>8} {'trades':>7} {'win%':>6} {'net bps/trade':>14} {'p-value':>8}"
print(header)
for symbol, (_, _, e) in results.items():
    print(f"{symbol:8} {e['accuracy']:6.1%} {e['baseline']:6.1%} {e['balanced_accuracy']:8.1%} {e['trades']:7} {e['win_rate']:6.1%} {e['net_bps_per_trade']:14.1f} {e['p_value']:8.3f}")

print("\n=== 4. Why accuracy alone misleads ===")
always_hold = np.zeros(len(lab_te), dtype=int)
hold_eval = evaluate(lab_te["label"], always_hold, lab_te["ret"])
print(f"a model that always says 'hold' gets {hold_eval['accuracy']:.1%} accuracy, makes {hold_eval['trades']} trades, and can never lose money")
print("it also never finds a single opportunity. Judge a trading model by trade quality after costs, not by accuracy.")

counts = ev["confusion"].astype(float)
shares = counts / counts.sum(axis=1, keepdims=True)
cmap = LinearSegmentedColormap.from_list("blue", ["#fcfcfb", "#2a78d6"])
fig, ax = plt.subplots(figsize=(5.5, 4.5))
ax.imshow(shares, cmap=cmap, vmin=0, vmax=1)
for i in range(3):
    for j in range(3):
        colour = "#ffffff" if shares[i, j] > 0.55 else "#0b0b0b"
        ax.text(j, i, f"{shares[i, j]:.0%}\n({int(counts[i, j])})", ha="center", va="center", color=colour, fontsize=10)
ax.set_xticks(range(3), names)
ax.set_yticks(range(3), names)
ax.set_xlabel("model said", color="#52514e", fontsize=9)
ax.set_ylabel("what happened", color="#52514e", fontsize=9)
ax.set_title("BTCUSDT: share of each true class by prediction", loc="left", fontsize=11)
for side in ax.spines.values():
    side.set_visible(False)
fig.set_facecolor("#fcfcfb")
fig.tight_layout()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
path = OUTPUT_DIR / "day43_confusion.png"
fig.savefig(path, dpi=140, facecolor=fig.get_facecolor())
print(f"\nchart saved: {path}")
