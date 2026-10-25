import sys
import time

import requests

BASE = "http://127.0.0.1:8010"
results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def get(path: str):
    started = time.time()
    response = requests.get(BASE + path, timeout=30)
    return response, (time.time() - started) * 1000


try:
    requests.get(BASE + "/", timeout=3)
except requests.RequestException:
    print(f"backend not reachable at {BASE}. Start it in Tab 2: uvicorn main:app --reload --port 8010")
    sys.exit(1)

print("prediction endpoint")
response, first_ms = get("/predict/BTCUSDT")
check("GET /predict/BTCUSDT returns 200", response.status_code == 200, f"{first_ms:.0f} ms (first call loads the model)")
if response.status_code == 200:
    body = response.json()
    expected = {"symbol", "timeframe", "signal", "confidence", "probabilities", "as_of", "data_age_minutes", "stale", "model", "calibrated", "research_only", "disclaimer"}
    check("response has every documented field", expected <= set(body))
    check("probabilities sum to about 1", abs(sum(body["probabilities"].values()) - 1) < 0.01, str(body["probabilities"]))
    check("signal is sell / hold / buy", body["signal"] in {"sell", "hold", "buy"}, f"{body['signal']} at {body['confidence']:.2f}")
    check("honesty flags present", body["research_only"] is True and body["calibrated"] is False)
    print(f"  info: as_of {body['as_of']} | data age {body['data_age_minutes']:.0f} min | stale={body['stale']}")
    second, second_ms = get("/predict/BTCUSDT")
    check("second call is fast (model cached)", second.status_code == 200 and second_ms < 1500, f"{second_ms:.0f} ms")
else:
    print("   ", response.text[:300])

for symbol in ("XAUUSD", "EURUSD", "btcusdt"):
    r, ms = get(f"/predict/{symbol}")
    check(f"GET /predict/{symbol} returns 200", r.status_code == 200, f"{ms:.0f} ms")

print("error handling")
r, _ = get("/predict/DOGEUSDT")
check("unknown symbol gives 404", r.status_code == 404, r.json().get("detail", "")[:60])
r, _ = get("/predict/BTCUSDT?timeframe=15m")
check("unsupported timeframe gives 422", r.status_code == 422)
r, _ = get("/openapi.json")
check("endpoint is documented in OpenAPI", "/predict/{symbol}" in r.json().get("paths", {}))

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
