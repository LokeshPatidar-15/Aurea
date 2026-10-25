import warnings
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
import pandas as pd

from analysis.cleaning import TIMEFRAME_FREQ, clean_candles
from analysis.features import compute_features
from analysis.ml_features import make_features
from services.model_store import SCHEMA_VERSION, library_versions, read_artifact

SUPPORTED_SYMBOLS = ("BTCUSDT", "XAUUSD", "EURUSD")
INTERVAL_MINUTES = {"15m": 15, "1h": 60}
CLASS_NAMES = {-1: "sell", 0: "hold", 1: "buy"}
LOOKBACK_CANDLES = 600


class PredictionError(Exception):
    pass


class UnsupportedSymbolError(PredictionError):
    pass


class ModelNotFoundError(PredictionError):
    pass


class NotEnoughDataError(PredictionError):
    pass


def validate_request(symbol: str, timeframe: str) -> None:
    if symbol not in SUPPORTED_SYMBOLS:
        raise UnsupportedSymbolError(f"unsupported symbol {symbol!r}. Supported: {', '.join(SUPPORTED_SYMBOLS)}")
    if timeframe not in INTERVAL_MINUTES:
        raise UnsupportedSymbolError(f"unsupported timeframe {timeframe!r}")


@lru_cache(maxsize=8)
def load_artifact(symbol: str, timeframe: str) -> dict:
    validate_request(symbol, timeframe)
    try:
        artifact = read_artifact(symbol, timeframe)
    except FileNotFoundError as exc:
        raise ModelNotFoundError(
            f"no trained model for {symbol} {timeframe}. Run: python3 -m scripts.train_model --symbols {symbol}"
        ) from exc
    if artifact.get("schema_version") != SCHEMA_VERSION:
        raise ModelNotFoundError(f"model file for {symbol} {timeframe} has an old format. Retrain it.")
    saved, now = artifact.get("versions", {}), library_versions()
    for lib in ("scikit-learn", "xgboost", "pandas"):
        if saved.get(lib) != now.get(lib):
            warnings.warn(f"{lib} version differs: model saved with {saved.get(lib)}, running {now.get(lib)}")
    return artifact


def proba_for(artifact: dict, X: pd.DataFrame) -> np.ndarray:
    return artifact["model"].predict_proba(X[artifact["feature_names"]])


def load_recent_candles(symbol: str, timeframe: str, n: int = LOOKBACK_CANDLES) -> pd.DataFrame:
    from sqlalchemy import select

    from database import SessionLocal
    from models import PriceHistory

    columns = ["open_time", "open", "high", "low", "close", "volume"]
    stmt = (
        select(*[getattr(PriceHistory, c) for c in columns])
        .where(PriceHistory.symbol == symbol, PriceHistory.timeframe == timeframe)
        .order_by(PriceHistory.open_time.desc())
        .limit(n)
    )
    with SessionLocal() as session:
        rows = session.execute(stmt).all()
    if not rows:
        raise NotEnoughDataError(f"no candles stored for {symbol} {timeframe}. Run: python3 -m scripts.ingest_history")
    df = pd.DataFrame(rows[::-1], columns=columns)
    df["open_time"] = pd.to_datetime(df["open_time"], utc=True)
    return df.set_index("open_time").astype(float)


def predict_from_candles(artifact: dict, candles: pd.DataFrame, now: datetime | None = None) -> dict:
    symbol, timeframe = artifact["symbol"], artifact["timeframe"]
    window = candles.tail(LOOKBACK_CANDLES)
    cleaned, _ = clean_candles(window, timeframe)
    feats = compute_features(cleaned)
    X = make_features(feats)
    last_time = cleaned.index[-1]
    row = X.loc[[last_time]]
    if row.isna().any(axis=None):
        raise NotEnoughDataError(f"not enough clean history to build features for {symbol} {timeframe} (need about {LOOKBACK_CANDLES} candles)")

    proba = proba_for(artifact, row)[0]
    order = artifact["class_order"]
    probabilities = {CLASS_NAMES[c]: round(float(p), 4) for c, p in zip(order, proba)}
    best = int(np.argmax(proba))

    now = now or datetime.now(timezone.utc)
    interval = pd.Timedelta(minutes=INTERVAL_MINUTES[timeframe])
    candle_closed_at = last_time + interval
    age_minutes = max((pd.Timestamp(now) - candle_closed_at).total_seconds() / 60, 0.0)
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "signal": CLASS_NAMES[order[best]],
        "confidence": round(float(proba[best]), 4),
        "probabilities": probabilities,
        "as_of": last_time.to_pydatetime(),
        "data_age_minutes": round(age_minutes, 1),
        "stale": bool(age_minutes > 2 * INTERVAL_MINUTES[timeframe]),
        "model": {
            "type": artifact["model_type"],
            "trained_through": artifact["trained_through"],
            "trained_rows": artifact["trained_rows"],
            "created_at": artifact["created_at"],
            "walk_forward": artifact["walk_forward"],
        },
    }


def predict(symbol: str, timeframe: str = "1h") -> dict:
    artifact = load_artifact(symbol, timeframe)
    candles = load_recent_candles(symbol, timeframe)
    return predict_from_candles(artifact, candles)
