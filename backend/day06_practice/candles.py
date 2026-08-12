candles = [
    {"time": "09:00", "open": 1950.0, "high": 1955.0, "low": 1948.0, "close": 1953.0},
    {"time": "09:01", "open": 1953.0, "high": 1954.0, "low": 1949.0, "close": 1950.0},
    {"time": "09:02", "open": 1950.0, "high": 1960.0, "low": 1950.0, "close": 1958.0},
    {"time": "09:03", "open": 1958.0, "high": 1959.0, "low": 1945.0, "close": 1946.0},
]

# Traditional loop: find bullish candles (close > open)
bullish_candles = []
for c in candles:
    if c["close"] > c["open"]:
        bullish_candles.append(c)

# Same thing with a list comprehension
bullish_candles_v2 = [c for c in candles if c["close"] > c["open"]]

# Comprehension to extract just closing prices
closes = [c["close"] for c in candles]

# Comprehension with transformation: candle range (high - low)
ranges = [c["high"] - c["low"] for c in candles]

print("Bullish candles:", len(bullish_candles_v2))
print("Closing prices:", closes)
print("Candle ranges:", ranges)
print("Average close:", sum(closes) / len(closes))
