import asyncio
import json
import logging
import math
import time
from collections import Counter, deque
from dataclasses import dataclass, field

log = logging.getLogger("aurea.ws")

PROTOCOL_VERSION = 1
DEFAULT_SYMBOLS = ("BTCUSDT", "XAUUSD", "EURUSD")
MAX_MESSAGE_CHARS = 1024
MAX_SYMBOLS_PER_REQUEST = 20
MAX_BAD_MESSAGES = 10
FUTURE_TOLERANCE_MS = 60_000
SEND_TIMEOUT_SECONDS = 10.0
FLUSH_WAIT_SECONDS = 2.0


class ConnectionClosed(Exception):
    pass


def _dumps(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"), allow_nan=False)


def _wall_ms() -> int:
    return int(time.time() * 1000)


def origin_allowed(origin: str | None, allowed: list[str]) -> bool:
    if not origin:
        return True
    return origin in allowed


@dataclass
class Client:
    id: int
    control: deque = field(default_factory=deque)
    pending: dict = field(default_factory=dict)
    symbols: set = field(default_factory=set)
    recent: deque = field(default_factory=deque)
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    closed: bool = False
    close_code: int | None = None
    close_reason: str = ""
    bad: int = 0


class Hub:
    def __init__(
        self,
        symbols=DEFAULT_SYMBOLS,
        max_clients: int = 100,
        max_control_backlog: int = 50,
        rate_limit_messages: int = 30,
        rate_limit_window_s: float = 10.0,
        snapshot_max_age_ms: int = 30_000,
        monotonic=time.monotonic,
        wall_ms=_wall_ms,
        send_timeout_s: float = SEND_TIMEOUT_SECONDS,
    ):
        self.symbols = tuple(symbols)
        self.max_clients = max_clients
        self.max_control_backlog = max_control_backlog
        self.rate_limit_messages = rate_limit_messages
        self.rate_limit_window_s = rate_limit_window_s
        self.snapshot_max_age_ms = snapshot_max_age_ms
        self.send_timeout_s = send_timeout_s
        self._monotonic = monotonic
        self._wall_ms = wall_ms
        self.clients: dict[int, Client] = {}
        self.latest: dict[str, tuple[dict, str]] = {}
        self.stats: Counter = Counter()
        self.rejected: Counter = Counter()
        self.meta: dict = {}
        self._seq = 0
        self._next_id = 0

    def add_client(self) -> Client | None:
        if len(self.clients) >= self.max_clients:
            self.stats["clients_refused_full"] += 1
            return None
        self._next_id += 1
        client = Client(id=self._next_id)
        self.clients[client.id] = client
        self.stats["clients_connected_total"] += 1
        self._send_control(
            client,
            {
                "type": "hello",
                "protocol": PROTOCOL_VERSION,
                "symbols": list(self.symbols),
                "server_time": self._wall_ms(),
            },
        )
        return client

    def remove_client(self, client: Client) -> None:
        self.clients.pop(client.id, None)
        client.closed = True
        client.pending.clear()
        client.control.clear()
        client.wake.set()

    def close_client(self, client: Client, code: int, reason: str) -> None:
        if client.closed:
            return
        client.closed = True
        client.close_code = code
        client.close_reason = reason
        client.pending.clear()
        client.wake.set()

    def has_subscribers(self, symbol: str) -> bool:
        return any(symbol in c.symbols and not c.closed for c in self.clients.values())

    def _send_control(self, client: Client, message: dict) -> None:
        if client.closed:
            return
        if len(client.control) >= self.max_control_backlog:
            self.stats["clients_closed_backlog"] += 1
            self.close_client(client, 1008, "backlog")
            return
        client.control.append(_dumps(message))
        client.wake.set()

    def _error(self, client: Client, code: str, message: str) -> None:
        self.stats["messages_rejected"] += 1
        client.bad += 1
        self._send_control(client, {"type": "error", "code": code, "message": message})
        if client.bad >= MAX_BAD_MESSAGES and not client.closed:
            self.stats["clients_closed_bad_messages"] += 1
            self.close_client(client, 1008, "too many bad messages")

    def handle_message(self, client: Client, raw) -> None:
        if client.closed:
            return
        self.stats["messages_in"] += 1
        now = self._monotonic()
        while client.recent and now - client.recent[0] > self.rate_limit_window_s:
            client.recent.popleft()
        if len(client.recent) >= self.rate_limit_messages:
            self.stats["clients_closed_rate_limit"] += 1
            self._send_control(client, {"type": "error", "code": "rate_limited", "message": "too many messages"})
            self.close_client(client, 1008, "rate limited")
            return
        client.recent.append(now)

        if isinstance(raw, (bytes, bytearray)):
            self._error(client, "text_only", "send JSON text frames")
            return
        if not isinstance(raw, str) or len(raw) > MAX_MESSAGE_CHARS or len(raw.encode("utf-8")) > MAX_MESSAGE_CHARS:
            self._error(client, "message_too_large", f"max {MAX_MESSAGE_CHARS} characters")
            return
        try:
            data = json.loads(raw)
        except (ValueError, RecursionError):
            self._error(client, "invalid_json", "message is not valid JSON")
            return
        if not isinstance(data, dict) or not isinstance(data.get("action"), str):
            self._error(client, "invalid_message", 'expected an object like {"action": "subscribe", "symbols": [...]}')
            return

        action = data["action"]
        if action == "ping":
            self._send_control(client, {"type": "pong", "server_time": self._wall_ms()})
        elif action in ("subscribe", "unsubscribe"):
            self._handle_symbols(client, action, data.get("symbols"))
        else:
            self._error(client, "unknown_action", "actions: subscribe, unsubscribe, ping")

    def _handle_symbols(self, client: Client, action: str, symbols) -> None:
        if not isinstance(symbols, list) or not symbols or len(symbols) > MAX_SYMBOLS_PER_REQUEST or not all(isinstance(s, str) for s in symbols):
            self._error(client, "invalid_symbols", "symbols must be a non-empty list of strings")
            return
        wanted = {s.strip().upper() for s in symbols}
        unknown = wanted - set(self.symbols)
        if unknown:
            self._error(client, "unknown_symbol", "supported symbols: " + ", ".join(self.symbols))
            return
        if action == "subscribe":
            new = wanted - client.symbols
            client.symbols |= wanted
            self._send_control(client, {"type": "subscribed", "symbols": sorted(client.symbols)})
            now = self._wall_ms()
            for symbol in sorted(new):
                entry = self.latest.get(symbol)
                if entry and now - entry[0]["ts"] <= self.snapshot_max_age_ms:
                    client.pending[symbol] = entry[1]
                    client.wake.set()
        else:
            client.symbols -= wanted
            for symbol in wanted:
                client.pending.pop(symbol, None)
            self._send_control(client, {"type": "subscribed", "symbols": sorted(client.symbols)})

    def _tick_problem(self, tick) -> str | None:
        if not isinstance(tick, dict):
            return "not_a_dict"
        symbol = tick.get("symbol")
        if not isinstance(symbol, str) or symbol not in self.symbols:
            return "unknown_symbol"
        price = tick.get("price")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
            return "bad_price"
        ts = tick.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, int) or ts <= 0:
            return "bad_ts"
        if ts > self._wall_ms() + FUTURE_TOLERANCE_MS:
            return "future_ts"
        entry = self.latest.get(symbol)
        if entry and ts < entry[0]["ts"]:
            return "out_of_order"
        if not isinstance(tick.get("source"), str) or not tick["source"]:
            return "bad_source"
        if not isinstance(tick.get("mock"), bool):
            return "bad_mock"
        return None

    def publish(self, tick: dict) -> bool:
        problem = self._tick_problem(tick)
        if problem:
            self.rejected[problem] += 1
            return False
        self._seq += 1
        out = {
            "type": "tick",
            "seq": self._seq,
            "symbol": tick["symbol"],
            "price": float(tick["price"]),
            "ts": tick["ts"],
            "server_time": self._wall_ms(),
            "source": tick["source"],
            "mock": tick["mock"],
        }
        change = tick.get("change_percent_24h")
        if isinstance(change, (int, float)) and not isinstance(change, bool) and math.isfinite(change):
            out["change_percent_24h"] = float(change)
        text = _dumps(out)
        self.latest[out["symbol"]] = (out, text)
        self.stats["ticks_published"] += 1
        for client in self.clients.values():
            if not client.closed and out["symbol"] in client.symbols:
                client.pending[out["symbol"]] = text
                client.wake.set()
        return True

    async def pump(self, client: Client, send) -> None:
        while True:
            await client.wake.wait()
            client.wake.clear()
            while client.control or client.pending:
                if client.control:
                    text = client.control.popleft()
                else:
                    symbol = next(iter(client.pending))
                    text = client.pending.pop(symbol)
                try:
                    await asyncio.wait_for(send(text), self.send_timeout_s)
                except asyncio.TimeoutError:
                    self.stats["clients_closed_slow"] += 1
                    self.close_client(client, 1011, "send timeout")
                    return
            if client.closed:
                return

    def status(self) -> dict:
        now = self._wall_ms()
        subscriptions = {s: 0 for s in self.symbols}
        for client in self.clients.values():
            for symbol in client.symbols:
                subscriptions[symbol] += 1
        latest = {}
        for symbol, (out, _) in self.latest.items():
            latest[symbol] = {
                "price": out["price"],
                "ts": out["ts"],
                "age_ms": max(0, now - out["ts"]),
                "source": out["source"],
                "mock": out["mock"],
                "seq": out["seq"],
            }
        return {
            "protocol": PROTOCOL_VERSION,
            "clients": len(self.clients),
            "max_clients": self.max_clients,
            "subscriptions": subscriptions,
            "latest": latest,
            "counters": dict(self.stats),
            "ticks_rejected": dict(self.rejected),
            "meta": dict(self.meta),
        }


async def serve_connection(hub: Hub, receive, send) -> tuple[int, str]:
    client = hub.add_client()
    if client is None:
        return 1013, "server full"

    async def reader():
        while not client.closed:
            raw = await receive()
            try:
                hub.handle_message(client, raw)
            except Exception:
                log.exception("websocket message handler failed")
                hub.close_client(client, 1011, "internal error")

    reader_task = asyncio.create_task(reader())
    pump_task = asyncio.create_task(hub.pump(client, send))
    try:
        await asyncio.wait({reader_task, pump_task}, return_when=asyncio.FIRST_COMPLETED)
        if reader_task.done() and not pump_task.done():
            socket_gone = not reader_task.cancelled() and isinstance(reader_task.exception(), ConnectionClosed)
            if not socket_gone:
                hub.close_client(client, 1000, "")
                await asyncio.wait({pump_task}, timeout=FLUSH_WAIT_SECONDS)
    finally:
        hub.remove_client(client)
        for task in (reader_task, pump_task):
            task.cancel()
        await asyncio.gather(reader_task, pump_task, return_exceptions=True)
    return client.close_code or 1000, client.close_reason


hub = Hub()
