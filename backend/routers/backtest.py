from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from analysis.rules import RuleError
from schemas.backtest import BacktestOut, TrialsOut
from schemas.builder import StrategyIn
from services import backtest_service
from services.prediction_service import NotEnoughDataError, UnsupportedSymbolError

router = APIRouter(prefix="/strategy", tags=["Strategy backtest"])


@router.post("/backtest/{symbol}", response_model=BacktestOut, summary="Backtest a rule strategy with honest evidence (random-entry test, time slices, multiple-testing guard)")
def backtest(symbol: str, body: StrategyIn, timeframe: str = "1h"):
    try:
        return backtest_service.backtest(symbol, body.strategy, timeframe)
    except RuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UnsupportedSymbolError as exc:
        raise HTTPException(status_code=404 if "symbol" in str(exc) else 422, detail=str(exc))
    except NotEnoughDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except backtest_service.BusyError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": "10"})
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.get("/trials", response_model=TrialsOut, summary="How many strategies have been tested so far (the multiple-testing count)")
def trials():
    return backtest_service.trials()
