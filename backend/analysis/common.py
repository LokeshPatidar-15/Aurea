from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_DIR = Path(__file__).parent / "output"


def load_candles(symbol: str = "BTCUSDT", timeframe: str = "1m") -> pd.DataFrame:
    path = DATA_DIR / f"{symbol}_{timeframe}.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run: python3 -m analysis.download_sample")
    df = pd.read_csv(path, parse_dates=["open_time"], index_col="open_time")
    df.index = pd.to_datetime(df.index, utc=True)
    return df


OHLCV_RULES = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
    "trades": "sum",
}


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule).agg(OHLCV_RULES)
    return out.dropna(subset=["close"])
