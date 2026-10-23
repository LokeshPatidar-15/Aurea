from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from services import price_service, trade_service
from services.price_service import (
    InvalidSymbolError,
    PriceServiceError,
    UnsupportedSymbolError,
)
from services.trade_service import TradeNotFoundError

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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)


class Trade(BaseModel):
    symbol: str = Field(..., min_length=3, description="Trading pair symbol, e.g. BTCUSDT")
    entry_price: float = Field(..., gt=0)
    exit_price: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    direction: Literal["long", "short"]
    notes: str = Field("", max_length=500)


class TradeUpdate(BaseModel):
    symbol: str | None = Field(None, min_length=3)
    entry_price: float | None = Field(None, gt=0)
    exit_price: float | None = Field(None, gt=0)
    quantity: float | None = Field(None, gt=0)
    direction: Literal["long", "short"] | None = None
    notes: str | None = Field(None, max_length=500)


class TradeResponse(BaseModel):
    id: int
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    direction: str
    notes: str
    pnl: float
    created_at: str


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
    except (UnsupportedSymbolError, TradeNotFoundError) as e:
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


@app.post("/trades", response_model=TradeResponse, status_code=201)
def create_trade(trade: Trade):
    return call_service(trade_service.create_trade, trade.model_dump())


@app.get("/trades", response_model=list[TradeResponse])
def list_trades(
    limit: int = Query(10, ge=1, le=200),
    direction: Literal["long", "short"] | None = None,
    symbol: str | None = None,
):
    return trade_service.list_trades(limit, direction, symbol)


@app.get("/trades/{trade_id}", response_model=TradeResponse)
def get_trade(trade_id: int):
    return call_service(trade_service.get_trade, trade_id)


@app.put("/trades/{trade_id}", response_model=TradeResponse)
def replace_trade(trade_id: int, trade: Trade):
    return call_service(trade_service.replace_trade, trade_id, trade.model_dump())


@app.patch("/trades/{trade_id}", response_model=TradeResponse)
def update_trade(trade_id: int, changes: TradeUpdate):
    return call_service(
        trade_service.update_trade, trade_id, changes.model_dump(exclude_unset=True)
    )


@app.delete("/trades/{trade_id}", status_code=204)
def delete_trade(trade_id: int):
    call_service(trade_service.delete_trade, trade_id)
    return Response(status_code=204)
