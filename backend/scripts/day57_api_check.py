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

print("performance endpoint")
r = requests.get(BASE + "/paper/performance", timeout=30)
check("GET /paper/performance returns 200", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")
if r.status_code != 200:
    sys.exit(1)
perf = r.json()
print(f"  info: {perf['trades']} closed trades | equity {perf['start_equity']:,.0f} -> {perf['end_equity']:,.2f}")
if perf.get("sample_warning"):
    print(f"  info: warning shown to the user: {perf['sample_warning']}")
check("trades is a count and the start equity is 10,000", isinstance(perf["trades"], int) and perf["start_equity"] == 10_000)
check("a ledger with fewer than 30 trades carries a warning", perf["trades"] >= 30 or perf["sample_warning"] is not None)

print("equity curve")
r = requests.get(BASE + "/paper/equity-curve", timeout=30)
check("GET /paper/equity-curve returns 200", r.status_code == 200)
curve = r.json() if r.status_code == 200 else []
check("curve has a start point plus one point per closed trade (or is empty)", len(curve) == 0 or len(curve) == perf["trades"] + 1, f"{len(curve)} points")
check("curve points are in time order", all(a["time"] <= b["time"] for a, b in zip(curve, curve[1:])))
check("drawdown is always between 0 and 1", all(0 <= p["drawdown"] <= 1 for p in curve))
check("limit=2 returns at most 2 points", len(requests.get(BASE + "/paper/equity-curve?limit=2", timeout=30).json()) <= 2)

print("cross-check with /paper/summary (two separate code paths)")
summary = requests.get(BASE + "/paper/summary", timeout=30).json()
check("realized equity matches the end of the curve", abs(summary["realized_equity"] - perf["end_equity"]) < 1e-6, f"{summary['realized_equity']:.2f} vs {perf['end_equity']:.2f}")
check("closed trade count matches", summary["closed_trades"] == perf["trades"])
if perf["trades"]:
    check("drawdown from the summary is not worse than the max drawdown", summary["drawdown"] <= perf["max_drawdown"] + 1e-9)
    check("net pnl equals end equity minus start", abs(perf["net_pnl"] - (perf["end_equity"] - perf["start_equity"])) < 1e-6)

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
