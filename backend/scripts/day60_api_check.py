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

print("conditions catalog")
r = requests.get(BASE + "/strategy/conditions", timeout=30)
check("GET /strategy/conditions returns 200", r.status_code == 200)
names = [c["name"] for c in r.json()]
check("14 conditions with descriptions", len(names) == 14 and all(c["description"] for c in r.json()), f"{len(names)}")
check("the catalog includes the sweep and pattern conditions", {"sweep_bull", "bullish_engulfing", "inside_bar", "trend_up"} <= set(names))

print("patterns per symbol")
for symbol in ("BTCUSDT", "XAUUSD", "EURUSD"):
    r = requests.get(f"{BASE}/strategy/patterns/{symbol}", timeout=60)
    if r.status_code == 503:
        print(f"  SKIP {symbol}: {r.json()['detail']}")
        continue
    check(f"{symbol} returns 200", r.status_code == 200, r.text[:150] if r.status_code != 200 else "")
    body = r.json()
    print(f"  info: as_of {body['as_of']} stale={body['stale']} latest={[k for k, v in body['latest'].items() if v]} recent hits={len(body['recent'])}")
    check(f"{symbol} reports all five patterns", set(body["latest"]) == {"bullish_engulfing", "bearish_engulfing", "bullish_pin", "bearish_pin", "inside_bar"})
    check(f"{symbol} is research only", body["research_only"] is True)
    s = requests.get(f"{BASE}/strategy/signal/{symbol}", timeout=60)
    if s.status_code == 200 and s.json()["as_of"] == body["as_of"]:
        c = s.json()["conditions"]
        check(f"{symbol} sweep flags match /strategy/signal", c["sweep_bull"] == body["sweep"]["sweep_bull"] and c["sweep_bear"] == body["sweep"]["sweep_bear"])
    else:
        print(f"  info: {symbol} sweep cross-check skipped (different as_of)")

print("input checks")
check("unknown symbol gives 404", requests.get(BASE + "/strategy/patterns/DOGEUSDT", timeout=30).status_code == 404)
check("unknown timeframe gives 422", requests.get(BASE + "/strategy/patterns/BTCUSDT?timeframe=5m", timeout=30).status_code == 422)

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
