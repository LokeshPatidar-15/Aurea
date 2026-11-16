from datetime import datetime, timezone

import pandas as pd


def price(symbol: str) -> dict:
    from services.prediction_service import INTERVAL_MINUTES, SUPPORTED_SYMBOLS, UnsupportedSymbolError, load_recent_candles

    if symbol not in SUPPORTED_SYMBOLS:
        raise UnsupportedSymbolError(f"unsupported symbol {symbol!r}")
    candles = load_recent_candles(symbol, "1h", 3)
    last = candles.index[-1]
    closes_at = last + pd.Timedelta(minutes=INTERVAL_MINUTES["1h"])
    age = max((pd.Timestamp(datetime.now(timezone.utc)) - closes_at).total_seconds() / 60, 0.0)
    return {"symbol": symbol, "close": float(candles["close"].iloc[-1]), "as_of": last.to_pydatetime(), "data_age_minutes": round(age, 1), "stale": bool(age > 2 * INTERVAL_MINUTES["1h"])}


def build_backend() -> dict:
    from services import backtest_service, paper_report_service, paper_service, pattern_service, prediction_service, strategy_service

    return {
        "price": price,
        "signal": strategy_service.latest_signal,
        "prediction": lambda symbol: prediction_service.predict(symbol, "1h", "xgboost"),
        "patterns": pattern_service.latest_patterns,
        "summary": paper_service.summary,
        "performance": paper_report_service.performance,
        "tradability": paper_service.tradability_report,
        "trials": backtest_service.trials,
    }
