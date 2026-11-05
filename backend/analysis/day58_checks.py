import tempfile
from pathlib import Path

import numpy as np

from rag.bm25 import BM25, stem, tokenize
from rag.chunker import chunk_corpus, chunk_markdown, corpus_hash, load_corpus
from rag.embedders import LsaEmbedder
from rag.evaluate import evaluate, gold_problems, load_questions
from rag.index import build_index, load_index
from services.rag_service import KNOWLEDGE_DIR

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


print("chunker")
md = "# Doc title\n\nIntro line.\n\n## Risk\nFirst risk fact. Second risk fact.\n\n### Limits\nLimit text here.\n\n## Empty section\n\n## Costs\nCost text."
chunks = chunk_markdown("d.md", md)
titles = [c.title for c in chunks]
check("headings become a title path", titles == ["Doc title", "Doc title > Risk", "Doc title > Risk > Limits", "Doc title > Costs"], str(titles))
check("a heading with no text produces no chunk", not any("Empty" in t for t in titles))
check("ids are unique and stable", len({c.id for c in chunks}) == len(chunks) and [c.id for c in chunks] == [c.id for c in chunk_markdown("d.md", md)])
long_text = "# T\n\n" + " ".join(f"Sentence number {i} talks about risk and size of the position." for i in range(40))
long_chunks = chunk_markdown("l.md", long_text, max_chars=300, overlap_chars=60)
check("long sections are split", len(long_chunks) > 3, f"{len(long_chunks)} chunks")
check("no chunk is much longer than the limit", all(len(c.text) <= 300 + 60 for c in long_chunks), f"longest {max(len(c.text) for c in long_chunks)}")
joined = " ".join(c.text for c in long_chunks)
check("no sentence is lost by splitting", all(f"Sentence number {i} " in joined for i in range(40)))
check("neighbouring chunks overlap", any(set(a.text.split()[-5:]) & set(b.text.split()[:12]) for a, b in zip(long_chunks, long_chunks[1:])))
check("the corpus hash changes when a document or a setting changes", corpus_hash({"a": "x"}) != corpus_hash({"a": "y"}) and corpus_hash({"a": "x"}) != corpus_hash({"a": "x"}, max_chars=500))

print("BM25 keyword search")
docs = ["risk limit one percent per trade", "stop and target orders", "daily loss limit three percent", "limit " + "filler " * 40]
bm = BM25(docs)
scores = bm.scores("daily loss limit")
check("the document with the most matching words ranks first", int(np.argmax(scores)) == 2)
check("a word nobody has gives all zeros", all(s == 0 for s in bm.scores("zzzunknown")))
check("a rare word counts more than a common one", bm.scores("daily")[2] > bm.scores("limit")[2])
check("a short document beats a long one with the same single match", bm.scores("limit")[0] > bm.scores("limit")[3])
check("simple stemming: limits and limit match", stem("limits") == stem("limit") and stem("stops") == "stop" and stem("class") == "class")
check("stop words are dropped from the query", tokenize("what is the limit") == ["limit"])

print("knowledge base index (offline LSA embedder)")
corpus = load_corpus(KNOWLEDGE_DIR)
all_chunks = chunk_corpus(corpus)
check("the knowledge folder has documents and many chunks", len(corpus) >= 6 and len(all_chunks) >= 30, f"{len(corpus)} documents, {len(all_chunks)} chunks")
folder = Path(tempfile.mkdtemp())
index = build_index(corpus, LsaEmbedder(), folder)
check("vectors have unit length", np.allclose(np.linalg.norm(index.vectors, axis=1), 1.0, atol=1e-4))
hits = index.search("What is the daily loss limit?", k=3)
check("hybrid search returns k hits sorted by score", len(hits) == 3 and hits[0]["score"] >= hits[1]["score"] >= hits[2]["score"])
check("the best hit for a plain question contains the answer", "daily loss limit" in hits[0]["text"].lower(), hits[0]["title"])
check("every hit says where it came from", all(h["doc"].endswith(".md") and h["title"] and h["id"] for h in hits))
check("bm25 mode has no dense fields and dense mode has them", index.search("daily loss limit", 2, "bm25")[0]["dense_rank"] is None and index.search("daily loss limit", 2, "dense")[0]["dense_score"] is not None)
paraphrase = "How much of my account can I lose in one position?"
bm_hits = index.search(paraphrase, 5, "bm25")
dense_hits = index.search(paraphrase, 5, "dense")
found = lambda hs: any("risk at most 1 percent of equity per trade" in h["text"].lower() for h in hs)
print(f"  info: paraphrase found by bm25 top 5: {found(bm_hits)} | by dense top 5: {found(dense_hits)} | by hybrid top 5: {found(index.search(paraphrase, 5))}")
check("hybrid finds the paraphrase", found(index.search(paraphrase, 5)))
for bad in ("", "   "):
    try:
        index.search(bad)
        check(f"empty query {bad!r} is refused", False)
    except ValueError:
        check(f"empty query {bad!r} is refused", True)
try:
    index.search("risk", mode="magic")
    check("unknown mode is refused", False)
except ValueError:
    check("unknown mode is refused", True)
check("k larger than the index is clipped", len(index.search("risk", k=10_000)) <= len(all_chunks))
reloaded = load_index(folder)
same = [h["id"] for h in index.search("tradability screen", 5)] == [h["id"] for h in reloaded.search("tradability screen", 5)]
check("saving and loading the index gives identical results", same and reloaded.meta["corpus_hash"] == index.meta["corpus_hash"])
changed = dict(corpus)
changed["01_overview.md"] = corpus["01_overview.md"] + "\nNew fact."
check("editing a document makes the saved index detectably stale", corpus_hash(changed, index.meta["max_chars"], index.meta["overlap_chars"]) != index.meta["corpus_hash"])

print("retrieval quality on the 24 test questions")
questions = load_questions(KNOWLEDGE_DIR / "eval_questions.json")
check("every test question's answer phrase exists in some chunk", gold_problems(questions, all_chunks) == [], str(gold_problems(questions, all_chunks)))
scores = evaluate(index, questions)
for mode, r in scores.items():
    print(f"  info: {mode:7} recall@1 {r['recall@1']:.2f} | recall@3 {r['recall@3']:.2f} | recall@5 {r['recall@5']:.2f} | MRR {r['mrr']:.2f}")
check("hybrid recall@3 is at least 0.80", scores["hybrid"]["recall@3"] >= 0.80)
check("hybrid is not worse than the weaker of bm25 and dense at recall@3", scores["hybrid"]["recall@3"] >= min(scores["bm25"]["recall@3"], scores["dense"]["recall@3"]))

print(f"\n{results['passed']} passed, {results['failed']} failed")
raise SystemExit(1 if results["failed"] else 0)
