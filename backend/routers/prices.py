from typing import Literal

from fastapi import APIRouter, Query

from schemas.price import Candle, PriceResponse
from services import price_service

router = APIRouter(prefix="/prices", tags=["Prices"])


@router.get("/{symbol}", response_model=PriceResponse, summary="Latest price with 24h stats")
def get_price(symbol: str):
    return price_service.get_price(symbol)


@router.get("/{symbol}/history", response_model=list[Candle], summary="OHLCV candle history")
def get_history(
    symbol: str,
    interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1m",
    limit: int = Query(100, ge=1, le=500),
):
    return price_service.get_candles(symbol, interval, limit)
