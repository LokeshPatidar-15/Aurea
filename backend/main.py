from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Literal
import requests
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CRYPTO_SYMBOLS = {"BTCUSDT", "ETHUSDT"}
trades_db = []

class Trade(BaseModel):
    symbol: str = Field(..., min_length=3, description="Trading pair symbol, e.g. BTCUSDT")
    entry_price: float = Field(..., gt=0, description="Must be greater than 0")
    exit_price: float = Field(..., gt=0, description="Must be greater than 0")
    quantity: float = Field(..., gt=0, description="Must be greater than 0")
    direction: Literal["long", "short"]  # ONLY these two values are allowed now

class TradeResponse(BaseModel):
    id: int
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    direction: str
    pnl: float  # computed field, not something the client sends

@app.get("/")
def read_root():
    return {"message": "Aurea backend is alive"}

@app.get("/price/{symbol}")
def get_price(symbol: str):
    if symbol in CRYPTO_SYMBOLS:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            return {"symbol": symbol, "price": float(data["price"])}
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}
    else:
        mock_base = {"XAUUSD": 1950.0, "EURUSD": 1.09}
        base = mock_base.get(symbol, 100.0)
        fake_price = base + random.uniform(-1, 1)
        return {"symbol": symbol, "price": round(fake_price, 4), "mock": True}

@app.post("/trades", response_model=TradeResponse)
def create_trade(trade: Trade):
    diff = trade.exit_price - trade.entry_price
    if trade.direction == "short":
        diff = -diff
    pnl = diff * trade.quantity

    record = trade.dict()
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
