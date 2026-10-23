import random
import time

import requests

BINANCE_URL = "https://api.binance.com/api/v3"

CRYPTO_SYMBOLS = {"BTCUSDT", "ETHUSDT"}
MOCK_BASE = {"XAUUSD": 1950.0, "EURUSD": 1.09}
SUPPORTED_SYMBOLS = CRYPTO_SYMBOLS | set(MOCK_BASE)

INTERVAL_SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


class InvalidSymbolError(Exception):
    pass


class UnsupportedSymbolError(Exception):
    pass


class PriceServiceError(Exception):
    pass


def normalize_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if len(symbol) < 3 or not symbol.isalnum():
        raise InvalidSymbolError("Invalid symbol")
    if symbol not in SUPPORTED_SYMBOLS:
        raise UnsupportedSymbolError(f"Unsupported symbol: {symbol}")
    return symbol


def _binance_get(path: str, params: dict):
    try:
        response = requests.get(f"{BINANCE_URL}{path}", params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        raise PriceServiceError(f"Market data provider unavailable: {e}")


def get_price(symbol: str) -> dict:
    symbol = normalize_symbol(symbol)

    if symbol in CRYPTO_SYMBOLS:
        data = _binance_get("/ticker/24hr", {"symbol": symbol})
        try:
            return {
                "symbol": symbol,
                "price": float(data["lastPrice"]),
                "change_percent_24h": float(data["priceChangePercent"]),
                "high_24h": float(data["highPrice"]),
                "low_24h": float(data["lowPrice"]),
                "source": "binance",
                "mock": False,
                "timestamp": int(time.time() * 1000),
            }
        except (KeyError, ValueError) as e:
            raise PriceServiceError(f"Unexpected response from provider: {e}")

    base = MOCK_BASE[symbol]
    price = base * (1 + random.uniform(-0.0005, 0.0005))
    return {
        "symbol": symbol,
        "price": round(price, 4),
        "change_percent_24h": round(random.uniform(-0.5, 0.5), 2),
        "high_24h": round(price * 1.004, 4),
        "low_24h": round(price * 0.996, 4),
        "source": "mock",
        "mock": True,
        "timestamp": int(time.time() * 1000),
    }


def get_candles(symbol: str, interval: str = "1m", limit: int = 100) -> list:
    symbol = normalize_symbol(symbol)

    if symbol in CRYPTO_SYMBOLS:
        rows = _binance_get("/klines", {"symbol": symbol, "interval": interval, "limit": limit})
        try:
            return [
                {
                    "time": int(r[0]),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),
                }
                for r in rows
            ]
        except (IndexError, ValueError) as e:
            raise PriceServiceError(f"Unexpected candle format from provider: {e}")

    step = INTERVAL_SECONDS[interval]
    now = int(time.time())
    end = now - now % step
    price = MOCK_BASE[symbol]
    candles = []
    for i in range(limit):
        t = end - (limit - 1 - i) * step
        o = price
        c = o * (1 + random.uniform(-0.0008, 0.0008))
        h = max(o, c) * (1 + random.uniform(0, 0.0004))
        l = min(o, c) * (1 - random.uniform(0, 0.0004))
        candles.append(
            {
                "time": t * 1000,
                "open": round(o, 4),
                "high": round(h, 4),
                "low": round(l, 4),
                "close": round(c, 4),
                "volume": round(random.uniform(10, 100), 2),
            }
        )
        price = c
    return candles
