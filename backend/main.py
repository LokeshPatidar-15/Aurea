from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests
import random

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Symbols Binance actually supports
CRYPTO_SYMBOLS = {"BTCUSDT", "ETHUSDT"}

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
        # TEMPORARY mock data for XAUUSD / EURUSD until Day 22 (real forex API)
        mock_base = {"XAUUSD": 1950.0, "EURUSD": 1.09}
        base = mock_base.get(symbol, 100.0)
        fake_price = base + random.uniform(-1, 1)
        return {"symbol": symbol, "price": round(fake_price, 4), "mock": True}
