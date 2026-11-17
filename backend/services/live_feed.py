import asyncio
import json
import logging
import math
import random
import time
from collections import Counter

log = logging.getLogger("aurea.feed")

FEED_SYMBOLS = {"BTCUSDT": "BTCUSDT", "XAUUSD": "PAXGUSDT", "EURUSD": "EURUSDT"}
PROXY_FEEDS = {"XAUUSD": "PAXGUSDT", "EURUSD": "EURUSDT"}
_REVERSE = {feed: symbol for symbol, feed in FEED_SYMBOLS.items()}
BACKOFF_SECONDS = (1.0, 2.0, 4.0, 8.0, 16.0, 30.0)


class FeedStale(Exception):
    pass


def _wall_ms() -> int:
    return int(time.time() * 1000)


def _num(value) -> float:
    if isinstance(value, bool):
        raise ValueError("bool is not a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("not finite")
    return number


def stream_url(base: str, symbols=tuple(FEED_SYMBOLS)) -> str:
    streams = "/".join(f"{FEED_SYMBOLS[s].lower()}@miniTicker" for s in symbols)
    return f"{base}?streams={streams}"


def parse_mini_ticker(message) -> tuple[dict | None, str | None]:
    if isinstance(message, (bytes, bytearray)):
        try:
            message = bytes(message).decode("utf-8")
        except UnicodeDecodeError:
            return None, "invalid_json"
    if isinstance(message, str):
        try:
            message = json.loads(message)
        except (ValueError, RecursionError):
            return None, "invalid_json"
    if not isinstance(message, dict):
        return None, "not_an_object"
    data = message.get("data")
    if not isinstance(data, dict) or data.get("e") != "24hrMiniTicker":
        return None, "other_event"
    feed_symbol = data.get("s")
    if not isinstance(feed_symbol, str) or feed_symbol not in _REVERSE:
        return None, "unknown_symbol"
    symbol = _REVERSE[feed_symbol]
    try:
        price = _num(data.get("c"))
        event_time = data.get("E")
        if isinstance(event_time, bool) or not isinstance(event_time, int) or event_time <= 0:
            raise ValueError("bad event time")
        if price <= 0:
            raise ValueError("price must be positive")
        open_raw = data.get("o")
        open_price = _num(open_raw) if open_raw is not None else None
    except (TypeError, ValueError):
        return None, "bad_fields"
    tick = {
        "symbol": symbol,
        "price": price,
        "ts": event_time,
        "source": "binance-ws",
        "mock": False,
        "proxy": symbol in PROXY_FEEDS,
        "feed_symbol": feed_symbol,
    }
    if open_price is not None and open_price > 0:
        tick["change_percent_24h"] = (price - open_price) / open_price * 100.0
    return tick, None


def parse_rest_ticker(symbol: str, data: dict, now_ms: int) -> dict:
    try:
        price = _num(data["lastPrice"])
        raw_change = data.get("priceChangePercent")
        change = _num(raw_change) if raw_change is not None else None
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValueError("unexpected ticker format")
    if price <= 0:
        raise ValueError("unexpected ticker format")
    tick = {
        "symbol": symbol,
        "price": price,
        "ts": now_ms,
        "source": "binance-rest",
        "mock": False,
        "proxy": symbol in PROXY_FEEDS,
        "feed_symbol": FEED_SYMBOLS[symbol],
    }
    if change is not None:
        tick["change_percent_24h"] = change
    return tick


def rest_fetcher(http_get, base_url: str, timeout_s: float, wall_ms=_wall_ms):
    def fetch(symbol: str) -> dict:
        response = http_get(f"{base_url}/ticker/24hr", params={"symbol": FEED_SYMBOLS[symbol]}, timeout=timeout_s)
        response.raise_for_status()
        return parse_rest_ticker(symbol, response.json(), wall_ms())

    return fetch


def make_websockets_connect():
    def connect(url: str):
        import websockets

        return websockets.connect(url, ping_interval=20, ping_timeout=20, max_size=2**20, open_timeout=10)

    return connect


class BinanceWsFeed:
    def __init__(
        self,
        hub,
        base_url: str,
        connect,
        idle_grace_s: float = 60.0,
        stale_after_s: float = 15.0,
        recv_timeout_s: float = 5.0,
        healthy_within_s: float = 10.0,
        fallback_after_s: float = 10.0,
        backoff=BACKOFF_SECONDS,
        jitter=None,
        sleep=asyncio.sleep,
        monotonic=time.monotonic,
    ):
        self.hub = hub
        self.url = stream_url(base_url)
        self.connect = connect
        self.idle_grace_s = idle_grace_s
        self.stale_after_s = stale_after_s
        self.recv_timeout_s = recv_timeout_s
        self.healthy_within_s = healthy_within_s
        self.fallback_after_s = fallback_after_s
        self.backoff = tuple(backoff)
        self._jitter = jitter or (lambda delay: delay * random.uniform(0.8, 1.2))
        self._sleep = sleep
        self._monotonic = monotonic
        self.state = "idle"
        self.attempt = 0
        self.last_msg: float | None = None
        self.messages = 0
        self.ticks_published = 0
        self.ticks_refused_by_hub = 0
        self.reconnects = 0
        self.ignored = 0
        self.parse_rejects: Counter = Counter()
        self.last_error_type: str | None = None
        self._unhealthy_since: float | None = None

    def healthy(self) -> bool:
        if self.state != "connected" or self.last_msg is None:
            return False
        return self._monotonic() - self.last_msg <= self.healthy_within_s

    def fallback_wanted(self) -> bool:
        now = self._monotonic()
        if not self.hub.clients or self.healthy():
            self._unhealthy_since = None
            return False
        if self._unhealthy_since is None:
            self._unhealthy_since = now
        return now - self._unhealthy_since >= self.fallback_after_s

    def status(self) -> dict:
        age = None if self.last_msg is None else round(self._monotonic() - self.last_msg, 2)
        host = self.url.split("://", 1)[-1].split("/", 1)[0]
        return {
            "state": self.state,
            "healthy": self.healthy(),
            "host": host,
            "last_message_age_s": age,
            "messages": self.messages,
            "ticks_published": self.ticks_published,
            "ticks_refused_by_hub": self.ticks_refused_by_hub,
            "ignored_events": self.ignored,
            "parse_rejects": dict(self.parse_rejects),
            "reconnects": self.reconnects,
            "last_error_type": self.last_error_type,
            "rest_fallback_active": self.fallback_wanted(),
        }

    def _handle(self, raw) -> None:
        tick, reason = parse_mini_ticker(raw)
        if tick is None:
            if reason == "other_event":
                self.ignored += 1
            else:
                self.parse_rejects[reason] += 1
            return
        if self.hub.publish(tick):
            self.ticks_published += 1
        else:
            self.ticks_refused_by_hub += 1

    async def _session(self) -> None:
        self.state = "connecting"
        async with self.connect(self.url) as ws:
            self.state = "connected"
            self.last_msg = self._monotonic()
            idle_since = None
            while True:
                if not self.hub.clients:
                    now = self._monotonic()
                    idle_since = now if idle_since is None else idle_since
                    if now - idle_since >= self.idle_grace_s:
                        self.state = "idle"
                        return
                else:
                    idle_since = None
                try:
                    raw = await asyncio.wait_for(ws.recv(), self.recv_timeout_s)
                except asyncio.TimeoutError:
                    if self._monotonic() - self.last_msg > self.stale_after_s:
                        raise FeedStale("no message from the exchange")
                    continue
                self.last_msg = self._monotonic()
                self.messages += 1
                self.attempt = 0
                self._handle(raw)

    async def run(self) -> None:
        while True:
            if not self.hub.clients:
                self.state = "idle"
                await self._sleep(1.0)
                continue
            try:
                await self._session()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error_type = type(exc).__name__
                self.reconnects += 1
                self.state = "backoff"
                delay = self.backoff[min(self.attempt, len(self.backoff) - 1)]
                self.attempt += 1
                log.warning("market feed dropped (%s), retry in %.1fs", self.last_error_type, delay)
                await self._sleep(self._jitter(delay))
