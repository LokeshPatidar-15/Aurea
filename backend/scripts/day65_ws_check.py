import asyncio
import json
import statistics
import sys
import time

import requests

try:
    import websockets
except ImportError:
    print("the websockets package is missing. Run: pip install websockets")
    sys.exit(1)

HTTP = "http://127.0.0.1:8010"
WS = "ws://127.0.0.1:8010/ws/prices"
BINANCE = "https://api.binance.com/api/v3"
FEED = {"BTCUSDT": "BTCUSDT", "XAUUSD": "PAXGUSDT", "EURUSD": "EURUSDT"}
TOLERANCE = {"BTCUSDT": 0.003, "XAUUSD": 0.005, "EURUSD": 0.002}
SANE = {"BTCUSDT": (1_000, 1_000_000), "XAUUSD": (500, 20_000), "EURUSD": (0.5, 2.0)}
REST_ONLY = "--rest-only" in sys.argv
SLOW = "--slow" in sys.argv
IDLE_GRACE = 60
for arg in sys.argv:
    if arg.startswith("--idle-grace="):
        IDLE_GRACE = float(arg.split("=", 1)[1])
results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def exchange_price(feed_symbol: str) -> float:
    r = requests.get(f"{BINANCE}/ticker/price", params={"symbol": feed_symbol}, timeout=10)
    r.raise_for_status()
    return float(r.json()["price"])


