from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services import price_service
from services.price_service import (
    InvalidSymbolError,
    PriceServiceError,
    UnsupportedSymbolError,
)

app = FastAPI(title="Aurea API")

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)

trades_db = []


class Trade(BaseModel):
    symbol: str = Field(..., min_length=3, description="Trading pair symbol, e.g. BTCUSDT")
    entry_price: float = Field(..., gt=0)
    exit_price: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    direction: Literal["long", "short"]


class TradeResponse(BaseModel):
    id: int
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    direction: str
    pnl: float


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


def call_service(fn, *args):
    try:
        return fn(*args)
    except InvalidSymbolError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnsupportedSymbolError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PriceServiceError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/")
def read_root():
    return {"message": "Aurea backend is alive"}


@app.get("/prices/{symbol}", response_model=PriceResponse)
def get_prices(symbol: str):
    return call_service(price_service.get_price, symbol)


@app.get("/prices/{symbol}/history", response_model=list[Candle])
def get_price_history(
    symbol: str,
    interval: Literal["1m", "5m", "15m", "1h", "4h", "1d"] = "1m",
    limit: int = Query(100, ge=1, le=500),
):
    return call_service(price_service.get_candles, symbol, interval, limit)


@app.get("/price/{symbol}", response_model=PriceResponse, deprecated=True)
def get_price_legacy(symbol: str):
    return call_service(price_service.get_price, symbol)


@app.post("/trades", response_model=TradeResponse)
def create_trade(trade: Trade):
    diff = trade.exit_price - trade.entry_price
    if trade.direction == "short":
        diff = -diff
    pnl = diff * trade.quantity

    record = trade.model_dump()
    record["id"] = len(trades_db) + 1
    record["pnl"] = round(pnl, 2)
    trades_db.append(record)
    return record


@app.get("/trades")
def list_trades(limit: int = 10, direction: str | None = None):
    results = trades_db
    if direction:
        results = [t for t in results if t["direction"] == direction]
    return results[-limit:]
