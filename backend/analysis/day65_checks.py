import asyncio
import json
import logging
import py_compile
import re
from pathlib import Path

from services.live_feed import (
    BACKOFF_SECONDS,
    FEED_SYMBOLS,
    BinanceWsFeed,
    FeedStale,
    parse_mini_ticker,
    parse_rest_ticker,
    rest_fetcher,
    stream_url,
)
from services.tick_poller import PollingTicker
from services.ws_hub import Hub

ROOT = Path(__file__).resolve().parent.parent
logging.getLogger("aurea.feed").setLevel(logging.CRITICAL)
results = {"passed": 0, "failed": 0}
NOW_MS = 1_780_000_000_000


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def mini(symbol="BTCUSDT", close="64210.50", open_="63000.00", event=NOW_MS, event_type="24hrMiniTicker"):
    return json.dumps({"stream": symbol.lower() + "@miniTicker", "data": {"e": event_type, "E": event, "s": symbol, "c": close, "o": open_, "h": "65000.00", "l": "62000.00", "v": "100.5", "q": "6400000.1"}})


def make_hub(**kw):
    kw.setdefault("wall_ms", lambda: NOW_MS + 5000)
    return Hub(**kw)


def subscribe_all(hub):
    client = hub.add_client()
    client.control.clear()
    hub.handle_message(client, json.dumps({"action": "subscribe", "symbols": ["BTCUSDT", "XAUUSD", "EURUSD"]}))
    client.control.clear()
    return client


def pending(client):
    out = [json.loads(t) for t in client.pending.values()]
    client.pending.clear()
    return out


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class FakeWs:
    def __init__(self, script):
        self.script = list(script)

    async def recv(self):
        if not self.script:
            await asyncio.sleep(3600)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeConnect:
    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = 0
        self.entered = 0
        self.exited = 0
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        self.calls += 1
        script = self.scripts.pop(0) if self.scripts else []
        outer = self

        class Ctx:
            async def __aenter__(self):
                if isinstance(script, Exception):
                    raise script
                outer.entered += 1
                return FakeWs(script)

            async def __aexit__(self, *exc):
                outer.exited += 1
                return False

        return Ctx()


class Recorder:
    def __init__(self):
        self.delays = []

    async def sleep(self, seconds):
        self.delays.append(seconds)
        await asyncio.sleep(0.001)


def fast_feed(hub, connect, rec=None, **kw):
    rec = rec or Recorder()
    kw.setdefault("recv_timeout_s", 0.01)
    kw.setdefault("stale_after_s", 5.0)
    kw.setdefault("idle_grace_s", 0.05)
    kw.setdefault("jitter", lambda d: d)
    return BinanceWsFeed(hub, "wss://example.test/stream", connect, sleep=rec.sleep, **kw), rec


async def stop(task):
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


