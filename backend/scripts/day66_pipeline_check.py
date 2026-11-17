import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.request

SYMBOLS = ["BTCUSDT", "XAUUSD", "EURUSD"]
results = {"passed": 0, "failed": 0}


def check(name, ok, detail=""):
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def http(base, path, method="GET"):
    req = urllib.request.Request(base + path, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode()), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            body = {}
        return exc.code, body, dict(exc.headers)


async def collect(ws, seconds, want=None):
    out = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.monotonic()))
        except asyncio.TimeoutError:
            break
        msg = json.loads(raw)
        out.append(msg)
        if want and want(out):
            break
    return out


async def main_async(args):
    import websockets

    base = f"http://{args.host}:{args.port}"
    ws_url = f"ws://{args.host}:{args.port}/ws/prices"

    print("pipeline status")
    code, status, _ = http(base, "/pipeline/status")
    check("GET /pipeline/status answers 200", code == 200, str(code))
    check("the scheduler is enabled and orders are off", status.get("scheduler_enabled") is True and status.get("place_orders") is False, json.dumps({k: status.get(k) for k in ("scheduler_enabled", "place_orders")}))
    waited = 0
    while not status.get("last_summary") and waited < 90:
        await asyncio.sleep(3)
        waited += 3
        code, status, _ = http(base, "/pipeline/status")
    check("the warm-up run finished", bool(status.get("last_summary")), f"waited {waited}s")

    print("websocket: cached signals")
    async with websockets.connect(ws_url) as ws:
        hello = json.loads(await ws.recv())
        check("hello lists the signal and paper_tick events", "signal" in hello.get("events", []) and "paper_tick" in hello.get("events", []))
        await ws.send(json.dumps({"action": "subscribe", "symbols": SYMBOLS}))
        msgs = await collect(ws, 6, want=lambda m: len([x for x in m if x.get("type") == "signal"]) >= 3)
        sigs = {m["symbol"]: m for m in msgs if m.get("type") == "signal"}
        check("one cached signal per symbol arrives right after subscribing", set(sigs) == set(SYMBOLS), str(sorted(sigs)))
        btc = sigs.get("BTCUSDT", {})
        check("signal shape: research_only, calibrated false, 1h", btc.get("research_only") is True and btc.get("timeframe") == "1h" and (btc.get("model") or {}).get("calibrated") in (False, None))
        raw = json.dumps(msgs).lower()
        check("nothing pushed contains equity, pnl or balance", not any(w in raw for w in ("equity", "pnl", "balance")))

        print("parity with the REST endpoints")
        code, rest_rule, _ = http(base, "/strategy/signal/BTCUSDT")
        if code == 200 and btc.get("rule"):
            check("pushed rule status matches REST", btc["rule"]["status"] == rest_rule.get("status"), f"{btc['rule']['status']} vs {rest_rule.get('status')}")
            check("pushed rule side matches REST", btc["rule"]["side"] == rest_rule.get("side"))
        else:
            check("REST rule signal reachable and pushed rule present", False, f"http {code}, rule={bool(btc.get('rule'))}")
        code, rest_model, _ = http(base, "/predict/BTCUSDT?model=xgboost")
        if code == 200 and btc.get("model"):
            check("pushed model signal matches REST", btc["model"]["signal"] == rest_model.get("signal"), f"{btc['model']['signal']} vs {rest_model.get('signal')}")
        else:
            check("model signal pushed or model_error reported (artifact may be missing)", bool(btc.get("model_error")), f"http {code}")

        print("manual refresh")
        before = max((m.get("seq", 0) for m in msgs if m.get("type") == "signal"), default=0)
        code, body, _ = http(base, "/pipeline/run?mode=refresh", "POST")
        check("POST /pipeline/run?mode=refresh answers 200", code == 200, str(code))
        more = await collect(ws, 8, want=lambda m: len([x for x in m if x.get("type") == "signal"]) >= 3)
        new = [m for m in more if m.get("type") == "signal"]
        check("a new signal per symbol is pushed with a higher seq", len(new) >= 3 and min(m["seq"] for m in new) > before, str(len(new)))
        code, _, headers = http(base, "/pipeline/run?mode=refresh", "POST")
        check("an immediate second call is rate limited (429 + Retry-After)", code == 429 and any(k.lower() == "retry-after" for k in headers), str(code))

        if args.full:
            print("full cycle (ingest + paper tick)")
            code, before_pos, _ = http(base, "/paper/positions")
            n_before = len(before_pos if isinstance(before_pos, list) else before_pos.get("positions", []))
            await asyncio.sleep(max(0, 31 - 0))
            code, body, _ = http(base, "/pipeline/run?mode=full", "POST")
            check("POST /pipeline/run?mode=full answers 200", code == 200, str(code))
            more = await collect(ws, 10, want=lambda m: any(x.get("type") == "paper_tick" for x in m))
            ticks = [m for m in more if m.get("type") == "paper_tick"]
            check("a counts-only paper_tick arrives", len(ticks) == 1 and "equity" not in json.dumps(ticks[0]))
            code, after_pos, _ = http(base, "/paper/positions")
            n_after = len(after_pos if isinstance(after_pos, list) else after_pos.get("positions", []))
            check("no new orders were placed (pipeline_place_orders is false)", ticks and ticks[0]["orders_placed"] == 0, f"positions {n_before} -> {n_after}")

    print("regression")
    for path in ("/health/db", "/ws/status", "/strategy/signal/BTCUSDT", "/paper/summary"):
        code, _, _ = http(base, path)
        check(f"GET {path} still answers", code == 200, str(code))

    print(f"\n{results['passed']} passed, {results['failed']} failed")
    return 1 if results["failed"] else 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    parser.add_argument("--full", action="store_true")
    sys.exit(asyncio.run(main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
