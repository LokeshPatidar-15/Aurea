import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin

from analysis.labeling import triple_barrier

BASE_FEATURES = [
    "ret_1", "ret_4", "ret_24", "rsi_14", "macd_hist", "bb_pct_b", "bb_width",
    "ema_20_dist", "atr_14_pct", "vol_z", "dist_swing_high_atr", "dist_swing_low_atr",
    "sweep_bull", "sweep_bear", "dist_poc_atr", "in_value_area",
]


class Winsorizer(BaseEstimator, TransformerMixin):
    def __init__(self, lower: float = 0.005, upper: float = 0.995):
        self.lower = lower
        self.upper = upper

    def fit(self, X, y=None):
        values = np.asarray(X, dtype=float)
        self.low_ = np.nanquantile(values, self.lower, axis=0)
        self.high_ = np.nanquantile(values, self.upper, axis=0)
        return self

    def transform(self, X):
        return np.clip(np.asarray(X, dtype=float), self.low_, self.high_)


def make_features(feats: pd.DataFrame) -> pd.DataFrame:
    X = feats[BASE_FEATURES].astype(float).copy()
    hour_angle = 2 * np.pi * feats["hour_utc"].astype(float) / 24
    dow_angle = 2 * np.pi * feats["day_of_week"].astype(float) / 7
    X["hour_sin"] = np.sin(hour_angle)
    X["hour_cos"] = np.cos(hour_angle)
    X["dow_sin"] = np.sin(dow_angle)
    X["dow_cos"] = np.cos(dow_angle)
    X["ret_1_lag1"] = X["ret_1"].shift(1)
    X["ret_1_lag2"] = X["ret_1"].shift(2)
    X["rsi_change_3"] = X["rsi_14"].diff(3)
    X["vol_z_lag1"] = X["vol_z"].shift(1)
    X["sweep_bull_recent"] = X["sweep_bull"].rolling(6, min_periods=1).max()
    X["sweep_bear_recent"] = X["sweep_bear"].rolling(6, min_periods=1).max()
    return X


def build_model_frame_from(feats: pd.DataFrame, cleaned: pd.DataFrame, horizon: int = 12, k: float = 2.0):
    X = make_features(feats)
    labels = triple_barrier(cleaned, feats["atr_14_pct"], horizon, k)
    labels = labels.reindex(X.index)
    keep = X.notna().all(axis=1) & labels["label"].notna()
    return X[keep], labels[keep].astype({"label": int})


def load_inputs(symbol: str, timeframe: str = "1h"):
    from sqlalchemy import select

    from analysis.cleaning import clean_candles
    from analysis.db_loader import load_from_db
    from analysis.features import FEATURE_COLUMNS
    from database import SessionLocal
    from models import Feature

    cleaned, _ = clean_candles(load_from_db(symbol, timeframe), timeframe)
    columns = [getattr(Feature, name) for name in FEATURE_COLUMNS]
    stmt = (
        select(Feature.open_time, *columns)
        .where(Feature.symbol == symbol, Feature.timeframe == timeframe)
        .order_by(Feature.open_time)
    )
    with SessionLocal() as session:
        rows = session.execute(stmt).all()
    feats = pd.DataFrame(rows, columns=["open_time", *FEATURE_COLUMNS])
    feats["open_time"] = pd.to_datetime(feats["open_time"], utc=True)
    feats = feats.set_index("open_time")
    return feats, cleaned


def load_model_frame(symbol: str, timeframe: str = "1h", horizon: int = 12, k: float = 2.0):
    feats, cleaned = load_inputs(symbol, timeframe)
    return build_model_frame_from(feats, cleaned, horizon, k)


def purged_split(X: pd.DataFrame, labels: pd.DataFrame, test_frac: float = 0.3):
    cut = int(len(X) * (1 - test_frac))
    test_start = X.index[cut]
    in_train = (np.arange(len(X)) < cut) & (labels["exit_time"] < test_start).to_numpy()
    in_test = np.arange(len(X)) >= cut
    return X[in_train], X[in_test], labels[in_train], labels[in_test]
