import numpy as np
import pandas as pd
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

DEFAULT_PARAMS = {
    "n_estimators": 500,
    "learning_rate": 0.03,
    "max_depth": 3,
    "min_child_weight": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 5.0,
}


def _build(params: dict, early_stopping_rounds: int | None) -> XGBClassifier:
    options = dict(
        objective="multi:softprob",
        eval_metric="mlogloss",
        random_state=0,
        n_jobs=-1,
        **params,
    )
    if early_stopping_rounds:
        options["early_stopping_rounds"] = early_stopping_rounds
    return XGBClassifier(**options)


def fit_xgb(X_tr: pd.DataFrame, y_tr: pd.Series, horizon: int = 12, params: dict | None = None) -> XGBClassifier:
    params = {**DEFAULT_PARAMS, **(params or {})}
    cut = int(len(X_tr) * 0.85)
    X_fit, y_fit = X_tr.iloc[: cut - horizon], y_tr.iloc[: cut - horizon] + 1
    X_val, y_val = X_tr.iloc[cut:], y_tr.iloc[cut:] + 1
    model = _build(params, early_stopping_rounds=30)
    model.fit(X_fit, y_fit, sample_weight=compute_sample_weight("balanced", y_fit), eval_set=[(X_val, y_val)], verbose=False)
    return model


def fit_xgb_final(X: pd.DataFrame, y: pd.Series, horizon: int = 12, params: dict | None = None) -> XGBClassifier:
    params = {**DEFAULT_PARAMS, **(params or {})}
    probe = fit_xgb(X, y, horizon, params)
    trees = int(probe.best_iteration) + 1
    final_params = {**params, "n_estimators": trees}
    model = _build(final_params, early_stopping_rounds=None)
    y_all = y + 1
    model.fit(X, y_all, sample_weight=compute_sample_weight("balanced", y_all), verbose=False)
    return model


def predict_xgb(model: XGBClassifier, X: pd.DataFrame) -> np.ndarray:
    return model.predict(X).astype(int) - 1
