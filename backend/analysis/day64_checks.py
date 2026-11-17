import asyncio
import json
import math
import py_compile
import re
from pathlib import Path

from services.tick_poller import PollingTicker, tick_from_price
from services.ws_hub import (
    MAX_BAD_MESSAGES,
    MAX_MESSAGE_CHARS,
    ConnectionClosed,
    Hub,
    origin_allowed,
    serve_connection,
)

ROOT = Path(__file__).resolve().parent.parent
results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


NOW_MS = 1_780_000_000_000


def tick(symbol="BTCUSDT", price=64000.0, ts=NOW_MS, mock=False, source="binance-poll", **extra):
    base = {"symbol": symbol, "price": price, "ts": ts, "mock": mock, "source": source}
    base.update(extra)
    return base


def make_hub(**kw):
    kw.setdefault("wall_ms", lambda: NOW_MS + 1000)
    return Hub(**kw)


def drain(client):
    out = [json.loads(t) for t in client.control]
    client.control.clear()
    return out


def drain_pending(client):
    out = [json.loads(t) for t in client.pending.values()]
    client.pending.clear()
    return out


def send(hub, client, obj):
    hub.handle_message(client, obj if isinstance(obj, (str, bytes)) else json.dumps(obj))


class FakeSocket:
    def __init__(self, send_delay=0.0, send_fails=False):
        self.inbox = asyncio.Queue()
        self.sent = []
        self.send_delay = send_delay
        self.send_fails = send_fails

    async def receive(self):
        item = await self.inbox.get()
        if item is None:
            raise ConnectionClosed()
        return item

    async def send(self, text):
        if self.send_fails:
            raise RuntimeError("socket gone")
        if self.send_delay:
            await asyncio.sleep(self.send_delay)
        self.sent.append(json.loads(text))

    def types(self):
        return [m["type"] for m in self.sent]

    def ticks(self, symbol=None):
        return [m for m in self.sent if m["type"] == "tick" and (symbol is None or m["symbol"] == symbol)]


async def settle(seconds=0.05):
    await asyncio.sleep(seconds)


def test_protocol():
    print("protocol: hello, subscribe, errors")
    hub = make_hub()
    c = hub.add_client()
    msgs = drain(c)
    check("a new client gets a hello with protocol and symbols", msgs[0]["type"] == "hello" and msgs[0]["protocol"] == 1 and msgs[0]["symbols"] == ["BTCUSDT", "XAUUSD", "EURUSD"])
    send(hub, c, {"action": "subscribe", "symbols": ["btcusdt", " xauusd "]})
    m = drain(c)
    check("subscribe accepts lower case and spaces and confirms the full list", m == [{"type": "subscribed", "symbols": ["BTCUSDT", "XAUUSD"]}], str(m))
    send(hub, c, {"action": "subscribe", "symbols": ["BTCUSDT", "DOGE"]})
    m = drain(c)
    check("one unknown symbol rejects the whole request", m[0]["type"] == "error" and m[0]["code"] == "unknown_symbol")
    check("a rejected subscribe changes nothing (atomic)", c.symbols == {"BTCUSDT", "XAUUSD"})
    check("the error does not echo the user's input", "DOGE" not in json.dumps(m))
    for raw, code in [
        ("not json", "invalid_json"),
        ("[1,2]", "invalid_message"),
        ('"hi"', "invalid_message"),
        ("{}", "invalid_message"),
        ('{"action": 5}', "invalid_message"),
        ('{"action": "buy"}', "unknown_action"),
        ('{"action": "subscribe"}', "invalid_symbols"),
        ('{"action": "subscribe", "symbols": []}', "invalid_symbols"),
        ('{"action": "subscribe", "symbols": [1]}', "invalid_symbols"),
        ('{"action": "subscribe", "symbols": "BTCUSDT"}', "invalid_symbols"),
        ("x" * (MAX_MESSAGE_CHARS + 1), "message_too_large"),
        (b"\x00\x01", "text_only"),
        ("[" * 100000, "message_too_large"),
        ("é" * 600, "message_too_large"),
    ]:
        c2 = hub.add_client()
        drain(c2)
        send(hub, c2, raw)
        m = drain(c2)
        check(f"bad message -> {code}", len(m) == 1 and m[0].get("code") == code and not c2.closed, str(m)[:100])
    deep = "[" * 500 + "]" * 500
    c3 = hub.add_client()
    drain(c3)
    send(hub, c3, deep)
    m = drain(c3)
    check("deeply nested JSON does not crash the handler", len(m) == 1 and m[0]["type"] == "error")
    send(hub, c, {"action": "ping"})
    m = drain(c)
    check("ping gets a pong with server time", m[0]["type"] == "pong" and isinstance(m[0]["server_time"], int))
    send(hub, c, {"action": "unsubscribe", "symbols": ["XAUUSD"]})
    m = drain(c)
    check("unsubscribe confirms the remaining list", m == [{"type": "subscribed", "symbols": ["BTCUSDT"]}], str(m))


