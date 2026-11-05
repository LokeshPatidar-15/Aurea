from datetime import datetime, timezone

import pandas as pd

from analysis.cleaning import clean_candles
from analysis.features import compute_features
from analysis.indicators import ema
from analysis.strategy import StrategyParams, generate_signals

STRATEGY_NAME = "sweep_reversal_v1"
PARAMS = StrategyParams()
INTERVAL_MINUTES = {"1h": 60}
LOOKBACK = 600
SIDE_NAMES = {1: "long", -1: "short", 0: "none"}


def compute_signal(candles: pd.DataFrame, symbol: str, timeframe: str = "1h", params: StrategyParams = PARAMS, now: datetime | None = None) -> dict:
    window = candles.tail(LOOKBACK)
    cleaned, _ = clean_candles(window, timeframe)
    feats = compute_features(cleaned)
    signals = generate_signals(cleaned, feats, params)
    last_time = cleaned.index[-1]
    row, frow = signals.iloc[-1], feats.iloc[-1]
    reference = float(cleaned["close"].iloc[-1])
    side = int(row["side"])
    atr = float(row["atr"]) if pd.notna(row["atr"]) else None
    stop = float(row["stop"]) if side != 0 and pd.notna(row["stop"]) else None

    now = now or datetime.now(timezone.utc)
    closes_at = last_time + pd.Timedelta(minutes=INTERVAL_MINUTES[timeframe])
    age_minutes = max((pd.Timestamp(now) - closes_at).total_seconds() / 60, 0.0)
    stale = bool(age_minutes > 2 * INTERVAL_MINUTES[timeframe])

    risk_atr = None
    status, reason = "none", "no_setup"
    if side != 0 and stop is not None and atr:
        risk_atr = side * (reference - stop) / atr
        if not (params.min_risk_atr <= risk_atr <= params.max_risk_atr):
            reason = "risk_outside_band"
        elif stale:
            reason = "stale_data"
        else:
            status, reason = "signal", "setup_confirmed"
    fast, slow = ema(cleaned["close"], 50).iloc[-1], ema(cleaned["close"], 200).iloc[-1]
    trend = "up" if fast > slow else "down" if fast < slow else "flat"
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "strategy": STRATEGY_NAME,
        "status": status,
        "reason": reason,
        "side": SIDE_NAMES[side] if status == "signal" else "none",
        "as_of": last_time.to_pydatetime(),
        "reference_price": reference,
        "stop_price": stop if status == "signal" else None,
        "rr": params.rr,
        "risk_atr": risk_atr,
        "atr": atr,
        "data_age_minutes": round(age_minutes, 1),
        "stale": stale,
        "conditions": {
            "sweep_bull": bool(frow["sweep_bull"]),
            "sweep_bear": bool(frow["sweep_bear"]),
            "volume_ok": bool(pd.notna(frow["vol_z"]) and frow["vol_z"] >= params.vol_min),
            "trend": trend,
        },
        "research_only": True,
        "note": "Day 54 backtests showed no net edge after costs. Signals are paper-trading material, not advice.",
    }


def latest_signal(symbol: str, timeframe: str = "1h") -> dict:
    from services.prediction_service import SUPPORTED_SYMBOLS, UnsupportedSymbolError, load_recent_candles

    symbol = symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise UnsupportedSymbolError(f"unsupported symbol {symbol!r}. Supported: {', '.join(SUPPORTED_SYMBOLS)}")
    if timeframe not in INTERVAL_MINUTES:
        raise UnsupportedSymbolError(f"unsupported timeframe {timeframe!r}")
    return compute_signal(load_recent_candles(symbol, timeframe, LOOKBACK), symbol, timeframe)
