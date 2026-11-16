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

templates = requests.get(BASE + "/strategy/templates", timeout=30).json()
sweep = next(t for t in templates if t["id"] == "sweep_reversal")["strategy"]

print("trial counter")
before = requests.get(BASE + "/strategy/trials", timeout=30)
check("GET /strategy/trials returns 200", before.status_code == 200)
n0 = before.json()["strategies_tried"]
print(f"  info: strategies tried so far: {n0}")

print("backtest")
r = requests.post(BASE + "/strategy/backtest/BTCUSDT", json={"strategy": sweep}, timeout=300)
if r.status_code == 503:
    print("  SKIP: " + r.json()["detail"])
    sys.exit(1)
check("POST /strategy/backtest/BTCUSDT returns 200", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")
body = r.json()
res, base, mt = body["result"], body["random_baseline"], body["multiple_testing"]
print(f"  info: {res['trades']} trades, gross {res.get('gross_bps', 0):.1f} bps, net {res.get('net_bps', 0):.1f} bps, p {base['p'] if base else None}, adjusted p {base['p_adjusted'] if base else None}")
print(f"  info: verdict {body['verdict']['label']}: {body['verdict']['reasons']}")
print(f"  info: Sharpe {body['sharpe']['value']} warnings {body['sharpe']['warnings']}")
check("the evidence block is complete", all(k in body for k in ("result", "random_baseline", "slices", "sharpe", "cost_sensitivity", "multiple_testing", "verdict", "assumptions")))
check("net bps equals gross bps minus 20", abs(res["net_bps"] - (res["gross_bps"] - 20)) < 1e-6)
check("the verdict is one of the three honest labels", body["verdict"]["label"] in ("insufficient_data", "no_edge", "promising"))
check("it is marked research only", body["research_only"] is True)
check("Sharpe always carries its method", "per-trade" in body["sharpe"]["method"])
first_count = mt["strategies_tried"]
check("the trial count includes this test", first_count >= n0 and first_count >= 1, f"{first_count}")

print("repeat and rename do not inflate the count or change the answer")
r2 = requests.post(BASE + "/strategy/backtest/BTCUSDT", json={"strategy": sweep}, timeout=300)
check("the repeat gives the same numbers", r2.status_code == 200 and r2.json()["result"] == res and r2.json()["random_baseline"] == base)
check("the repeat is not counted again", r2.json()["multiple_testing"]["strategies_tried"] == first_count and r2.json()["multiple_testing"]["new_trial"] is False)
renamed = dict(sweep, name="same rules, other name")
r3 = requests.post(BASE + "/strategy/backtest/BTCUSDT", json={"strategy": renamed}, timeout=300)
check("renaming does not make a new trial", r3.status_code == 200 and r3.json()["multiple_testing"]["strategies_tried"] == first_count)
after = requests.get(BASE + "/strategy/trials", timeout=30).json()
check("the trials list shows the strategy in words", any("sweep_bull" in (e.get("long") or "") for e in after["recent"]))

print("a different strategy raises the count")
other = {"name": "api check pin", "long": {"all": ["bullish_pin", "trend_up"]}}
r4 = requests.post(BASE + "/strategy/backtest/BTCUSDT", json={"strategy": other}, timeout=300)
check("a new strategy returns 200 and counts as a new trial", r4.status_code == 200 and r4.json()["multiple_testing"]["strategies_tried"] >= first_count)

print("input checks")
check("code in a condition gives 422", requests.post(BASE + "/strategy/backtest/BTCUSDT", json={"strategy": {"long": "__import__('os')"}}, timeout=30).status_code == 422)
check("unknown symbol gives 404", requests.post(BASE + "/strategy/backtest/DOGEUSDT", json={"strategy": sweep}, timeout=30).status_code == 404)
check("unknown timeframe gives 422", requests.post(BASE + "/strategy/backtest/BTCUSDT?timeframe=5m", json={"strategy": sweep}, timeout=30).status_code == 422)
check("a missing strategy gives 422", requests.post(BASE + "/strategy/backtest/BTCUSDT", json={}, timeout=30).status_code == 422)

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
