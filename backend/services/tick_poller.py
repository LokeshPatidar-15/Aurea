import asyncio
import logging

log = logging.getLogger("aurea.ws")

MAX_BACKOFF_SECONDS = 60.0


def tick_from_price(raw: dict) -> dict:
    source = str(raw.get("source", "unknown"))
    return {
        "symbol": raw.get("symbol"),
        "price": raw.get("price"),
        "ts": raw.get("timestamp"),
        "source": f"{source}-poll",
        "mock": raw.get("mock"),
        "change_percent_24h": raw.get("change_percent_24h"),
    }


class PollingTicker:
    def __init__(self, hub, fetch, symbols, interval_s: float, sleep=asyncio.sleep, to_thread=asyncio.to_thread, to_tick=None, gate=None):
        self.hub = hub
        self.fetch = fetch
        self.symbols = tuple(symbols)
        self.interval_s = interval_s
        self._sleep = sleep
        self._to_thread = to_thread
        self._to_tick = to_tick or tick_from_price
        self._gate = gate
        self.skipped_gated = 0
        self.failures: dict[str, int] = {s: 0 for s in self.symbols}
        self.last_error_type: dict[str, str] = {}
        self.cycles = 0
        self.skipped_no_subscribers = 0

    async def poll_once(self) -> tuple[int, int]:
        if self._gate is not None and not self._gate():
            self.skipped_gated += 1
            self.cycles += 1
            self.hub.meta["poller"] = self.status()
            return 0, 0
        attempted = 0
        failed = 0
        for symbol in self.symbols:
            if not self.hub.has_subscribers(symbol):
                self.skipped_no_subscribers += 1
                continue
            attempted += 1
            try:
                raw = await self._to_thread(self.fetch, symbol)
                ok = self.hub.publish(self._to_tick(raw))
            except Exception as exc:
                ok = False
                self.last_error_type[symbol] = type(exc).__name__
                log.warning("tick poll failed for %s: %s", symbol, type(exc).__name__)
            if ok:
                self.failures[symbol] = 0
            else:
                self.failures[symbol] += 1
                failed += 1
        self.cycles += 1
        self.hub.meta["poller"] = self.status()
        return attempted, failed

    def next_delay(self, attempted: int, failed: int) -> float:
        if attempted == 0 or failed < attempted:
            return self.interval_s
        worst = max(self.failures.values())
        return min(MAX_BACKOFF_SECONDS, self.interval_s * (2 ** min(worst, 5)))

    def status(self) -> dict:
        return {
            "interval_s": self.interval_s,
            "cycles": self.cycles,
            "skipped_gated": self.skipped_gated,
            "consecutive_failures": dict(self.failures),
            "last_error_type": dict(self.last_error_type),
        }

    async def run(self) -> None:
        while True:
            attempted, failed = await self.poll_once()
            await self._sleep(self.next_delay(attempted, failed))
