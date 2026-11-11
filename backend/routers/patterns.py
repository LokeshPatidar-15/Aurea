from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from schemas.patterns import ConditionOut, PatternsOut
from services import pattern_service
from services.prediction_service import NotEnoughDataError, UnsupportedSymbolError

router = APIRouter(prefix="/strategy", tags=["Strategy"])


@router.get("/patterns/{symbol}", response_model=PatternsOut, summary="Candlestick patterns on the latest closed 1h candles")
def patterns(symbol: str, timeframe: str = "1h"):
    try:
        return pattern_service.latest_patterns(symbol, timeframe)
    except UnsupportedSymbolError as exc:
        raise HTTPException(status_code=404 if "symbol" in str(exc) else 422, detail=str(exc))
    except NotEnoughDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.get("/conditions", response_model=list[ConditionOut], summary="Named conditions a rule can use")
def conditions():
    return pattern_service.conditions_catalog()