def test_publish():
    print("publish: validation, routing, sequence")
    hub = make_hub()
    a = hub.add_client()
    b = hub.add_client()
    d = hub.add_client()
    drain(a), drain(b), drain(d)
    send(hub, a, {"action": "subscribe", "symbols": ["BTCUSDT"]})
    send(hub, b, {"action": "subscribe", "symbols": ["XAUUSD"]})
    drain(a), drain(b)
    check("a valid tick is accepted", hub.publish(tick(price=64000.5, change_percent_24h=1.25)))
    pa, pb, pd = drain_pending(a), drain_pending(b), drain_pending(d)
    check("only the BTC subscriber receives it", len(pa) == 1 and not pb and not pd)
    t = pa[0]
    check("tick fields are complete", t["type"] == "tick" and t["symbol"] == "BTCUSDT" and t["price"] == 64000.5 and t["ts"] == NOW_MS and t["mock"] is False and t["source"] == "binance-poll" and t["change_percent_24h"] == 1.25 and "server_time" in t and "seq" in t)
    hub.publish(tick(ts=NOW_MS + 1, price=64001.0))
    hub.publish(tick("XAUUSD", 2650.0, mock=True, source="mock-poll"))
    seqs = [drain_pending(a)[0]["seq"]]
    check("sequence numbers increase across symbols", seqs[0] == 2 and hub.status()["latest"]["XAUUSD"]["seq"] == 3)
    bad = {
        "nan": tick(price=float("nan")),
        "inf": tick(price=float("inf")),
        "zero": tick(price=0),
        "negative": tick(price=-5),
        "bool": tick(price=True),
        "string": tick(price="64000"),
        "none": tick(price=None),
        "unknown symbol": tick("DOGEUSDT"),
        "symbol not str": tick(symbol=5),
        "missing ts": {k: v for k, v in tick().items() if k != "ts"},
        "float ts": tick(ts=1.5e12),
        "future ts": tick(ts=NOW_MS + 3_600_000),
        "old ts": tick(ts=NOW_MS - 5000),
        "no source": tick(source=""),
        "mock not bool": tick(mock="no"),
        "not a dict": [1, 2],
    }
    drain_pending(a), drain_pending(b)
    before = hub.stats["ticks_published"]
    for name, t_ in bad.items():
        check(f"rejected: {name}", hub.publish(t_) is False)
    check("rejected ticks are counted by reason and not published", hub.stats["ticks_published"] == before and sum(hub.rejected.values()) == len(bad), str(dict(hub.rejected)))
    check("rejected ticks never reach clients", not drain_pending(a) and not drain_pending(b))
    check("a NaN change field is dropped, tick still valid", hub.publish(tick(ts=NOW_MS + 5, change_percent_24h=float("nan"))) and "change_percent_24h" not in drain_pending(a)[0])
    check("every serialised message is strict JSON (no NaN)", all("NaN" not in text and "Infinity" not in text for _, text in hub.latest.values()))
    check("an equal timestamp is allowed (same-millisecond refetch)", hub.publish(tick(ts=NOW_MS + 5, price=64002.0)))


