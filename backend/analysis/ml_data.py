import numpy as np
import pandas as pd

FEATURE_NAMES = [
    "ret_1", "ret_4", "ret_24", "rsi_14", "macd_hist", "bb_pct_b", "bb_width",
    "ema_20_dist", "atr_14_pct", "vol_z", "hour_utc", "day_of_week",
    "dist_swing_high_atr", "dist_swing_low_atr", "sweep_bull", "sweep_bear",
    "dist_poc_atr", "in_value_area",
]


def build_dataset(feats: pd.DataFrame, close: pd.Series, horizon: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    X = feats[FEATURE_NAMES].astype(float)
    forward_return = close.shift(-horizon) / close - 1
    y = (forward_return > 0).astype(int)
    valid = X.notna().all(axis=1) & forward_return.reindex(X.index).notna()
    X = X[valid]
    y = y.reindex(X.index)
    return X, y


def chronological_split(X: pd.DataFrame, y: pd.Series, test_frac: float = 0.3, embargo: int = 4):
    cut = int(len(X) * (1 - test_frac))
    train_end = cut - embargo
    return X.iloc[:train_end], X.iloc[cut:], y.iloc[:train_end], y.iloc[cut:]


def load_dataset_from_db(symbol: str, timeframe: str, horizon: int = 4) -> tuple[pd.DataFrame, pd.Series]:
    from sqlalchemy import select

    from analysis.cleaning import clean_candles
    from analysis.db_loader import load_from_db
    from database import SessionLocal
    from models import Feature

    cleaned, _ = clean_candles(load_from_db(symbol, timeframe), timeframe)
    columns = [getattr(Feature, name) for name in FEATURE_NAMES]
    stmt = (
        select(Feature.open_time, *columns)
        .where(Feature.symbol == symbol, Feature.timeframe == timeframe)
        .order_by(Feature.open_time)
    )
    with SessionLocal() as session:
        rows = session.execute(stmt).all()
    feats = pd.DataFrame(rows, columns=["open_time", *FEATURE_NAMES])
    feats["open_time"] = pd.to_datetime(feats["open_time"], utc=True)
    feats = feats.set_index("open_time")
    return build_dataset(feats, cleaned["close"], horizon)
