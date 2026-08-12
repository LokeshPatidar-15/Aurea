from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import requests

app = FastAPI()

# CORS: browser React app (localhost:5174) ko backend (localhost:8001) se
# baat karne ki permission deta hai. Bina iske browser request block kar dega.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # abhi ke liye sab allow, production mein specific origin denge
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Aurea backend is alive"}

@app.get("/price/{symbol}")
def get_price(symbol: str):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return {"symbol": symbol, "price": float(data["price"])}
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}
