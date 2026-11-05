from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from schemas.strategy import SignalOut
from services import strategy_service
from services.prediction_service import NotEnoughDataError, UnsupportedSymbolError

router = APIRouter(prefix="/strategy", tags=["Strategy"])


@router.get("/signal/{symbol}", response_model=SignalOut, summary="Rule-based sweep-reversal signal on the latest closed 1h candle")
def signal(symbol: str, timeframe: str = "1h"):
    try:
        return strategy_service.latest_signal(symbol, timeframe)
    except UnsupportedSymbolError as exc:
        raise HTTPException(status_code=404 if "symbol" in str(exc) else 422, detail=str(exc))
    except NotEnoughDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")
