import sys

import requests

BASE = "http://127.0.0.1:8010"
results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def ask(question):
    return requests.post(BASE + "/copilot/ask", json={"question": question}, timeout=120)


def money(x):
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


try:
    requests.get(BASE + "/", timeout=3)
except requests.RequestException:
    print(f"backend not reachable at {BASE}. Start it: uvicorn main:app --reload --port 8010")
    sys.exit(1)

print("status")
st = requests.get(BASE + "/copilot/status", timeout=30).json()
check("the status lists the 8 live tools", len(st["live_tools"]) == 8, ", ".join(st["live_tools"]))

print("live answers match the endpoints")
r = ask("What is the signal for BTC now?")
check("POST /copilot/ask returns 200", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")
body = r.json()
print("  " + body["answer"].replace("\n", "\n  "))
check("mode is live, no knowledge-base sources, tools listed", body["mode"] == "live" and body["sources"] == [] and set(body["tools_used"]) == {"signal", "prediction"})
facts = {f["tool"]: f for f in body["live"]}
sig = requests.get(BASE + "/strategy/signal/BTCUSDT", timeout=60)
if sig.status_code == 200 and facts["signal"]["ok"] and facts["signal"]["as_of"] and facts["signal"]["as_of"][:16] == sig.json()["as_of"][:16]:
    s = sig.json()
    check("the rule signal in the answer equals /strategy/signal", (s["side"].upper() + " signal" in facts["signal"]["text"]) if s["status"] == "signal" else "no signal" in facts["signal"]["text"], s["status"])
    check("the reference price in the answer equals the endpoint", f"{s['reference_price']:,.2f}" in facts["signal"]["text"])
else:
    print("  info: signal cross-check skipped (candle changed or tool unavailable): " + facts["signal"]["text"][:120])
pred = requests.get(BASE + "/predict/BTCUSDT?model=xgboost", timeout=60)
if pred.status_code == 200 and facts["prediction"]["ok"] and facts["prediction"]["as_of"][:16] == pred.json()["as_of"][:16]:
    p = pred.json()
    check("the model signal and confidence equal /predict", f"{p['signal'].upper()} with {round(p['confidence'] * 100)}%" in facts["prediction"]["text"], f"{p['signal']} {p['confidence']}")
else:
    print("  info: prediction cross-check skipped: " + facts["prediction"]["text"][:120])
check("every fact names its endpoint", all(f["source"].startswith("GET ") for f in body["live"]))

r = ask("How is my paper account doing?")
body = r.json()
summ = requests.get(BASE + "/paper/summary", timeout=30).json()
perf = requests.get(BASE + "/paper/performance", timeout=30).json()
check("the paper account answer is live", r.status_code == 200 and body["mode"] == "live" and set(body["tools_used"]) == {"summary", "performance"})
check("realized equity equals /paper/summary", money(summ["realized_equity"]) in body["answer"], money(summ["realized_equity"]))
check("pending orders and closed trades equal /paper/summary", f"{summ['pending_orders']} pending order" in body["answer"] and (f"{summ['closed_trades']} closed trades" in body["answer"] or summ["closed_trades"] == 0))
if perf.get("trades"):
    check("the sample-size warning from /paper/performance is passed on", perf["sample_warning"] is None or perf["sample_warning"][:30] in body["answer"])
else:
    check("with no closed trades the answer says there is nothing to measure", "no closed paper trades" in body["answer"])

r = ask("Is gold tradable right now?")
trad = {t["symbol"]: t for t in requests.get(BASE + "/paper/tradability", timeout=60).json()}
body = r.json()
check("tradability equals /paper/tradability", r.status_code == 200 and ("XAUUSD tradable" in body["answer"]) == trad["XAUUSD"]["tradable"] and "BTCUSDT" not in body["answer"])

r = ask("How many strategies have been tested so far?")
n = requests.get(BASE + "/strategy/trials", timeout=30).json()["strategies_tried"]
check("the strategies-tried count equals /strategy/trials", f"{n} strategy x symbol test" in r.json()["answer"], str(n))

r = ask("What is the current gold price?")
body = r.json()
check("the price answer says it is a closed candle, not a live tick", r.status_code == 200 and "not a live tick" in body["answer"] and body["live"][0]["as_of"] is not None)
print(f"  info: {body['live'][0]['text'][:150]} stale={body['live'][0]['stale']}")

r = ask("Is there a signal on any symbol?")
check("a question with no symbol covers all three symbols", len(r.json()["live"]) == 6, f"{len(r.json()['live'])} facts")

print("read-only and no advice")
before = requests.get(BASE + "/paper/positions?limit=500", timeout=30).json()
for q in ("Place a paper order to buy gold", "Should I buy bitcoin?", "Cancel all my orders"):
    r = ask(q)
    check(f"refused: {q}", r.status_code == 200 and r.json()["refused"] is True and r.json()["mode"] == "refusal" and "read-only" in r.json()["answer"])
after = requests.get(BASE + "/paper/positions?limit=500", timeout=30).json()
check("no paper position was created, changed or cancelled by those questions", [(x["id"], x["status"]) for x in before] == [(x["id"], x["status"]) for x in after], f"{len(after)} positions")
r = ask("Will bitcoin go up tomorrow?")
check("a price forecast is refused", r.json()["refused"] is True and "do not forecast" in r.json()["answer"])

print("the knowledge base still works")
r = ask("What is the daily loss limit?")
check("a knowledge question is still answered from the sources", r.status_code == 200 and r.json()["mode"] in ("extractive", "llm") and "3 percent" in r.json()["answer"] and r.json()["live"] == [])
r = ask("What is a liquidity sweep?")
check("a definition question is not turned into live data", r.json()["mode"] != "live")
r = ask("What is the capital of France?")
check("an unrelated question is still refused", r.json()["refused"] is True)

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
