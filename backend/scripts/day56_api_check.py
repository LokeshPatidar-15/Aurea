import sys

import requests

BASE = "http://127.0.0.1:8010"
results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


try:
    requests.get(BASE + "/", timeout=3)
except requests.RequestException:
    print(f"backend not reachable at {BASE}. Start it: uvicorn main:app --reload --port 8010")
    sys.exit(1)

FIELDS = {"symbol", "timeframe", "strategy", "status", "reason", "side", "as_of", "reference_price", "stop_price", "rr", "risk_atr", "atr",
          "data_age_minutes", "stale", "conditions", "research_only", "note"}
print("strategy signal endpoint")
for symbol in ("BTCUSDT", "XAUUSD", "EURUSD"):
    r = requests.get(f"{BASE}/strategy/signal/{symbol}", timeout=60)
    ok = r.status_code == 200
    check(f"GET /strategy/signal/{symbol} returns 200", ok, r.text[:150] if not ok else "")
    if ok:
        body = r.json()
        print(f"  info: {symbol:8} status={body['status']} reason={body['reason']} trend={body['conditions']['trend']} as_of={body['as_of']} age={body['data_age_minutes']} min")
        check(f"{symbol} response has every documented field", FIELDS <= set(body))
        check(f"{symbol} is flagged research_only", body["research_only"] is True)
        check(f"{symbol} signal fields are consistent", (body["status"] == "signal") == (body["side"] != "none") and (body["status"] == "signal") == (body["stop_price"] is not None))
check("lowercase symbol works", requests.get(BASE + "/strategy/signal/btcusdt", timeout=60).status_code == 200)
check("unknown symbol gives 404", requests.get(BASE + "/strategy/signal/DOGEUSDT", timeout=30).status_code == 404)
check("unsupported timeframe gives 422", requests.get(BASE + "/strategy/signal/BTCUSDT?timeframe=15m", timeout=30).status_code == 422)

print("one loop cycle (signals only, no orders)")
before = len(requests.get(BASE + "/paper/positions?limit=500", timeout=30).json())
r = requests.post(BASE + "/loop/run?place_orders=false", timeout=180)
check("POST /loop/run returns 200", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")
if r.status_code != 200:
    sys.exit(1)
cycle = r.json()
print(f"  info: ingest {cycle['ingest']}")
print(f"  info: tick {cycle['tick']}")
for symbol, entry in cycle["symbols"].items():
    print(f"  info: {symbol:8} signal={entry['signal']} action={entry['action']} why={entry['why']}")
check("all three symbols were processed", set(cycle["symbols"]) == {"BTCUSDT", "XAUUSD", "EURUSD"})
check("ingest had no errors", cycle["ingest"] is not None and all("error" not in v for v in cycle["ingest"].values()), str(cycle["errors"]))
check("tick ran", cycle["tick"] is not None and "processed_candles" in cycle["tick"])
check("no cycle error", cycle["errors"] == [], "; ".join(cycle["errors"]))
check("orders disabled means no new ledger rows", len(requests.get(BASE + "/paper/positions?limit=500", timeout=30).json()) == before)
r = requests.post(BASE + "/loop/run?place_orders=false", timeout=180)
second = r.json() if r.status_code == 200 else {"ingest": {}}
check("second cycle inserts no duplicate candles", r.status_code == 200 and all(v.get("inserted", 1) == 0 for v in second["ingest"].values()), str(second["ingest"]))
check("GET /loop/last returns the latest cycle", requests.get(BASE + "/loop/last", timeout=30).status_code == 200)

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