def test_parsing():
    print("parsing exchange messages")
    tick, why = parse_mini_ticker(mini())
    check("a BTC miniTicker becomes a tick", why is None and tick["symbol"] == "BTCUSDT" and tick["price"] == 64210.5 and tick["ts"] == NOW_MS and tick["source"] == "binance-ws" and tick["mock"] is False)
    check("BTC is not a proxy", tick["proxy"] is False and tick["feed_symbol"] == "BTCUSDT")
    check("24h change is (close - open) / open in percent", abs(tick["change_percent_24h"] - (64210.5 - 63000) / 63000 * 100) < 1e-9)
    tick, _ = parse_mini_ticker(mini("PAXGUSDT", "2650.25", "2600.00"))
    check("PAXGUSDT is published as XAUUSD and flagged proxy", tick["symbol"] == "XAUUSD" and tick["proxy"] is True and tick["feed_symbol"] == "PAXGUSDT")
    tick, _ = parse_mini_ticker(mini("EURUSDT", "1.0843", "1.0800"))
    check("EURUSDT is published as EURUSD and flagged proxy", tick["symbol"] == "EURUSD" and tick["proxy"] is True)
    check("bytes frames are decoded", parse_mini_ticker(mini().encode())[0] is not None)
    tick, _ = parse_mini_ticker(mini(open_="0"))
    check("a zero open price drops the change field instead of dividing by zero", "change_percent_24h" not in tick)
    for name, message, reason in [
        ("not json", "nope", "invalid_json"),
        ("bad bytes", b"\xff\xfe", "invalid_json"),
        ("a JSON list", "[1]", "not_an_object"),
        ("a subscription ack", json.dumps({"result": None, "id": 1}), "other_event"),
        ("another event type", mini(event_type="trade"), "other_event"),
        ("unknown symbol", mini("DOGEUSDT"), "unknown_symbol"),
        ("a symbol that is only a stream name", json.dumps({"data": {"e": "24hrMiniTicker", "s": "btcusdt", "c": "1", "E": 5}}), "unknown_symbol"),
        ("price text", mini(close="abc"), "bad_fields"),
        ("price nan", mini(close="nan"), "bad_fields"),
        ("price inf", mini(close="inf"), "bad_fields"),
        ("price zero", mini(close="0"), "bad_fields"),
        ("price negative", mini(close="-5"), "bad_fields"),
        ("missing price", json.dumps({"data": {"e": "24hrMiniTicker", "s": "BTCUSDT", "E": 5}}), "bad_fields"),
        ("event time as text", json.dumps({"data": {"e": "24hrMiniTicker", "s": "BTCUSDT", "c": "1", "E": "5"}}), "bad_fields"),
        ("event time bool", json.dumps({"data": {"e": "24hrMiniTicker", "s": "BTCUSDT", "c": "1", "E": True}}), "bad_fields"),
        ("price bool", json.dumps({"data": {"e": "24hrMiniTicker", "s": "BTCUSDT", "c": True, "E": 5}}), "bad_fields"),
    ]:
        tick, why = parse_mini_ticker(message)
        check(f"rejected: {name}", tick is None and why == reason, str(why))
    url = stream_url("wss://stream.binance.com:9443/stream")
    check("the stream URL asks for the 3 miniTicker streams, lower case", url == "wss://stream.binance.com:9443/stream?streams=btcusdt@miniTicker/paxgusdt@miniTicker/eurusdt@miniTicker", url)
    check("the feed symbol map is the documented one", FEED_SYMBOLS == {"BTCUSDT": "BTCUSDT", "XAUUSD": "PAXGUSDT", "EURUSD": "EURUSDT"})

    tick = parse_rest_ticker("XAUUSD", {"lastPrice": "2650.50", "priceChangePercent": "0.75"}, NOW_MS)
    check("a REST ticker becomes a tick with source binance-rest and proxy flag", tick["price"] == 2650.5 and tick["source"] == "binance-rest" and tick["mock"] is False and tick["proxy"] is True and tick["feed_symbol"] == "PAXGUSDT" and tick["change_percent_24h"] == 0.75)
    bad_count = 0
    for bad in [{}, {"lastPrice": "x"}, {"lastPrice": "0"}, {"lastPrice": "nan"}, {"lastPrice": None}, {"lastPrice": "5", "priceChangePercent": "zz"}, "text"]:
        try:
            parse_rest_ticker("BTCUSDT", bad, NOW_MS)
        except ValueError:
            bad_count += 1
    check("malformed REST data raises ValueError (7 cases)", bad_count == 7, str(bad_count))

    calls = []

    class Resp:
        def __init__(self, ok=True):
            self.ok = ok

        def raise_for_status(self):
            if not self.ok:
                raise RuntimeError("http 500 https://secret.example")

        def json(self):
            return {"lastPrice": "1.09", "priceChangePercent": "0.1"}

    def http_get(url, params, timeout):
        calls.append((url, params, timeout))
        return Resp(ok=params["symbol"] != "BTCUSDT")

    fetch = rest_fetcher(http_get, "https://api.example/api/v3", 5.0, wall_ms=lambda: NOW_MS)
    t = fetch("EURUSD")
    check("rest_fetcher asks the proxy pair for EURUSD", calls[0] == ("https://api.example/api/v3/ticker/24hr", {"symbol": "EURUSDT"}, 5.0) and t["symbol"] == "EURUSD" and t["ts"] == NOW_MS)
    try:
        fetch("BTCUSDT")
        raised = False
    except RuntimeError:
        raised = True
    check("an HTTP error propagates (the poller counts it as a failed poll)", raised)


