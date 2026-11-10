import json
import re
import tempfile
from pathlib import Path

from rag.chunker import load_corpus
from rag.copilot import answer_question, extractive_answer
from rag.embedders import LsaEmbedder
from rag.index import build_index
from services.rag_service import KNOWLEDGE_DIR

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


index = build_index(load_corpus(KNOWLEDGE_DIR), LsaEmbedder(), Path(tempfile.mkdtemp()))
gold = json.load(open(KNOWLEDGE_DIR / "eval_questions.json"))

print("extractive answers keep the useful sentence and drop the noise")
r = answer_question("What is the daily loss limit?", index)
check("daily loss limit: answer has the 3 percent sentence and no unrelated glossary sentence", "daily loss limit of 3 percent" in r["answer"] and "Total profit of winning trades" not in r["answer"], r["answer"][:80])
r = answer_question("Why is gold blocked from paper trading?", index)
check("gold blocked: answer explains the tradability result and does not add the paper-trading definition", "blocked at this cost" in r["answer"] and "simulated money" not in r["answer"])

hits_total = chars = sentences = 0
grounded = True
for q in gold:
    r = answer_question(q["q"], index)
    hits_total += q["phrase"].lower() in r["answer"].lower()
    chars += len(r["answer"])
    sentences += len(re.findall(r"\[\d+\]", r["answer"]))
    parts = [re.sub(r"\s*\[\d+\]$", "", s).strip() for s in re.split(r"(?<=\])\s+", r["answer"])]
    parts = [p.replace("I am not sure this fully answers your question. The closest passages say: ", "") for p in parts]
    grounded &= all(any(p in s["text"] for s in r["sources"]) for p in parts)
print(f"  info: answer contains the gold phrase for {hits_total}/24 questions | average {sentences / 24:.2f} sentences, {chars / 24:.0f} characters")
check("at least 18 of 24 answers contain the sentence that holds the facts", hits_total >= 18)
check("answers are shorter than before (average under 330 characters)", chars / 24 < 330)
check("every sentence of every answer is still copied from a source passage", grounded)
hits = index.search("What is the daily loss limit?", k=4, mode="hybrid")
body, cited = extractive_answer("What is the daily loss limit?", hits, "ok")
check("the function still works without idf weights (older call style)", "[" in body and cited)

print(f"\n{results['passed']} passed, {results['failed']} failed")
raise SystemExit(1 if results["failed"] else 0)