async def main():
    try:
        requests.get(HTTP + "/", timeout=3)
    except requests.RequestException:
        print(f"backend not reachable at {HTTP}. Start it: uvicorn main:app --reload --port 8010")
        return
    mode = "REST only (WS_FEED_ENABLED=false)" if REST_ONLY else "WebSocket feed with REST fallback"
    print(f"mode: {mode}")

    print("status before any client")
    st0 = requests.get(HTTP + "/ws/status", timeout=10).json()
    has_feed = "feed" in st0["meta"]
    if REST_ONLY:
        check("the feed is switched off in this mode", not has_feed, "start uvicorn with WS_FEED_ENABLED=false for --rest-only")
    else:
        check("/ws/status reports the market feed", has_feed, "meta keys: " + ", ".join(st0["meta"]))
        if has_feed:
            print(f"  info: feed state before the first client: {st0['meta']['feed']['state']}, host {st0['meta']['feed']['host']}")

    print("subscribe to all three symbols and watch for 15 seconds")
    ticks = {s: [] for s in FEED}
    async with websockets.connect(WS) as ws:
        hello = json.loads(await asyncio.wait_for(ws.recv(), 10))
        check("hello lists gold and euro as proxies of PAXGUSDT and EURUSDT", hello.get("proxies") == {"XAUUSD": "PAXGUSDT", "EURUSD": "EURUSDT"}, str(hello.get("proxies")))
        await ws.send(json.dumps({"action": "subscribe", "symbols": list(FEED)}))
        end = time.monotonic() + 15
        errors = []
        while time.monotonic() < end:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), max(0.1, end - time.monotonic())))
            except asyncio.TimeoutError:
                break
            if msg["type"] == "tick":
                ticks[msg["symbol"]].append(msg)
            elif msg["type"] == "error":
                errors.append(msg)
        check("no protocol errors", not errors, str(errors[:1]))

        total = {s: len(v) for s, v in ticks.items()}
        print(f"  info: ticks in 15 s: {total}")
        need = {"BTCUSDT": 1 if REST_ONLY else 4, "XAUUSD": 1, "EURUSD": 1}
        for s in FEED:
            check(f"{s}: at least {need[s]} ticks arrived", total[s] >= need[s], f"got {total[s]}")
        if not REST_ONLY:
            sparse = [s for s in FEED if 1 <= total[s] < 5]
            if sparse:
                print(f"  info: few ticks for {sparse}: the exchange only sends an update when something traded, quiet pairs can be sparse")

        print("tick content")
        expected_source = "binance-rest" if REST_ONLY else "binance-ws"
        for s in FEED:
            if not ticks[s]:
                continue
            t = ticks[s][-1]
            check(f"{s}: real data (mock false), source {expected_source}", all(x["mock"] is False and x["source"] in (expected_source, "binance-rest") for x in ticks[s]), f"sources {sorted({x['source'] for x in ticks[s]})}")
            check(f"{s}: proxy flag and feed symbol are right", all(x.get("proxy") is (s != "BTCUSDT") and x.get("feed_symbol") == FEED[s] for x in ticks[s]), str({k: t.get(k) for k in ("proxy", "feed_symbol")}))
            lo, hi = SANE[s]
            check(f"{s}: price is in a sane range", lo < t["price"] < hi, str(t["price"]))
            check(f"{s}: ts and seq never go backwards", all(b["ts"] >= a["ts"] and b["seq"] > a["seq"] for a, b in zip(ticks[s], ticks[s][1:])))
            ref = exchange_price(FEED[s])
            check(f"{s}: within {TOLERANCE[s] * 100:.1f}% of the exchange REST price {FEED[s]}", abs(t["price"] - ref) / ref < TOLERANCE[s], f"tick {t['price']} vs rest {ref}")
            if s == "BTCUSDT" and "change_percent_24h" in t:
                check("BTCUSDT: the 24h change is plausible (between -30 and 30 percent)", -30 < t["change_percent_24h"] < 30, f"{t['change_percent_24h']:.2f}")

        lags = [x["server_time"] - x["ts"] for s in FEED for x in ticks[s]]
        if lags and not REST_ONLY:
            med = statistics.median(lags)
            check("median delay between the exchange event time and our server time is under 3 s", -500 < med < 3000, f"{med:.0f} ms. A big negative or positive number means this computer's clock is off")

        print("feed status while the client is connected")
        st = requests.get(HTTP + "/ws/status", timeout=10).json()
        if not REST_ONLY and "feed" in st["meta"]:
            feed = st["meta"]["feed"]
            check("feed is connected and healthy", feed["state"] == "connected" and feed["healthy"] is True, json.dumps(feed)[:200])
            check("messages are flowing", feed["messages"] > 10, f"messages={feed['messages']}")
            check("the REST fallback is NOT active while the websocket is healthy", feed["rest_fallback_active"] is False)
            check("nothing was refused by the hub (no future or out-of-order timestamps)", feed["ticks_refused_by_hub"] == 0, f"refused={feed['ticks_refused_by_hub']}, hub reasons {st['ticks_rejected']}")
            check("no unparseable messages", feed["parse_rejects"] == {}, str(feed["parse_rejects"]))
            print(f"  info: reconnects so far {feed['reconnects']}, last error type {feed['last_error_type']}, last message {feed['last_message_age_s']} s ago")
        poller = st["meta"].get("poller", {})
        if not REST_ONLY:
            check("the REST poller stayed quiet (all its cycles were gated)", poller.get("cycles", 0) == 0 or poller.get("skipped_gated", 0) >= poller.get("cycles", 0) - 1, json.dumps(poller)[:200])
        print(f"  info: poller {json.dumps(poller)}")

    if SLOW and not REST_ONLY:
        wait = IDLE_GRACE + 8
        print(f"idle: waiting {wait:.0f} s with no client (idle grace {IDLE_GRACE:.0f} s)")
        await asyncio.sleep(wait)
        st = requests.get(HTTP + "/ws/status", timeout=10).json()
        check("with no clients the exchange connection is closed (state idle)", st["meta"]["feed"]["state"] == "idle", st["meta"]["feed"]["state"])
        published = st["counters"].get("ticks_published", 0)
        await asyncio.sleep(5)
        st2 = requests.get(HTTP + "/ws/status", timeout=10).json()
        check("no ticks are published while idle", st2["counters"].get("ticks_published", 0) == published)
        async with websockets.connect(WS) as ws:
            await ws.recv()
            await ws.send(json.dumps({"action": "subscribe", "symbols": ["BTCUSDT"]}))
            got = None
            end = time.monotonic() + 15
            while time.monotonic() < end:
                msg = json.loads(await asyncio.wait_for(ws.recv(), 15))
                if msg["type"] == "tick":
                    got = msg
                    break
            check("a new client after the idle period gets a live tick within 15 s", got is not None)
    elif not SLOW:
        print("  info: the idle test is skipped. Run with --slow to include it (takes about 75 s)")

    print("regression")
    check("GET / still works", requests.get(HTTP + "/", timeout=5).status_code == 200)
    check("GET /prices/BTCUSDT still works", requests.get(HTTP + "/prices/BTCUSDT", timeout=15).status_code == 200)
    check("GET /paper/summary still works", requests.get(HTTP + "/paper/summary", timeout=30).status_code == 200)
    check("GET /strategy/signal/BTCUSDT still works (200 or 503 if data is missing)", requests.get(HTTP + "/strategy/signal/BTCUSDT", timeout=60).status_code in (200, 503))


asyncio.run(main())
print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
