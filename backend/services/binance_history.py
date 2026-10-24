import time
from datetime import datetime, timezone

import requests

from config import settings

INTERVAL_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}
SOURCE_SYMBOL = {"BTCUSDT": "BTCUSDT", "XAUUSD": "PAXGUSDT", "EURUSD": "EURUSDT"}
PAGE_LIMIT = 1000
RETRY_STATUS = {418, 429, 500, 502, 503, 504}


class HistoryError(Exception):
    pass


def _get_page(params: dict, retries: int = 4) -> list:
    url = f"{settings.binance_base_url}/klines"
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=max(settings.request_timeout_seconds, 15))
        except requests.RequestException as exc:
            if attempt == retries - 1:
                raise HistoryError(f"Binance unreachable: {exc}") from exc
            time.sleep(2**attempt)
            continue
        if resp.status_code in RETRY_STATUS and attempt < retries - 1:
            time.sleep(2**attempt)
            continue
        if resp.status_code != 200:
            raise HistoryError(f"Binance returned {resp.status_code}: {resp.text[:200]}")
        return resp.json()
    raise HistoryError("unreachable")


def parse_kline(row: list) -> dict:
    return {
        "open_time": datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc),
        "open": row[1],
        "high": row[2],
        "low": row[3],
        "close": row[4],
        "volume": row[5],
        "close_time_ms": row[6],
    }


def fetch_range(symbol: str, timeframe: str, start_ms: int, end_ms: int, pause: float = 0.15, page_fn=_get_page) -> list[dict]:
    source = SOURCE_SYMBOL.get(symbol, symbol)
    step = INTERVAL_MS[timeframe]
    now_ms = int(time.time() * 1000)
    cursor = start_ms
    out: list[dict] = []
    while cursor < end_ms:
        page = page_fn({"symbol": source, "interval": timeframe, "startTime": cursor, "endTime": end_ms, "limit": PAGE_LIMIT})
        if not page:
            break
        out.extend(parse_kline(r) for r in page)
        last_open_ms = page[-1][0]
        next_cursor = last_open_ms + step
        if next_cursor <= cursor:
            raise HistoryError("pagination did not advance")
        cursor = next_cursor
        if len(page) < PAGE_LIMIT:
            break
        time.sleep(pause)
    return [c for c in out if c["close_time_ms"] < now_ms]
