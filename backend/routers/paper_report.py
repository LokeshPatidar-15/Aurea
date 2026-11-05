from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from schemas.paper_report import EquityPoint, PerformanceOut
from services import paper_report_service

router = APIRouter(prefix="/paper", tags=["Paper trading"])


@router.get("/performance", response_model=PerformanceOut, summary="Win rate, expectancy in R with a 90% interval, drawdown, fees, breakdowns")
def performance():
    try:
        return paper_report_service.performance()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.get("/equity-curve", response_model=list[EquityPoint], summary="Realized equity after every closed trade, with drawdown")
def equity_curve(limit: int = 1000):
    try:
        return paper_report_service.equity_curve(min(max(limit, 1), 5000))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")