def test_conflation_and_snapshot():
    print("slow clients: conflation; snapshot on subscribe")
    hub = make_hub()
    c = hub.add_client()
    drain(c)
    send(hub, c, {"action": "subscribe", "symbols": ["BTCUSDT", "XAUUSD"]})
    drain(c)
    for i in range(5000):
        hub.publish(tick(price=60000 + i, ts=NOW_MS + i))
        hub.publish(tick("XAUUSD", 2000 + i, ts=NOW_MS + i, mock=True, source="mock-poll"))
    check("a client that never reads holds at most one tick per symbol", len(c.pending) == 2 and len(c.control) == 0)
    pend = {m["symbol"]: m for m in drain_pending(c)}
    check("and that tick is the newest one", pend["BTCUSDT"]["price"] == 64999 and pend["XAUUSD"]["price"] == 6999)

    hub = make_hub()
    hub.publish(tick(price=64000.0, ts=NOW_MS))
    c = hub.add_client()
    drain(c)
    send(hub, c, {"action": "subscribe", "symbols": ["BTCUSDT", "EURUSD"]})
    snap = drain_pending(c)
    check("subscribe delivers the cached fresh tick right away, none for a symbol without ticks", len(snap) == 1 and snap[0]["symbol"] == "BTCUSDT")
    old = make_hub(wall_ms=lambda: NOW_MS + 31_000)
    old.latest = hub.latest
    c = old.add_client()
    drain(c)
    send(old, c, {"action": "subscribe", "symbols": ["BTCUSDT"]})
    check("a cached tick older than 30 s is not sent as if it were current", not drain_pending(c))
    c = hub.add_client()
    drain(c)
    send(hub, c, {"action": "subscribe", "symbols": ["BTCUSDT"]})
    drain_pending(c)
    send(hub, c, {"action": "subscribe", "symbols": ["BTCUSDT"]})
    check("subscribing again to the same symbol does not resend a snapshot", not drain_pending(c))
    hub.publish(tick(ts=NOW_MS + 10, price=64100.0))
    send(hub, c, {"action": "unsubscribe", "symbols": ["BTCUSDT"]})
    check("unsubscribe drops the queued tick and stops delivery", not c.pending)
    hub.publish(tick(ts=NOW_MS + 20, price=64200.0))
    check("no delivery after unsubscribe", not c.pending)


def test_limits():
    print("abuse limits")
    clock = Clock()
    hub = make_hub(monotonic=clock, rate_limit_messages=30, rate_limit_window_s=10.0)
    c = hub.add_client()
    drain(c)
    for _ in range(30):
        send(hub, c, {"action": "ping"})
        drain(c)
        clock.t += 0.1
    check("30 messages in 10 s are fine", not c.closed)
    send(hub, c, {"action": "ping"})
    check("the 31st is rate limited and the client is closed with 1008", c.closed and c.close_code == 1008)
    check("the client is told why before the close", any(json.loads(t).get("code") == "rate_limited" for t in c.control))
    clock2 = Clock()
    hub = make_hub(monotonic=clock2)
    c = hub.add_client()
    drain(c)
    for _ in range(25):
        send(hub, c, {"action": "ping"})
        drain(c)
    clock2.t += 11
    for _ in range(25):
        send(hub, c, {"action": "ping"})
        drain(c)
    check("the window slides: 25 + wait + 25 is fine", not c.closed)

    hub = make_hub(rate_limit_messages=10_000)
    c = hub.add_client()
    drain(c)
    for _ in range(MAX_BAD_MESSAGES):
        send(hub, c, "garbage")
    check(f"{MAX_BAD_MESSAGES} bad messages close the client", c.closed and c.close_code == 1008 and c.close_reason == "too many bad messages")
    send(hub, c, {"action": "ping"})
    check("a closed client is ignored", len(c.control) <= MAX_BAD_MESSAGES + 1)

    hub = make_hub(rate_limit_messages=10_000, max_control_backlog=5)
    c = hub.add_client()
    for _ in range(20):
        send(hub, c, {"action": "ping"})
    check("a client that sends but never reads is closed when its backlog is full", c.closed and c.close_reason == "backlog" and len(c.control) <= 5)

    hub = make_hub(max_clients=2)
    a, b = hub.add_client(), hub.add_client()
    check("client limit refuses the third connection", hub.add_client() is None and hub.stats["clients_refused_full"] == 1)
    hub.remove_client(a)
    check("a freed slot can be used again", hub.add_client() is not None)
    check("origin: browsers from allowed origins pass, others are refused, no Origin (scripts) passes", origin_allowed("http://localhost:5173", ["http://localhost:5173"]) and not origin_allowed("http://evil.example", ["http://localhost:5173"]) and origin_allowed(None, ["x"]) and not origin_allowed("http://localhost:5173.evil.example", ["http://localhost:5173"]))