async def test_feed_lifecycle():
    print("feed: connect only with clients, publish, reconnect, backoff")
    hub = make_hub()
    connect = FakeConnect([[mini()]])
    feed, rec = fast_feed(hub, connect)
    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.1)
    check("no clients: the feed never connects and stays idle", connect.calls == 0 and feed.state == "idle")
    client = subscribe_all(hub)
    await asyncio.sleep(0.1)
    check("a client appears: the feed connects once", connect.calls == 1 and connect.urls[0].startswith("wss://example.test/stream?streams=btcusdt@miniTicker"))
    got = pending(client)
    check("the message reached the subscriber as a binance-ws tick", len(got) == 1 and got[0]["source"] == "binance-ws" and got[0]["price"] == 64210.5 and got[0]["proxy"] is False)
    check("feed status counts the message", feed.messages == 1 and feed.ticks_published == 1 and feed.state == "connected")
    await stop(task)
    check("cancelling the feed closes the connection", connect.exited == connect.entered == 1)

    hub = make_hub()
    client = subscribe_all(hub)
    script = [mini("BTCUSDT", event=NOW_MS), mini("PAXGUSDT", "2650.25", "2600", event=NOW_MS + 1), mini("EURUSDT", "1.08", "1.07", event=NOW_MS + 2), "garbage", json.dumps({"result": None, "id": 1}), mini("DOGEUSDT"), mini(close="-1"), mini(event=NOW_MS + 10_000_000), mini(event=NOW_MS - 10_000)]
    connect = FakeConnect([script])
    feed, rec = fast_feed(hub, connect)
    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.1)
    got = {m["symbol"]: m for m in pending(client)}
    check("all three symbols arrive; gold and euro are proxies", set(got) == {"BTCUSDT", "XAUUSD", "EURUSD"} and got["XAUUSD"]["proxy"] is True and got["EURUSD"]["proxy"] is True and got["XAUUSD"]["feed_symbol"] == "PAXGUSDT")
    check("garbage, acks, unknown symbols and bad prices are counted, not fatal", feed.parse_rejects == {"invalid_json": 1, "unknown_symbol": 1, "bad_fields": 1} and feed.ignored == 1, str(dict(feed.parse_rejects)))
    check("a future-dated and an out-of-order tick are refused by the hub, the feed keeps running", feed.ticks_refused_by_hub == 2 and hub.rejected["future_ts"] == 1 and hub.rejected["out_of_order"] == 1 and feed.state == "connected", str(dict(hub.rejected)))
    await stop(task)

    hub = make_hub()
    subscribe_all(hub)
    boom = ConnectionResetError("secret https://x.example")
    scripts = [boom, boom, boom, [mini(), ConnectionResetError("closed")], []]
    connect = FakeConnect(scripts)
    feed, rec = fast_feed(hub, connect)
    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.4)
    check("three connect failures back off 1, 2, 4; a success resets the ladder to 1", rec.delays[:4] == [1.0, 2.0, 4.0, 1.0], str(rec.delays[:6]))
    check("after the drops it connects again and stays connected", connect.calls == 5 and feed.state == "connected" and feed.reconnects == 4)
    check("only the error class is kept, never the message", feed.last_error_type == "ConnectionResetError" and "secret" not in json.dumps(feed.status()))
    await stop(task)

    hub = make_hub()
    subscribe_all(hub)
    connect = FakeConnect([OSError("x")] * 8 + [[]])
    feed, rec = fast_feed(hub, connect)
    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.5)
    check("backoff is 1, 2, 4, 8, 16, 30 and then stays at 30", rec.delays[:8] == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0], str(rec.delays[:8]))
    check("the backoff table is the documented one", BACKOFF_SECONDS == (1.0, 2.0, 4.0, 8.0, 16.0, 30.0))
    await stop(task)

    hub = make_hub()
    subscribe_all(hub)
    connect = FakeConnect([[mini()], []])
    feed, rec = fast_feed(hub, connect, stale_after_s=0.05)
    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.4)
    check("a feed that goes silent is detected (watchdog) and reconnected", connect.calls >= 2 and feed.last_error_type == "FeedStale", f"calls={connect.calls} err={feed.last_error_type}")
    await stop(task)

    hub = make_hub()
    client = subscribe_all(hub)
    connect = FakeConnect([[mini()], [mini(event=NOW_MS + 5)]])
    feed, rec = fast_feed(hub, connect)
    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.1)
    hub.remove_client(client)
    await asyncio.sleep(0.2)
    check("when the last client leaves, the connection is closed after the grace period", connect.exited == 1 and feed.state == "idle")
    again = subscribe_all(hub)
    await asyncio.sleep(0.1)
    check("when a client returns, the feed connects again", connect.calls == 2 and len(pending(again)) == 1)
    await stop(task)
    check("no connection is left open", connect.entered == connect.exited)

    hub = make_hub()
    subscribe_all(hub)

    def import_fails(url):
        raise ImportError("no websockets")

    feed, rec = fast_feed(hub, import_fails)
    task = asyncio.create_task(feed.run())
    await asyncio.sleep(0.1)
    check("a missing websockets package is a normal failure with backoff, not a crash", feed.last_error_type == "ImportError" and feed.reconnects >= 1 and not task.done())
    await stop(task)


