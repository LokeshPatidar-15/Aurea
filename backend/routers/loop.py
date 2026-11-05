from fastapi import APIRouter, HTTPException

from schemas.loop import CycleOut
from services import trading_loop

router = APIRouter(prefix="/loop", tags=["Trading loop"])


@router.post("/run", response_model=CycleOut, summary="Run one cycle now: ingest, tick, signals, paper orders")
def run(ingest: bool = True, place_orders: bool = True):
    return trading_loop.run_cycle(ingest=ingest, place_orders=place_orders)


@router.get("/last", response_model=CycleOut, summary="Result of the most recent cycle in this server process")
def last():
    if not trading_loop.LAST_RUN:
        raise HTTPException(status_code=404, detail="no cycle has run in this server process yet")
    return trading_loop.LAST_RUN