async def test_connections():
    print("connections: end to end with fake sockets")
    hub = make_hub()
    s1, s2 = FakeSocket(), FakeSocket()
    t1 = asyncio.create_task(serve_connection(hub, s1.receive, s1.send))
    t2 = asyncio.create_task(serve_connection(hub, s2.receive, s2.send))
    await settle()
    check("both connected and got hello", s1.types() == ["hello"] and s2.types() == ["hello"] and len(hub.clients) == 2)
    await s1.inbox.put(json.dumps({"action": "subscribe", "symbols": ["BTCUSDT"]}))
    await s2.inbox.put(json.dumps({"action": "subscribe", "symbols": ["BTCUSDT", "EURUSD"]}))
    await settle()
    hub.publish(tick(price=64000.0, ts=NOW_MS))
    hub.publish(tick("EURUSD", 1.08, ts=NOW_MS, mock=True, source="mock-poll"))
    await settle()
    check("subscribers receive their ticks over the socket", len(s1.ticks("BTCUSDT")) == 1 and len(s1.ticks("EURUSD")) == 0 and len(s2.ticks()) == 2)
    await s1.inbox.put(None)
    res1 = await asyncio.wait_for(t1, 2)
    check("a disconnect ends the session cleanly and frees the client", res1 == (1000, "") and len(hub.clients) == 1)
    hub.publish(tick(price=64010.0, ts=NOW_MS + 1))
    await settle()
    check("the other client keeps receiving", len(s2.ticks("BTCUSDT")) == 2)
    await s2.inbox.put(None)
    await asyncio.wait_for(t2, 2)
    check("no tasks are left running after both disconnect", len([t for t in asyncio.all_tasks() if t is not asyncio.current_task()]) == 0)

    hub = make_hub(rate_limit_messages=3)
    s = FakeSocket()
    t = asyncio.create_task(serve_connection(hub, s.receive, s.send))
    await settle()
    for _ in range(4):
        await s.inbox.put('{"action":"ping"}')
    code, reason = await asyncio.wait_for(t, 3)
    check("rate limit ends the session with 1008", code == 1008 and reason == "rate limited")
    check("the final error message was flushed before closing", "error" in s.types() and s.sent[-1].get("code") == "rate_limited", str(s.types()))

    hub = make_hub(max_clients=1)
    s = FakeSocket()
    t = asyncio.create_task(serve_connection(hub, s.receive, s.send))
    await settle()
    s_full = FakeSocket()
    res = await serve_connection(hub, s_full.receive, s_full.send)
    check("a connection over the limit is closed with 1013 and nothing is sent", res == (1013, "server full") and not s_full.sent)
    await s.inbox.put(None)
    await asyncio.wait_for(t, 2)

    hub = make_hub()
    dead = FakeSocket(send_fails=True)
    t = asyncio.create_task(serve_connection(hub, dead.receive, dead.send))
    await settle()
    res = await asyncio.wait_for(t, 2)
    check("a socket that fails on send ends the session and the client is removed", len(hub.clients) == 0)
    check("no tasks left after the failed send", len([x for x in asyncio.all_tasks() if x is not asyncio.current_task()]) == 0)

    hub = make_hub(send_timeout_s=0.1)
    stuck, fast = FakeSocket(send_delay=5.0), FakeSocket()
    ts_ = asyncio.create_task(serve_connection(hub, stuck.receive, stuck.send))
    tf = asyncio.create_task(serve_connection(hub, fast.receive, fast.send))
    await settle()
    await fast.inbox.put(json.dumps({"action": "subscribe", "symbols": ["BTCUSDT"]}))
    await settle()
    hub.publish(tick(ts=NOW_MS))
    await settle()
    got_first = len(fast.ticks()) == 1
    res = await asyncio.wait_for(ts_, 3)
    check("a client whose socket hangs is dropped after the send timeout (1011)", res[0] == 1011 and hub.stats["clients_closed_slow"] == 1)
    hub.publish(tick(ts=NOW_MS + 1, price=64005.0))
    await settle()
    check("one stuck client never blocks the others", got_first and len(fast.ticks()) == 2)
    await fast.inbox.put(None)
    await asyncio.wait_for(tf, 2)

    hub = make_hub()
    sockets = [FakeSocket() for _ in range(50)]
    sessions = [asyncio.create_task(serve_connection(hub, s.receive, s.send)) for s in sockets]
    await settle()
    for s in sockets:
        await s.inbox.put(json.dumps({"action": "subscribe", "symbols": ["BTCUSDT"]}))
    await settle()
    for i in range(200):
        hub.publish(tick(price=60000 + i, ts=NOW_MS + i))
        if i % 7 == 0:
            await asyncio.sleep(0)
    await settle(0.2)
    ok_last = all(s.ticks()[-1]["price"] == 60199 for s in sockets)
    ok_order = all([m["seq"] for m in s.ticks()] == sorted({m["seq"] for m in s.ticks()}) for s in sockets)
    check("50 clients, 200 ticks: every client ends on the newest price", ok_last)
    check("and each client saw strictly increasing sequence numbers", ok_order)
    for s in sockets:
        await s.inbox.put(None)
    await asyncio.gather(*sessions)
    check("all 50 sessions cleaned up", len(hub.clients) == 0)


