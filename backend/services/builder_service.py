from datetime import datetime, timezone

import pandas as pd

from analysis.cleaning import clean_candles
from analysis.features import compute_features
from analysis.rule_builder import build_strategy, validate_payload
from analysis.rules import describe, generate_rule_signals
from analysis.strategy import StrategyParams
from analysis.templates import TEMPLATES, get_template

PARAMS = StrategyParams()
LOOKBACK = 600
INTERVAL_MINUTES = {"1h": 60}
SIDE_NAMES = {1: "long", -1: "short", 0: "none"}


def list_templates() -> list:
    out = []
    for tid, t in TEMPLATES.items():
        result = validate_payload(t["strategy"])
        out.append({"id": tid, "title": t["title"], "idea": t["idea"], "evidence": t["evidence"], "long_text": result["long_text"],
                    "short_text": result["short_text"], "strategy": result["strategy"]})
    return out


def template_detail(template_id: str) -> dict:
    t = get_template(template_id)
    result = validate_payload(t["strategy"])
    return {"id": template_id, "title": t["title"], "idea": t["idea"], "evidence": t["evidence"], "long_text": result["long_text"],
            "short_text": result["short_text"], "strategy": result["strategy"]}


def preview_from_candles(candles: pd.DataFrame, payload, symbol: str, timeframe: str = "1h", now: datetime | None = None) -> dict:
    strategy = build_strategy(payload)
    cleaned, _ = clean_candles(candles.tail(LOOKBACK), timeframe)
    feats = compute_features(cleaned)
    signals = generate_rule_signals(cleaned, feats, strategy)
    last_time = cleaned.index[-1]
    row = signals.iloc[-1]
    reference = float(cleaned["close"].iloc[-1])
    side = int(row["side"])
    atr = float(row["atr"]) if pd.notna(row["atr"]) else None
    stop = float(row["stop"]) if side != 0 and pd.notna(row["stop"]) else None
    now = now or datetime.now(timezone.utc)
    closes_at = last_time + pd.Timedelta(minutes=INTERVAL_MINUTES[timeframe])
    age = max((pd.Timestamp(now) - closes_at).total_seconds() / 60, 0.0)
    stale = bool(age > 2 * INTERVAL_MINUTES[timeframe])
    risk_atr = None
    status, reason = "none", "no_setup"
    if side != 0 and stop is not None and atr:
        risk_atr = side * (reference - stop) / atr
        if not (PARAMS.min_risk_atr <= risk_atr <= PARAMS.max_risk_atr):
            reason = "risk_outside_band"
        elif stale:
            reason = "stale_data"
        else:
            status, reason = "signal", "setup_confirmed"
    return {
        "symbol": symbol, "timeframe": timeframe, "strategy_name": strategy.name,
        "long_text": describe(strategy.long) if strategy.long else None, "short_text": describe(strategy.short) if strategy.short else None,
        "status": status, "reason": reason, "side": SIDE_NAMES[side] if status == "signal" else "none",
        "as_of": last_time.to_pydatetime(), "reference_price": reference, "stop_price": stop if status == "signal" else None,
        "risk_atr": risk_atr, "data_age_minutes": round(age, 1), "stale": stale,
        "signals_in_window": int((signals["side"] != 0).sum()), "window_candles": int(len(cleaned)),
        "research_only": True,
        "note": "Preview only: nothing is traded and nothing is saved. A rule you can write is not a rule with an edge; Day 62 adds the backtest evidence.",
    }


def preview(symbol: str, payload, timeframe: str = "1h") -> dict:
    from services.prediction_service import SUPPORTED_SYMBOLS, UnsupportedSymbolError, load_recent_candles

    symbol = symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise UnsupportedSymbolError(f"unsupported symbol {symbol!r}. Supported: {', '.join(SUPPORTED_SYMBOLS)}")
    if timeframe not in INTERVAL_MINUTES:
        raise UnsupportedSymbolError(f"unsupported timeframe {timeframe!r}")
    return preview_from_candles(load_recent_candles(symbol, timeframe, LOOKBACK), payload, symbol, timeframe)
