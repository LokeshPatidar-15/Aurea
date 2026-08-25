from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    direction: str

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

@app.post("/trades")
def create_trade(trade: Trade):
    trades_db.append(trade.dict())
    return {"message": "Trade added", "trade": trade}

# QUERY PARAMETERS: /trades?limit=5&direction=long
# Both are OPTIONAL (have default values) - that's what makes them query params, not path params.
@app.get("/trades")
def list_trades(limit: int = 10, direction: str | None = None):
    results = trades_db
    if direction:
        results = [t for t in results if t["direction"] == direction]
    return results[-limit:]  # most recent `limit` trades