async def test_poller():
    print("poller: fetch -> tick, subscriber-only polling, failure isolation")
    hub = make_hub()
    calls = []
    fail = {"XAUUSD": False}

    def fetch(symbol):
        calls.append(symbol)
        if symbol == "XAUUSD" and fail["XAUUSD"]:
            raise RuntimeError("https://secret.example/?key=abc123 refused")
        return {"symbol": symbol, "price": 100.0 + len(calls), "change_percent_24h": 0.5, "source": "mock" if symbol != "BTCUSDT" else "binance", "mock": symbol != "BTCUSDT", "timestamp": NOW_MS + len(calls)}

    async def fake_sleep(s):
        delays.append(s)
        if len(delays) >= 6:
            raise asyncio.CancelledError()

    delays = []
    poller = PollingTicker(hub, fetch, ("BTCUSDT", "XAUUSD", "EURUSD"), 5.0, sleep=fake_sleep)
    a, f = await poller.poll_once()
    check("nobody subscribed: nothing is fetched (no Binance calls while idle)", (a, f) == (0, 0) and calls == [])
    c = hub.add_client()
    drain(c)
    send(hub, c, {"action": "subscribe", "symbols": ["BTCUSDT", "XAUUSD"]})
    drain(c)
    a, f = await poller.poll_once()
    check("only subscribed symbols are fetched", calls == ["BTCUSDT", "XAUUSD"] and (a, f) == (2, 0))
    got = {m["symbol"]: m for m in drain_pending(c)}
    check("source and mock flag pass through (gold stays labelled mock)", got["BTCUSDT"]["source"] == "binance-poll" and got["BTCUSDT"]["mock"] is False and got["XAUUSD"]["source"] == "mock-poll" and got["XAUUSD"]["mock"] is True)
    check("tick_from_price maps the REST price fields", tick_from_price({"symbol": "BTCUSDT", "price": 1.0, "timestamp": 5, "source": "binance", "mock": False})["ts"] == 5)
    fail["XAUUSD"] = True
    a, f = await poller.poll_once()
    check("one failing symbol does not stop the other", (a, f) == (2, 1) and poller.failures == {"BTCUSDT": 0, "XAUUSD": 1, "EURUSD": 0} and len(drain_pending(c)) == 1)
    check("the error type is kept, the message (with a secret-looking URL) is not", poller.last_error_type == {"XAUUSD": "RuntimeError"} and "secret" not in json.dumps(hub.status()))
    check("poller state is visible in the hub status", hub.status()["meta"]["poller"]["consecutive_failures"]["XAUUSD"] == 1)
    check("delay stays normal when only some symbols fail", poller.next_delay(2, 1) == 5.0)

    hub2 = make_hub()
    c2 = hub2.add_client()
    drain(c2)
    send(hub2, c2, {"action": "subscribe", "symbols": ["XAUUSD"]})

    def always_fail(symbol):
        raise OSError("down")

    delays = []
    p2 = PollingTicker(hub2, always_fail, ("XAUUSD",), 5.0, sleep=fake_sleep)
    try:
        await p2.run()
    except asyncio.CancelledError:
        pass
    check("when everything fails the delay backs off 10, 20, 40, 60, 60, 60", delays == [10.0, 20.0, 40.0, 60.0, 60.0, 60.0], str(delays))

    good = {"n": 0}

    def flaky(symbol):
        good["n"] += 1
        if good["n"] <= 2:
            raise OSError("down")
        return {"symbol": symbol, "price": 5.0, "source": "mock", "mock": True, "timestamp": NOW_MS + good["n"]}

    p3 = PollingTicker(hub2, flaky, ("XAUUSD",), 5.0, sleep=fake_sleep)
    for _ in range(3):
        await p3.poll_once()
    check("a success resets the failure counter", p3.failures["XAUUSD"] == 0 and p3.next_delay(1, 0) == 5.0)

    out_hub = make_hub()
    out_hub.publish(tick("XAUUSD", 1.0, ts=NOW_MS + 100, mock=True, source="mock-poll"))
    c4 = out_hub.add_client()
    send(out_hub, c4, {"action": "subscribe", "symbols": ["XAUUSD"]})
    p4 = PollingTicker(out_hub, lambda s: {"symbol": s, "price": 2.0, "source": "mock", "mock": True, "timestamp": NOW_MS}, ("XAUUSD",), 5.0)
    a, f = await p4.poll_once()
    check("an out-of-order tick from the source counts as a failed poll", (a, f) == (1, 1) and out_hub.rejected["out_of_order"] == 1)

    run_hub = make_hub()
    p5 = PollingTicker(run_hub, fetch, ("BTCUSDT",), 5.0)
    task = asyncio.create_task(p5.run())
    await settle()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    check("run() can be cancelled (server shutdown)", task.cancelled())


