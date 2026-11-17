from pathlib import Path

ROOT = Path(__file__).parent


def edit(name, pairs, marker):
    path = ROOT / name
    text = path.read_text()
    if marker in text:
        print(f"{name}: already patched")
        return
    for old, new in pairs:
        assert old in text, f"{name}: expected text not found: {old[:60]!r}. Send me this file"
        text = text.replace(old, new, 1)
    path.write_text(text)
    print(f"{name}: patched")


edit(
    "services/ws_hub.py",
    [
        (
            "        self.meta: dict = {}\n",
            "        self.meta: dict = {}\n        self.proxies: dict = {}\n",
        ),
        (
            '                "symbols": list(self.symbols),\n                "server_time": self._wall_ms(),\n',
            '                "symbols": list(self.symbols),\n                "proxies": dict(self.proxies),\n                "server_time": self._wall_ms(),\n',
        ),
        (
            "        text = _dumps(out)\n        self.latest[out[\"symbol\"]] = (out, text)\n",
            "        proxy = tick.get(\"proxy\")\n"
            "        if isinstance(proxy, bool):\n"
            "            out[\"proxy\"] = proxy\n"
            "        feed_symbol = tick.get(\"feed_symbol\")\n"
            "        if isinstance(feed_symbol, str) and 3 <= len(feed_symbol) <= 20 and feed_symbol.isascii() and feed_symbol.isalnum():\n"
            "            out[\"feed_symbol\"] = feed_symbol\n"
            "        text = _dumps(out)\n        self.latest[out[\"symbol\"]] = (out, text)\n",
        ),
        (
            "    def status(self) -> dict:\n        now = self._wall_ms()\n",
            "    def _meta_snapshot(self) -> dict:\n"
            "        out = {}\n"
            "        for key, value in self.meta.items():\n"
            "            if callable(value):\n"
            "                try:\n"
            "                    value = value()\n"
            "                except Exception:\n"
            "                    value = {\"error\": \"status unavailable\"}\n"
            "            out[key] = value\n"
            "        return out\n\n"
            "    def status(self) -> dict:\n        now = self._wall_ms()\n",
        ),
        (
            '            "meta": dict(self.meta),\n',
            '            "meta": self._meta_snapshot(),\n',
        ),
    ],
    "_meta_snapshot",
)

edit(
    "services/tick_poller.py",
    [
        (
            "    def __init__(self, hub, fetch, symbols, interval_s: float, sleep=asyncio.sleep, to_thread=asyncio.to_thread):\n",
            "    def __init__(self, hub, fetch, symbols, interval_s: float, sleep=asyncio.sleep, to_thread=asyncio.to_thread, to_tick=None, gate=None):\n",
        ),
        (
            "        self._to_thread = to_thread\n",
            "        self._to_thread = to_thread\n        self._to_tick = to_tick or tick_from_price\n        self._gate = gate\n        self.skipped_gated = 0\n",
        ),
        (
            "    async def poll_once(self) -> tuple[int, int]:\n        attempted = 0\n",
            "    async def poll_once(self) -> tuple[int, int]:\n"
            "        if self._gate is not None and not self._gate():\n"
            "            self.skipped_gated += 1\n"
            "            self.cycles += 1\n"
            "            self.hub.meta[\"poller\"] = self.status()\n"
            "            return 0, 0\n"
            "        attempted = 0\n",
        ),
        (
            "ok = self.hub.publish(tick_from_price(raw))",
            "ok = self.hub.publish(self._to_tick(raw))",
        ),
        (
            '            "cycles": self.cycles,\n',
            '            "cycles": self.cycles,\n            "skipped_gated": self.skipped_gated,\n',
        ),
    ],
    "skipped_gated",
)

edit(
    "config.py",
    [
        (
            "    ws_max_clients: int = 100\n",
            '    ws_max_clients: int = 100\n    ws_feed_enabled: bool = True\n    ws_idle_grace_seconds: float = 60\n    binance_ws_url: str = "wss://stream.binance.com:9443/stream"\n',
        ),
    ],
    "ws_feed_enabled",
)

