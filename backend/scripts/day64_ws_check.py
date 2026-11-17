import asyncio
import json
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
results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


async def recv(ws, timeout=15.0):
    return json.loads(await asyncio.wait_for(ws.recv(), timeout))


async def collect(ws, kind, count, timeout, symbol=None):
    got = []
    end = time.monotonic() + timeout
    while len(got) < count and time.monotonic() < end:
        try:
            msg = await recv(ws, max(0.1, end - time.monotonic()))
        except asyncio.TimeoutError:
            break
        if msg.get("type") == kind and (symbol is None or msg.get("symbol") == symbol):
            got.append(msg)
    return got


def close_code(exc):
    rcvd = getattr(exc, "rcvd", None)
    return getattr(rcvd, "code", None) if rcvd else getattr(exc, "code", None)


async def main():
    try:
        requests.get(HTTP + "/", timeout=3)
    except requests.RequestException:
        print(f"backend not reachable at {HTTP}. Start it: uvicorn main:app --reload --port 8010")
        return

    print("status before any client")
    st = requests.get(HTTP + "/ws/status", timeout=10)
    check("GET /ws/status returns 200", st.status_code == 200, st.text[:150] if st.status_code != 200 else "")
    st0 = st.json()
    poll = float(st0["meta"].get("poll_seconds", 5))
    check("the poller is on (poll_seconds > 0)", poll > 0, f"poll_seconds={poll}")
    base_clients = st0["clients"]
    published0 = st0["counters"].get("ticks_published", 0)

    print("handshake and subscribe")
    async with websockets.connect(WS) as ws:
        hello = await recv(ws)
        check("first message is hello with protocol 1 and the 3 symbols", hello["type"] == "hello" and hello["protocol"] == 1 and hello["symbols"] == ["BTCUSDT", "XAUUSD", "EURUSD"], str(hello)[:150])
        await ws.send(json.dumps({"action": "subscribe", "symbols": ["BTCUSDT"]}))
        sub = await recv(ws)
        check("subscribe is confirmed", sub == {"type": "subscribed", "symbols": ["BTCUSDT"]}, str(sub))
        ticks = await collect(ws, "tick", 3, poll * 3 + 10, "BTCUSDT")
        check("3 BTC ticks arrive", len(ticks) == 3, f"got {len(ticks)} in about {poll * 3 + 10:.0f}s max")
        if ticks:
            check("ticks are well formed and not mock", all(t["symbol"] == "BTCUSDT" and t["price"] > 0 and t["mock"] is False and t["source"].startswith("binance") for t in ticks), str(ticks[0]))
            check("seq and ts never go backwards", all(b["seq"] > a["seq"] and b["ts"] >= a["ts"] for a, b in zip(ticks, ticks[1:])))
            print(f"  info: first tick {ticks[0]['price']} at seq {ticks[0]['seq']}, gap between ticks about {(ticks[-1]['ts'] - ticks[0]['ts']) / max(1, len(ticks) - 1) / 1000:.1f}s")
            rest = requests.get(HTTP + "/prices/BTCUSDT", timeout=15).json()["price"]
            check("tick price is within 0.5% of /prices/BTCUSDT", abs(ticks[-1]["price"] - rest) / rest < 0.005, f"tick {ticks[-1]['price']} vs rest {rest}")
            lag = (ticks[-1]["server_time"] - ticks[-1]["ts"]) / 1000
            check("server_time minus ts is small (under 5 s)", 0 <= lag < 5, f"{lag:.2f}s")

        print("gold and euro are still demo ticks")
        await ws.send(json.dumps({"action": "subscribe", "symbols": ["XAUUSD", "EURUSD"]}))
        demo = await collect(ws, "tick", 4, poll * 2 + 10)
        xau = [t for t in demo if t["symbol"] == "XAUUSD"]
        check("XAUUSD ticks arrive, real data via the PAXG proxy, flagged proxy=true", bool(xau) and all(t["mock"] is False and t.get("proxy") is True for t in xau))
        print("  info: since Day 65 gold and euro ticks come from the PAXGUSDT and EURUSDT proxies (flagged proxy=true).")

        print("protocol errors keep the connection open")
        await ws.send("not json")
        await ws.send(json.dumps({"action": "subscribe", "symbols": ["DOGE"]}))
        await ws.send(json.dumps({"action": "buy"}))
        await ws.send("x" * 2000)
        await ws.send(b"\x00\x01")
        codes = []
        while len(codes) < 5:
            msg = await recv(ws, 5)
            if msg["type"] == "error":
                codes.append(msg["code"])
        check("5 bad messages give 5 matching error codes", codes == ["invalid_json", "unknown_symbol", "unknown_action", "message_too_large", "text_only"], str(codes))
        await ws.send(json.dumps({"action": "ping"}))
        pong = None
        for _ in range(20):
            msg = await recv(ws, 5)
            if msg["type"] == "pong":
                pong = msg
                break
        check("the connection is still alive: ping gets a pong", pong is not None)

        print("two clients, one stream")
        async with websockets.connect(WS) as ws2:
            await recv(ws2)
            await ws2.send(json.dumps({"action": "subscribe", "symbols": ["BTCUSDT"]}))
            st = requests.get(HTTP + "/ws/status", timeout=10).json()
            check("status shows both clients", st["clients"] == base_clients + 2, f"clients={st['clients']}")
            a = await collect(ws, "tick", 2, poll * 3 + 10, "BTCUSDT")
            b = await collect(ws2, "tick", 2, poll * 3 + 10, "BTCUSDT")
            seqs_a = {t["seq"] for t in a if t["symbol"] == "BTCUSDT"}
            seqs_b = {t["seq"] for t in b if t["symbol"] == "BTCUSDT"}
            check("both clients receive the same ticks (shared sequence numbers)", bool(seqs_a & seqs_b), f"{sorted(seqs_a)} vs {sorted(seqs_b)}")

        print("unsubscribe")
        await ws.send(json.dumps({"action": "unsubscribe", "symbols": ["BTCUSDT", "XAUUSD", "EURUSD"]}))
        end_conf = None
        for _ in range(30):
            msg = await recv(ws, 10)
            if msg["type"] == "subscribed" and msg["symbols"] == []:
                end_conf = msg
                break
        check("unsubscribe confirms an empty list", end_conf is not None)
        late = await collect(ws, "tick", 1, poll + 3)
        check("no ticks after unsubscribing", len(late) == 0, f"{len(late)} ticks")

        print("rate limit")
        async with websockets.connect(WS) as spam:
            closed = None
            try:
                for _ in range(60):
                    await spam.send(json.dumps({"action": "ping"}))
                for _ in range(200):
                    await asyncio.wait_for(spam.recv(), 5)
            except websockets.exceptions.ConnectionClosed as exc:
                closed = close_code(exc)
            except asyncio.TimeoutError:
                pass
            check("60 pings in a burst get the client closed with 1008", closed == 1008, f"close code {closed}")

    print("origin check")
    try:
        async with websockets.connect(WS, origin="http://evil.example"):
            check("a foreign Origin is refused at the handshake", False, "connection was accepted")
    except websockets.exceptions.InvalidHandshake as exc:
        check("a foreign Origin is refused at the handshake", True, type(exc).__name__)
    except OSError as exc:
        check("a foreign Origin is refused at the handshake", False, str(exc))
    try:
        async with websockets.connect(WS, origin="http://localhost:5173") as okws:
            first = await recv(okws, 5)
            check("the frontend origin (localhost:5173) is accepted", first["type"] == "hello")
    except Exception as exc:
        check("the frontend origin (localhost:5173) is accepted", False, repr(exc)[:150])

    print("cleanup and idle cost")
    await asyncio.sleep(1.0)
    st = requests.get(HTTP + "/ws/status", timeout=10).json()
    check("all test clients are gone from the hub", st["clients"] == base_clients, f"clients={st['clients']}, before={base_clients}")
    published_now = st["counters"].get("ticks_published", 0)
    await asyncio.sleep(poll + 3)
    st2 = requests.get(HTTP + "/ws/status", timeout=10).json()
    print("  info: since Day 65 the exchange feed stays open for a grace period after the last client leaves, so the idle check moved to day65_ws_check.py")
    check("ticks were published during this run", published_now > published0, f"{published0} -> {published_now}")
    print("  rejected ticks by reason: " + (json.dumps(st2["ticks_rejected"]) if st2["ticks_rejected"] else "none"))
    print("  poller: " + json.dumps(st2["meta"].get("poller", {})))

    print("regression")
    check("GET / still works", requests.get(HTTP + "/", timeout=5).status_code == 200)
    check("GET /prices/BTCUSDT still works", requests.get(HTTP + "/prices/BTCUSDT", timeout=15).status_code == 200)
    check("GET /paper/summary still works", requests.get(HTTP + "/paper/summary", timeout=30).status_code == 200)


asyncio.run(main())
print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
