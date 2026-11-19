from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from schemas.signals import AccountabilityOut, SignalHistoryOut
from services import signal_service
from services.prediction_service import SUPPORTED_SYMBOLS

router = APIRouter(prefix="/signals", tags=["Signals"])


def _symbol(symbol: str | None) -> str | None:
    if symbol is None:
        return None
    symbol = symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise HTTPException(status_code=422, detail="unsupported symbol. Supported: " + ", ".join(SUPPORTED_SYMBOLS))
    return symbol


def _db(fn, *args):
    try:
        return fn(*args)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.get("/history", response_model=SignalHistoryOut, summary="Every signal recorded at candle close, newest first, with what happened after 1, 4 and 24 hours")
def signal_history(limit: int = 50, offset: int = 0, symbol: str | None = None, kind: Literal["rule", "model"] | None = None):
    return _db(signal_service.history, limit, offset, _symbol(symbol), kind)


@router.get("/accountability", response_model=AccountabilityOut, summary="Were the signals any good after costs? Accuracy, net bps, honest intervals and a verdict that never says profitable")
def signal_accountability(symbol: str | None = None, kind: Literal["rule", "model"] | None = None):
    return _db(signal_service.accountability, _symbol(symbol), kind)