def test_fallback_gate():
    print("REST fallback gate")
    hub = make_hub()
    clock = Clock()
    feed = BinanceWsFeed(hub, "wss://example.test/stream", lambda url: None, monotonic=clock, fallback_after_s=10.0, healthy_within_s=10.0)
    check("no clients: never wanted", feed.fallback_wanted() is False)
    subscribe_all(hub)
    check("a client but the feed was never connected: starts the clock, not wanted yet", feed.fallback_wanted() is False)
    clock.t += 9
    check("9 s unhealthy: still not wanted", feed.fallback_wanted() is False)
    clock.t += 2
    check("11 s unhealthy: REST fallback is wanted", feed.fallback_wanted() is True)
    feed.state = "connected"
    feed.last_msg = clock.t
    check("the feed recovers: fallback is off again", feed.fallback_wanted() is False and feed.healthy())
    clock.t += 11
    check("connected but silent for 11 s counts as unhealthy (clock restarts)", feed.healthy() is False and feed.fallback_wanted() is False)
    clock.t += 11
    check("and 11 s later the fallback turns on", feed.fallback_wanted() is True)
    st = feed.status()
    check("status reports the fallback and the host without the full URL", st["rest_fallback_active"] is True and st["host"] == "example.test" and "streams" not in json.dumps(st))


async def test_fallback_poller():
    print("REST fallback end to end (fake exchange)")
    hub = make_hub()
    client = subscribe_all(hub)
    clock = Clock()
    feed = BinanceWsFeed(hub, "wss://example.test/stream", lambda url: None, monotonic=clock, fallback_after_s=10.0)
    fetched = []

    def http_get(url, params, timeout):
        fetched.append(params["symbol"])

        class R:
            def raise_for_status(self):
                return None

            def json(self):
                return {"lastPrice": "100.5", "priceChangePercent": "1.5"}

        return R()

    fetch = rest_fetcher(http_get, "https://api.example/api/v3", 5.0, wall_ms=lambda: NOW_MS + 1)
    poller = PollingTicker(hub, fetch, ("BTCUSDT", "XAUUSD", "EURUSD"), 5.0, to_tick=lambda raw: raw, gate=feed.fallback_wanted)
    a, f = await poller.poll_once()
    check("feed state unknown and the clock just started: the poller stays quiet", (a, f) == (0, 0) and fetched == [] and poller.skipped_gated == 1)
    clock.t += 11
    a, f = await poller.poll_once()
    got = {m["symbol"]: m for m in pending(client)}
    check("after 11 s without a healthy feed it polls all subscribed symbols over REST", fetched == ["BTCUSDT", "PAXGUSDT", "EURUSDT"] and (a, f) == (3, 0), str(fetched))
    check("REST ticks are real (mock false), tagged binance-rest, proxies flagged", all(m["source"] == "binance-rest" and m["mock"] is False for m in got.values()) and got["XAUUSD"]["proxy"] is True and got["BTCUSDT"]["proxy"] is False)
    feed.state = "connected"
    feed.last_msg = clock.t
    fetched.clear()
    a, f = await poller.poll_once()
    check("when the websocket feed is healthy again, REST polling stops", fetched == [] and (a, f) == (0, 0))
    check("the poller status shows how often it was gated", hub.status()["meta"]["poller"]["skipped_gated"] == 2)

    hub2 = make_hub()
    subscribe_all(hub2)
    p2 = PollingTicker(hub2, fetch, ("BTCUSDT",), 5.0, to_tick=lambda raw: raw)
    a, f = await p2.poll_once()
    check("without a gate (feed disabled) the poller works on its own", (a, f) == (1, 0))


