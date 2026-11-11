from datetime import datetime, timezone

import pandas as pd

from analysis.cleaning import clean_candles
from analysis.features import compute_features
from analysis.patterns import PATTERN_NAMES, detect_all
from analysis.rules import CONDITIONS, Cond, Context, evaluate

LOOKBACK = 600
INTERVAL_MINUTES = {"1h": 60}
RECENT = 24


def conditions_catalog() -> list:
    return [{"name": name, "description": description} for name, (description, _) in CONDITIONS.items()]


def patterns_from_candles(candles: pd.DataFrame, symbol: str, timeframe: str = "1h", now: datetime | None = None) -> dict:
    window = candles.tail(LOOKBACK)
    cleaned, _ = clean_candles(window, timeframe)
    feats = compute_features(cleaned)
    ctx = Context(cleaned, feats)
    flags = detect_all(cleaned)
    last_time = cleaned.index[-1]
    now = now or datetime.now(timezone.utc)
    closes_at = last_time + pd.Timedelta(minutes=INTERVAL_MINUTES[timeframe])
    age = max((pd.Timestamp(now) - closes_at).total_seconds() / 60, 0.0)
    recent = []
    tail = flags.iloc[-RECENT:]
    for ts, row in tail.iterrows():
        hit = [name for name in PATTERN_NAMES if bool(row[name])]
        if hit:
            recent.append({"time": ts.to_pydatetime(), "patterns": hit})
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "as_of": last_time.to_pydatetime(),
        "data_age_minutes": round(age, 1),
        "stale": bool(age > 2 * INTERVAL_MINUTES[timeframe]),
        "latest": {name: bool(flags[name].iloc[-1]) for name in PATTERN_NAMES},
        "sweep": {"sweep_bull": bool(evaluate(Cond("sweep_bull"), ctx).iloc[-1]), "sweep_bear": bool(evaluate(Cond("sweep_bear"), ctx).iloc[-1])},
        "recent": recent,
        "recent_candles": RECENT,
        "research_only": True,
        "note": "Candlestick patterns are descriptions of the last candles. Day 60 tests found no tradable edge in them after costs.",
    }


def latest_patterns(symbol: str, timeframe: str = "1h") -> dict:
    from services.prediction_service import SUPPORTED_SYMBOLS, UnsupportedSymbolError, load_recent_candles

    symbol = symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise UnsupportedSymbolError(f"unsupported symbol {symbol!r}. Supported: {', '.join(SUPPORTED_SYMBOLS)}")
    if timeframe not in INTERVAL_MINUTES:
        raise UnsupportedSymbolError(f"unsupported timeframe {timeframe!r}")
    return patterns_from_candles(load_recent_candles(symbol, timeframe, LOOKBACK), symbol, timeframe)
