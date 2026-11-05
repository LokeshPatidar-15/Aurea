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

print("index status")
r = requests.get(BASE + "/rag/status", timeout=30)
if r.status_code == 503:
    print("  SKIP: " + r.json()["detail"])
    sys.exit(1)
st = r.json()
check("GET /rag/status returns 200", r.status_code == 200)
print(f"  info: embedder {st['embedder']} | {st['chunks']} chunks | {st['dim']}-d | built {st['built_at']} | documents {len(st['documents'])}")
check("the index is not stale (documents unchanged since it was built)", st["stale"] is False, "run python3 -m scripts.build_rag_index again" if st["stale"] else "")

print("search")
r = requests.get(BASE + "/rag/search", params={"q": "What is the daily loss limit?", "k": 3}, timeout=60)
check("GET /rag/search returns 200", r.status_code == 200, r.text[:150] if r.status_code != 200 else "")
body = r.json() if r.status_code == 200 else {"hits": []}
if body["hits"]:
    print(f"  info: took {body['took_ms']} ms | top hit: {body['hits'][0]['title']} (score {body['hits'][0]['score']:.4f})")
check("returns the 3 hits asked for", len(body["hits"]) == 3)
check("the top hit contains the answer", bool(body["hits"]) and "daily loss limit" in body["hits"][0]["text"].lower())
check("every hit has its source document and title", all(h["doc"] and h["title"] for h in body["hits"]))
for mode in ("bm25", "dense", "hybrid"):
    r = requests.get(BASE + "/rag/search", params={"q": "Why is gold blocked from paper trading?", "k": 5, "mode": mode}, timeout=60)
    ok = r.status_code == 200 and any("xauusd" in h["text"].lower() for h in r.json()["hits"])
    check(f"mode={mode} finds the XAUUSD tradability passage in the top 5", ok)
r = requests.get(BASE + "/rag/search", params={"q": "How much of my account can I lose in one position?", "k": 5}, timeout=60)
check("a paraphrase is found by hybrid search", r.status_code == 200 and any("1 percent of equity" in h["text"].lower() for h in r.json()["hits"]))
r = requests.get(BASE + "/rag/search", params={"q": "How fast is the second call?", "k": 3}, timeout=60)
check("a repeat call is fast (index is cached)", r.status_code == 200 and r.json()["took_ms"] < 500, f"{r.json()['took_ms']} ms")

print("error handling")
check("empty query gives 422", requests.get(BASE + "/rag/search", params={"q": ""}, timeout=30).status_code == 422)
check("whitespace-only query gives 422", requests.get(BASE + "/rag/search", params={"q": "   "}, timeout=30).status_code == 422)
check("k=0 gives 422", requests.get(BASE + "/rag/search", params={"q": "risk", "k": 0}, timeout=30).status_code == 422)
check("k=50 gives 422", requests.get(BASE + "/rag/search", params={"q": "risk", "k": 50}, timeout=30).status_code == 422)
check("unknown mode gives 422", requests.get(BASE + "/rag/search", params={"q": "risk", "mode": "magic"}, timeout=30).status_code == 422)
check("a query with no useful words still returns 200", requests.get(BASE + "/rag/search", params={"q": "zzzqqq xyzzy"}, timeout=30).status_code == 200)

print(f"\n{results['passed']} passed, {results['failed']} failed")
sys.exit(1 if results["failed"] else 0)
