from typing import Literal

from pydantic import BaseModel


class PriceResponse(BaseModel):
    symbol: str
    price: float
    change_percent_24h: float
    high_24h: float
    low_24h: float
    source: Literal["binance", "mock"]
    mock: bool
    timestamp: int


class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float
