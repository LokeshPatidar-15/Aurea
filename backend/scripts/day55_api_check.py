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

print("tradability screen")
r = requests.get(BASE + "/paper/tradability", timeout=60)
check("GET /paper/tradability returns 200", r.status_code == 200, r.text[:120] if r.status_code != 200 else "")
if r.status_code != 200:
    sys.exit(1)
rows = {row["symbol"]: row for row in r.json()}
for symbol, row in rows.items():
    print(f"  info: {symbol:8} median hourly ATR {row['atr_bps']:6.1f} bps | cost 20 bps = {row['cost_to_atr']:5.2f} ATR | tradable={row['tradable']}")
check("all three symbols are listed", set(rows) == {"BTCUSDT", "XAUUSD", "EURUSD"})
price = rows["BTCUSDT"]["last_close"]

print("placing orders")
r = requests.post(BASE + "/paper/orders", json={"symbol": "BTCUSDT", "side": "long", "stop_price": round(price * 0.98, 2)}, timeout=60)
if r.status_code == 409 and "stale_data" in str(r.json()):
    print("  SKIP: stored candles are older than 2 hours. Run: python3 -m scripts.ingest_history   then run this check again")
    sys.exit(1)
body = r.json()
check("valid long order is accepted as pending", r.status_code == 201 and body.get("status") == "pending", f"id {body.get('id')}, notional {body.get('notional')}")
order_id = body.get("id")
if r.status_code == 201:
    check("size follows the 1% risk rule", body["risk_amount"] is not None and abs(body["risk_amount"] - 100.0) < 15.0, f"risk {body['risk_amount']:.1f} on 10,000")
r2 = requests.post(BASE + "/paper/orders", json={"symbol": "BTCUSDT", "side": "long", "stop_price": round(price * 0.98, 2)}, timeout=60)
check("second order on the same symbol is rejected (409)", r2.status_code == 409 and "symbol_already_open" in str(r2.json()), str(r2.json().get("detail", {}).get("reasons")))
r3 = requests.post(BASE + "/paper/orders", json={"symbol": "XAUUSD", "side": "short", "stop_price": 1.0}, timeout=60)
check("short with the stop far below price is rejected (409)", r3.status_code == 409 and "invalid_stop" in str(r3.json()), str(r3.json().get("detail", {}).get("reasons")))
check("unknown symbol gives 404", requests.post(BASE + "/paper/orders", json={"symbol": "DOGEUSDT", "side": "long", "stop_price": 1.0}, timeout=30).status_code == 404)
check("bad side gives 422", requests.post(BASE + "/paper/orders", json={"symbol": "BTCUSDT", "side": "up", "stop_price": 1.0}, timeout=30).status_code == 422)
check("negative stop gives 422", requests.post(BASE + "/paper/orders", json={"symbol": "BTCUSDT", "side": "long", "stop_price": -5}, timeout=30).status_code == 422)

print("ledger")
r = requests.get(BASE + "/paper/positions?status=pending", timeout=30)
check("pending list contains the order", r.status_code == 200 and any(p["id"] == order_id for p in r.json()))
r = requests.get(BASE + "/paper/positions?status=rejected", timeout=30)
check("rejected orders are kept for audit", r.status_code == 200 and len(r.json()) >= 1, f"{len(r.json())} rejected so far")
r = requests.post(BASE + "/paper/tick", timeout=60)
check("POST /paper/tick returns counts", r.status_code == 200 and {"processed_candles", "filled", "closed", "rejected"} <= set(r.json()), str(r.json()))
r = requests.get(BASE + "/paper/summary", timeout=30)
check("GET /paper/summary returns equity", r.status_code == 200 and "realized_equity" in r.json(), f"equity {r.json().get('realized_equity')}")

print("cancelling")
if order_id:
    r = requests.get(BASE + "/paper/positions?limit=50", timeout=30)
    mine = next((p for p in r.json() if p["id"] == order_id), None)
    if mine and mine["status"] == "pending":
        r = requests.delete(f"{BASE}/paper/orders/{order_id}", timeout=30)
        check("pending order can be cancelled", r.status_code == 200 and r.json()["status"] == "cancelled")
        r = requests.delete(f"{BASE}/paper/orders/{order_id}", timeout=30)
        check("cancelling twice gives 409", r.status_code == 409)
    else:
        print(f"  info: order {order_id} is already {mine['status'] if mine else 'missing'} (a new candle arrived), cancel test skipped")
check("cancelling an unknown order gives 404", requests.delete(BASE + "/paper/orders/999999", timeout=30).status_code == 404)

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
