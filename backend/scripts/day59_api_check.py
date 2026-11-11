import sys

import requests

BASE = "http://127.0.0.1:8010"
results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def ask(question):
    return requests.post(BASE + "/copilot/ask", json={"question": question}, timeout=60)


try:
    requests.get(BASE + "/", timeout=3)
except requests.RequestException:
    print(f"backend not reachable at {BASE}. Start it: uvicorn main:app --reload --port 8010")
    sys.exit(1)

print("copilot status")
r = requests.get(BASE + "/copilot/status", timeout=30)
check("GET /copilot/status returns 200", r.status_code == 200)
st = r.json()
print(f"  info: mode={st['mode']} model={st['model']} note={st['note']}")

print("answering")
r = ask("What is the daily loss limit?")
if r.status_code == 503:
    print("  SKIP: " + r.json()["detail"])
    sys.exit(1)
body = r.json()
check("POST /copilot/ask returns 200", r.status_code == 200, r.text[:150] if r.status_code != 200 else "")
print(f"  info: [{body['mode']} | {body['confidence']}] {body['answer'][:200]}")
check("the question is answered, not refused", body["refused"] is False and "3 percent" in body["answer"])
check("the answer carries a citation and at least one source is marked cited", "[" in body["answer"] and any(s["cited"] for s in body["sources"]))
check("every source names its document and title", all(s["doc"] and s["title"] for s in body["sources"]))
check("the disclaimer is attached", "not" in body["disclaimer"].lower() and "advice" in body["disclaimer"].lower())
if st["mode"] == "llm":
    check("with an API key the answer comes from the language model (or falls back with a reason)", body["mode"] == "llm" or body["fallback_reason"] or body["llm_error"], f"mode {body['mode']}, fallback {body['fallback_reason']}, error {body['llm_error']}")
r = ask("How much of my account can I lose in one position?")
check("a paraphrased question is answered from the risk limits", r.status_code == 200 and not r.json()["refused"] and any("1 percent of equity" in s["text"] for s in r.json()["sources"]))

print("not guessing")
r = ask("What is the capital of France?")
check("an unrelated question is refused", r.status_code == 200 and r.json()["refused"] is True and r.json()["mode"] == "refusal")
check("a refusal shows no sources", r.json()["sources"] == [])
r = ask("Write a poem about the ocean.")
check("a second unrelated question is refused", r.json()["refused"] is True)
r = ask("Which broker does Aurea use for live trading?")
print(f"  info: near-domain question 'Which broker does Aurea use for live trading?' -> refused={r.json()['refused']} confidence={r.json()['confidence']} mode={r.json()['mode']} (the retrieval check alone cannot catch this one)")

print("input checks")
check("empty question gives 422", requests.post(BASE + "/copilot/ask", json={"question": ""}, timeout=30).status_code == 422)
check("a 501 character question gives 422", requests.post(BASE + "/copilot/ask", json={"question": "x" * 501}, timeout=30).status_code == 422)
check("a missing question gives 422", requests.post(BASE + "/copilot/ask", json={}, timeout=30).status_code == 422)
check("whitespace-only question gives 422", ask("   ").status_code == 422)

print("rate limit (20 questions per minute; refusals cost nothing)")
codes = [ask("What is the capital of France?").status_code for _ in range(25)]
check("the limit kicks in with 429", 429 in codes, f"{codes.count(200)} answered, {codes.count(429)} blocked")
r = ask("What is the capital of France?")
if r.status_code == 429:
    check("429 carries a Retry-After header", "Retry-After" in r.headers, f"{r.headers.get('Retry-After')} s")
print("  note: wait one minute before asking more questions")

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
