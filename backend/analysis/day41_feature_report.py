import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from analysis.ml_features import BASE_FEATURES, Winsorizer, build_model_frame_from, load_inputs, make_features, purged_split

HORIZON, K = 12, 2.0
feats, cleaned = load_inputs("BTCUSDT", "1h")
X, labels = build_model_frame_from(feats, cleaned, HORIZON, K)
X_tr, X_te, lab_tr, lab_te = purged_split(X, labels, test_frac=0.3)

print("=== 1. Model-ready table ===")
print(f"{X.shape[1]} features (started with {len(BASE_FEATURES)} stored ones) | rows: {len(X)} | NaN cells: {int(X.isna().sum().sum())}")
print(f"train rows: {len(X_tr)} (labels finished before the test period starts) | test rows: {len(X_te)}")
new_cols = [c for c in X.columns if c not in BASE_FEATURES]
print("new columns:", ", ".join(new_cols))

print("\n=== 2. Strongly correlated feature pairs (|corr| > 0.9, train only) ===")
corr = X_tr.corr().abs()
pairs = [(a, b, corr.loc[a, b]) for i, a in enumerate(corr.columns) for b in corr.columns[i + 1:] if corr.loc[a, b] > 0.9]
if pairs:
    for a, b, c in sorted(pairs, key=lambda t: -t[2]):
        print(f"{a:22} {b:22} {c:.3f}")
else:
    print("none")

print("\n=== 3. Information coefficient: Spearman(feature, realized trade return) on train ===")
ic = {col: spearmanr(X_tr[col], lab_tr["ret"])[0] for col in X_tr.columns}
ic = pd.Series(ic).sort_values(key=abs, ascending=False)
noise = 2 / np.sqrt(len(X_tr))
print(f"rough noise band (2 / sqrt(n)): +-{noise:.3f}")
for name, value in ic.head(8).items():
    flag = "above noise" if abs(value) > noise else "inside noise"
    print(f"{name:22} {value:+.3f}  {flag}")
print(f"features above the noise band: {(ic.abs() > noise).sum()} of {len(ic)}")

print("\n=== 4. Winsorizing: clip extreme values using TRAIN quantiles only ===")
win = Winsorizer().fit(X_tr)
for col in ("vol_z", "ret_1", "dist_poc_atr"):
    j = list(X_tr.columns).index(col)
    before = X_te[col].abs().max()
    after = np.abs(win.transform(X_te)[:, j]).max()
    print(f"{col:14} largest |value| in TEST: raw {before:8.3f} -> clipped {after:8.3f}")

print("\n=== 5. No-lookahead test for the new features ===")
full = make_features(feats)
for cut in (1500, 4000, 7000):
    part = make_features(feats.iloc[:cut])
    pd.testing.assert_frame_equal(full.iloc[:cut], part, check_exact=False, rtol=1e-9, atol=1e-9)
    print(f"cut at {cut}: first {cut} rows identical with and without the future")
