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
    response = requests.get(BASE + path, timeout=60)
    return response, (time.time() - started) * 1000


try:
    requests.get(BASE + "/", timeout=3)
except requests.RequestException:
    print(f"backend not reachable at {BASE}. Start it: uvicorn main:app --reload --port 8010")
    sys.exit(1)

print("model selection on /predict")
for model in ("xgboost", "logistic", "lstm"):
    r, ms = get(f"/predict/BTCUSDT?model={model}")
    if r.status_code == 200:
        body = r.json()
        check(f"model={model} returns 200", True, f"{ms:.0f} ms, signal {body['signal']} at {body['confidence']:.2f}, type {body['model']['type']}")
        check(f"model={model} reports its own type", body["model"]["type"] == model)
        check(f"model={model} probabilities sum to about 1", abs(sum(body["probabilities"].values()) - 1) < 0.01)
    else:
        check(f"model={model} returns 200", False, f"{r.status_code}: {r.text[:160]}")

r, _ = get("/predict/BTCUSDT")
check("default model is still xgboost", r.status_code == 200 and r.json()["model"]["type"] == "xgboost")
r, _ = get("/predict/BTCUSDT?model=transformer")
check("unknown model gives 422", r.status_code == 422)
r, _ = get("/predict/DOGEUSDT?model=lstm")
check("unknown symbol still gives 404", r.status_code == 404)

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
