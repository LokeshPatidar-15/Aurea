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

print("templates")
r = requests.get(BASE + "/strategy/templates", timeout=30)
check("GET /strategy/templates returns 200 with 5 templates", r.status_code == 200 and len(r.json()) == 5)
templates = r.json()
check("each template has words for the long rule and an evidence line", all(t["long_text"] and t["evidence"] for t in templates))
r = requests.get(BASE + "/strategy/templates/sweep_reversal", timeout=30)
check("GET one template returns 200", r.status_code == 200 and r.json()["strategy"]["name"] == "sweep_reversal")
check("unknown template gives 404", requests.get(BASE + "/strategy/templates/nope", timeout=30).status_code == 404)

print("validate")
good = {"strategy": {"name": "api test", "long": {"all": ["bullish_engulfing", {"any": ["trend_up", "volume_high"]}]}}}
r = requests.post(BASE + "/strategy/validate", json=good, timeout=30)
check("a good strategy is valid and explained", r.status_code == 200 and r.json()["valid"] and r.json()["long_text"] == "(bullish_engulfing AND (trend_up OR volume_high))")
r = requests.post(BASE + "/strategy/validate", json={"strategy": {"long": "__import__('os').system('ls')"}}, timeout=30)
check("code in a condition is refused, not executed", r.status_code == 200 and r.json()["valid"] is False and "unknown condition" in r.json()["errors"][0])
r = requests.post(BASE + "/strategy/validate", json={"strategy": {"long": "trend_up", "leverage": 50}}, timeout=30)
check("an unknown field is refused", r.json()["valid"] is False and "leverage" in r.json()["errors"][0])
check("a body without strategy gives 422", requests.post(BASE + "/strategy/validate", json={}, timeout=30).status_code == 422)
check("a strategy that is not an object gives 422", requests.post(BASE + "/strategy/validate", json={"strategy": "trend_up"}, timeout=30).status_code == 422)
deep = "trend_up"
for _ in range(60):
    deep = {"not": deep}
r = requests.post(BASE + "/strategy/validate", json={"strategy": {"long": deep}}, timeout=30)
check("a 60-level deep rule is refused politely", r.status_code == 200 and r.json()["valid"] is False)

print("preview")
for symbol in ("BTCUSDT", "XAUUSD", "EURUSD"):
    r = requests.post(f"{BASE}/strategy/preview/{symbol}", json={"strategy": templates[0]["strategy"]}, timeout=60)
    if r.status_code == 503:
        print(f"  SKIP {symbol}: {r.json()['detail']}")
        continue
    check(f"{symbol} preview returns 200", r.status_code == 200, r.text[:150] if r.status_code != 200 else "")
    body = r.json()
    print(f"  info: {symbol} {body['status']}/{body['reason']} as_of {body['as_of']} signals in window {body['signals_in_window']}/{body['window_candles']}")
    s = requests.get(f"{BASE}/strategy/signal/{symbol}", timeout=60)
    if s.status_code == 200 and s.json()["as_of"] == body["as_of"]:
        check(f"{symbol} sweep_reversal preview equals /strategy/signal", (s.json()["status"], s.json()["side"], s.json()["reason"]) == (body["status"], body["side"], body["reason"]))
    for t in templates[1:]:
        rr = requests.post(f"{BASE}/strategy/preview/{symbol}", json={"strategy": t["strategy"]}, timeout=60)
        if rr.status_code != 200:
            check(f"{symbol} {t['id']} preview", False, rr.text[:100])
    print(f"  info: {symbol} all 5 templates previewed")
r = requests.post(BASE + "/strategy/preview/BTCUSDT", json={"strategy": {"long": "moon_phase"}}, timeout=30)
check("previewing an invalid strategy gives 422 with the reason", r.status_code == 422 and "unknown condition" in r.json()["detail"])
check("unknown symbol gives 404", requests.post(BASE + "/strategy/preview/DOGEUSDT", json=good, timeout=30).status_code == 404)
check("unknown timeframe gives 422", requests.post(BASE + "/strategy/preview/BTCUSDT?timeframe=5m", json=good, timeout=30).status_code == 422)

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
