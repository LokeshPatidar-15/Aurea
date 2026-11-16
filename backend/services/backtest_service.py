import threading

from analysis.evidence import run_evidence
from analysis.rule_builder import build_strategy
from analysis.trial_log import TrialLog

TIMEFRAMES = ("1h",)
MIN_CANDLES = 1000
_gate = threading.Semaphore(1)


class BusyError(RuntimeError):
    pass


def backtest(symbol: str, payload, timeframe: str = "1h", log: TrialLog | None = None) -> dict:
    from analysis.ml_features import load_inputs
    from services.prediction_service import SUPPORTED_SYMBOLS, NotEnoughDataError, UnsupportedSymbolError

    symbol = symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise UnsupportedSymbolError(f"unsupported symbol {symbol!r}. Supported: {', '.join(SUPPORTED_SYMBOLS)}")
    if timeframe not in TIMEFRAMES:
        raise UnsupportedSymbolError(f"unsupported timeframe {timeframe!r}")
    strategy = build_strategy(payload)
    if not _gate.acquire(blocking=False):
        raise BusyError("another backtest is running. Try again in a few seconds")
    try:
        feats, cleaned = load_inputs(symbol, timeframe)
        if len(feats) < MIN_CANDLES:
            raise NotEnoughDataError(f"only {len(feats)} feature rows stored for {symbol}. Run: python3 -m scripts.ingest_history and scripts.build_features")
        return run_evidence(cleaned, feats, strategy, symbol, timeframe, log or TrialLog())
    finally:
        _gate.release()


def trials(limit: int = 20, log: TrialLog | None = None) -> dict:
    entries = (log or TrialLog()).entries()
    recent = [{"time": e.get("time"), "symbol": e["symbol"], "name": e.get("name", ""), "key": e["key"], "long": e.get("long"), "short": e.get("short")} for e in entries[-limit:]]
    return {"strategies_tried": len(entries), "bonferroni_threshold": 0.05 / max(len(entries), 1), "recent": recent[::-1]}