def test_hub_extensions():
    print("hub: proxy fields, hello, status")
    hub = make_hub()
    hub.proxies = {"XAUUSD": "PAXGUSDT", "EURUSD": "EURUSDT"}
    c = hub.add_client()
    hello = json.loads(c.control[0])
    check("hello lists which symbols are proxies", hello["proxies"] == {"XAUUSD": "PAXGUSDT", "EURUSD": "EURUSDT"})
    client = subscribe_all(hub)
    base = {"symbol": "XAUUSD", "price": 2650.0, "ts": NOW_MS, "source": "binance-ws", "mock": False}
    hub.publish({**base, "proxy": True, "feed_symbol": "PAXGUSDT"})
    t = pending(client)[0]
    check("proxy and feed_symbol are passed through on the tick", t["proxy"] is True and t["feed_symbol"] == "PAXGUSDT")
    hub.publish({**base, "ts": NOW_MS + 1, "proxy": "yes", "feed_symbol": "x; drop table"})
    t = pending(client)[0]
    check("a non-bool proxy and a suspicious feed_symbol are dropped", "proxy" not in t and "feed_symbol" not in t)
    hub.publish({**base, "ts": NOW_MS + 2})
    t = pending(client)[0]
    check("ticks without the new fields still work (Day 64 style)", "proxy" not in t and t["price"] == 2650.0)
    hub.meta["feed"] = lambda: {"state": "connected"}
    hub.meta["broken"] = lambda: 1 / 0
    hub.meta["plain"] = 5
    st = hub.status()["meta"]
    check("status evaluates callable meta, survives a failing one, keeps plain values", st["feed"] == {"state": "connected"} and st["broken"] == {"error": "status unavailable"} and st["plain"] == 5)
    json.dumps(hub.status())
    check("the whole status is JSON serialisable", True)


def test_static():
    print("static: purity and wiring")
    src = (ROOT / "services/live_feed.py").read_text()
    imports = set(re.findall(r"^(?:from|import)\s+([\w\.]+)", src, re.M))
    allowed = {"asyncio", "json", "logging", "math", "random", "time", "collections"}
    check("services/live_feed.py imports only the standard library at module level", imports <= allowed, str(sorted(imports - allowed)))
    check("it has no database or ledger access", not re.search(r"paper_|sqlalchemy|\bsession\b|\.execute\(", src))
    check("it never logs message contents or the URL, only the error class", "log.warning(\"market feed dropped (%s), retry in %.1fs\", self.last_error_type, delay)" in src)
    for name in ("services/live_feed.py", "services/ws_hub.py", "services/tick_poller.py", "main.py", "config.py", "scripts/day64_ws_check.py", "scripts/day65_ws_check.py"):
        try:
            py_compile.compile(str(ROOT / name), doraise=True)
            ok = True
        except py_compile.PyCompileError as exc:
            ok = False
            print(exc)
        check(f"{name} compiles", ok)
    main_src = (ROOT / "main.py").read_text()
    check("main.py starts the websocket feed and the gated REST fallback", "BinanceWsFeed(" in main_src and "gate=feed.fallback_wanted" in main_src and "price_service.get_price" not in main_src.split("lifespan", 1)[1].split("app = FastAPI", 1)[0])
    check("no mock price source is used for ticks any more", "mock-poll" not in main_src and "mock-poll" not in src)
    cfg = (ROOT / "config.py").read_text()
    check("config has the feed switch, the idle grace and the websocket URL", "ws_feed_enabled" in cfg and "ws_idle_grace_seconds" in cfg and "binance_ws_url" in cfg)
    check("the websocket URL default uses wss (encrypted)", 'binance_ws_url: str = "wss://' in cfg)


def main():
    test_parsing()
    asyncio.run(test_feed_lifecycle())
    test_fallback_gate()
    asyncio.run(test_fallback_poller())
    test_hub_extensions()
    test_static()
    print(f"\n{results['passed']} passed, {results['failed']} failed")
    raise SystemExit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main()
