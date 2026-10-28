from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from schemas.paper import OrderIn, PositionOut, SummaryOut, TickResult, TradabilityRow
from services import paper_service
from services.paper_service import OrderNotCancellable, OrderNotFound, OrderRejected
from services.prediction_service import NotEnoughDataError, UnsupportedSymbolError

router = APIRouter(prefix="/paper", tags=["Paper trading"])


@router.get("/tradability", response_model=list[TradabilityRow], summary="Is each symbol worth trading at the current cost?")
def tradability():
    try:
        return paper_service.tradability_report()
    except NotEnoughDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.post("/orders", response_model=PositionOut, status_code=201, summary="Place a paper order (filled at the next candle's open)")
def place_order(order: OrderIn):
    try:
        return paper_service.create_order(order.symbol, order.timeframe, order.side, order.stop_price, order.rr, order.source)
    except UnsupportedSymbolError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except OrderRejected as exc:
        raise HTTPException(status_code=409, detail={"message": "order rejected by the risk engine", "reasons": exc.reasons, "position_id": exc.position_id})
    except NotEnoughDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.delete("/orders/{position_id}", response_model=PositionOut, summary="Cancel a pending order")
def cancel_order(position_id: int):
    try:
        return paper_service.cancel_order(position_id)
    except OrderNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except OrderNotCancellable as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.post("/tick", response_model=TickResult, summary="Process new closed candles: fill pending orders, check stops and targets")
def tick():
    try:
        return paper_service.tick()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.get("/positions", response_model=list[PositionOut], summary="Paper positions, newest first")
def positions(status: Literal["pending", "open", "closed", "rejected", "cancelled"] | None = None, limit: int = 100):
    try:
        return paper_service.list_positions(status, min(max(limit, 1), 500))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")


@router.get("/summary", response_model=SummaryOut, summary="Equity, drawdown, today's result and open positions")
def summary():
    try:
        return paper_service.summary()
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")