edit(
    "main.py",
    [
        (
            "from fastapi import Depends, FastAPI, HTTPException\n",
            "import requests\nfrom fastapi import Depends, FastAPI, HTTPException\n",
        ),
        (
            "from services.tick_poller import PollingTicker\n",
            "from services.live_feed import PROXY_FEEDS, BinanceWsFeed, make_websockets_connect, rest_fetcher\nfrom services.tick_poller import PollingTicker\n",
        ),
        (
            '''    task = None
    if settings.ws_poll_seconds > 0:
        ticker = PollingTicker(hub, price_service.get_price, DEFAULT_SYMBOLS, max(1.0, settings.ws_poll_seconds))
        task = asyncio.create_task(ticker.run(), name="tick-poller")
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
''',
            '''    hub.proxies = dict(PROXY_FEEDS)
    feed = None
    tasks = []
    if settings.ws_feed_enabled:
        feed = BinanceWsFeed(hub, settings.binance_ws_url, make_websockets_connect(), idle_grace_s=settings.ws_idle_grace_seconds)
        hub.meta["feed"] = feed.status
        tasks.append(asyncio.create_task(feed.run(), name="binance-ws-feed"))
    if settings.ws_poll_seconds > 0:
        fetch = rest_fetcher(requests.get, settings.binance_base_url, settings.request_timeout_seconds)
        ticker = PollingTicker(
            hub,
            fetch,
            DEFAULT_SYMBOLS,
            max(1.0, settings.ws_poll_seconds),
            to_tick=lambda raw: raw,
            gate=feed.fallback_wanted if feed else None,
        )
        tasks.append(asyncio.create_task(ticker.run(), name="rest-fallback-poller"))
    yield
    for task in tasks:
        task.cancel()
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task
''',
        ),
    ],
    "BinanceWsFeed",
)

edit(
    "scripts/day64_ws_check.py",
    [
        (
            'all(t["symbol"] == "BTCUSDT" and t["price"] > 0 and t["mock"] is False and t["source"] == "binance-poll" for t in ticks)',
            'all(t["symbol"] == "BTCUSDT" and t["price"] > 0 and t["mock"] is False and t["source"].startswith("binance") for t in ticks)',
        ),
        (
            'check("XAUUSD ticks arrive and are flagged mock=true", bool(xau) and all(t["mock"] is True and t["source"] == "mock-poll" for t in xau))',
            'check("XAUUSD ticks arrive, real data via the PAXG proxy, flagged proxy=true", bool(xau) and all(t["mock"] is False and t.get("proxy") is True for t in xau))',
        ),
        (
            '        print("  info: gold and euro ticks are random demo numbers until Day 65 adds a real feed. The UI must show them as demo.")\n',
            '        print("  info: since Day 65 gold and euro ticks come from the PAXGUSDT and EURUSDT proxies (flagged proxy=true).")\n',
        ),
        (
            '    check("with no subscribers the poller stops fetching (no ticks published while idle)", st2["counters"].get("ticks_published", 0) == published_now, f"{published_now} -> {st2[\'counters\'].get(\'ticks_published\', 0)}")\n',
            '    print("  info: since Day 65 the exchange feed stays open for a grace period after the last client leaves, so the idle check moved to day65_ws_check.py")\n',
        ),
    ],
    "t[\"source\"].startswith(\"binance\")",
)

env_example = ROOT / ".env.example"
text = env_example.read_text()
if "WS_FEED_ENABLED" not in text:
    env_example.write_text(text.rstrip("\n") + "\nWS_FEED_ENABLED=true\nWS_IDLE_GRACE_SECONDS=60\nBINANCE_WS_URL=wss://stream.binance.com:9443/stream\n")
    print(".env.example: patched")
