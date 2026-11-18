from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from schemas.portfolio import BreakdownOut, OverviewOut, PnlOut, TradesPage
from services import portfolio_service

router = APIRouter(prefix="/portfolio", tags=["Portfolio"])


def _db(fn, *args):
    try:
        return fn(*args)
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.get("/overview", response_model=OverviewOut, summary="One call for the dashboard: equity, open P&L, exposure, drawdown, daily limit, halts")
def overview():
    return _db(portfolio_service.overview)


@router.get("/pnl", response_model=PnlOut, summary="Realized P&L per day, week or month (UTC), gaps filled, with cumulative equity")
def pnl(period: Literal["day", "week", "month"] = "day", limit: int = 90):
    return _db(portfolio_service.pnl, period, min(max(limit, 1), 400))


@router.get("/trades", response_model=TradesPage, summary="Closed-trade journal, newest first: R multiple, hold time, cost in bps")
def trades(limit: int = 50, offset: int = 0, symbol: str | None = None, exit_reason: str | None = None):
    return _db(portfolio_service.trades, limit, offset, symbol, exit_reason)


@router.get("/breakdown", response_model=BreakdownOut, summary="Results grouped by symbol, side, source or exit reason (thin groups flagged)")
def breakdown(by: Literal["symbol", "side", "source", "exit_reason"] = "symbol"):
    return _db(portfolio_service.breakdown, by)