def test_static():
    print("static: purity and wiring")
    for name in ("services/ws_hub.py", "services/tick_poller.py"):
        src = (ROOT / name).read_text()
        imports = set(re.findall(r"^(?:from|import)\s+([\w\.]+)", src, re.M))
        allowed = {"asyncio", "json", "logging", "math", "time", "collections", "dataclasses"}
        check(f"{name} imports only the standard library", imports <= allowed, str(sorted(imports - allowed)))
        check(f"{name} has no database or ledger access", not re.search(r"paper_(?!tick)|sqlalchemy|session|\.execute\(", src))
    for name in ("services/ws_hub.py", "services/tick_poller.py", "routers/ws.py", "main.py", "config.py"):
        try:
            py_compile.compile(str(ROOT / name), doraise=True)
            ok = True
        except py_compile.PyCompileError as exc:
            ok = False
            print(exc)
        check(f"{name} compiles", ok)
    main_src = (ROOT / "main.py").read_text()
    check("main.py includes the ws router and the lifespan", "ws_router.router" in main_src and "lifespan=lifespan" in main_src)
    ws_src = (ROOT / "routers/ws.py").read_text()
    check("the endpoint checks Origin before accepting", ws_src.index("origin_allowed") < ws_src.index("ws.accept()"))
    check("the router has the socket route and the status route", '"/ws/prices"' in ws_src and '"/ws/status"' in ws_src)
    check("the server only reads text from clients and never evals them", "eval(" not in (ROOT / "services/ws_hub.py").read_text())


def main():
    test_protocol()
    test_publish()
    test_conflation_and_snapshot()
    test_limits()
    asyncio.run(test_connections())
    asyncio.run(test_poller())
    test_static()
    print(f"\n{results['passed']} passed, {results['failed']} failed")
    raise SystemExit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main()
