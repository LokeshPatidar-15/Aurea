import argparse
import time
from pathlib import Path

import pandas as pd
import requests

from config import settings

DATA_DIR = Path(__file__).parent.parent / "data"

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume", "close_time",
    "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore",
]


def download(symbol: str, interval: str, total: int) -> pd.DataFrame:
    rows: list = []
    end_time = None
    while len(rows) < total + 1:
        params = {"symbol": symbol, "interval": interval, "limit": 1000}
        if end_time is not None:
            params["endTime"] = end_time
        response = requests.get(f"{settings.binance_base_url}/klines", params=params, timeout=10)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        rows = batch + rows
        end_time = batch[0][0] - 1
        print(f"  fetched {len(rows)} candles")
        time.sleep(0.3)

    rows = rows[-(total + 1):]
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")[["open", "high", "low", "close", "volume", "trades"]]
    df = df.astype({"open": float, "high": float, "low": float, "close": float, "volume": float, "trades": int})
    return df.iloc[:-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Binance candles to a CSV file.")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--total", type=int, default=20000)
    args = parser.parse_args()

    print(f"Downloading {args.total} {args.interval} candles for {args.symbol}...")
    df = download(args.symbol, args.interval, args.total)

    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / f"{args.symbol}_{args.interval}.csv"
    df.to_csv(path)
    print(f"saved {len(df)} rows to {path}")
    print(f"from {df.index[0]} to {df.index[-1]}")


if __name__ == "__main__":
    main()
