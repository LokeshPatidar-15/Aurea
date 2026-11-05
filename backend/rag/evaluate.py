import json
from pathlib import Path

from rag.index import MODES


def load_questions(path: Path) -> list:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def gold_problems(questions: list, chunks: list) -> list:
    texts = [c.text.lower() for c in chunks]
    return [q["q"] for q in questions if not any(q["phrase"].lower() in t for t in texts)]


def evaluate(index, questions: list, ks=(1, 3, 5)) -> dict:
    out = {}
    for mode in MODES:
        hits_at = {k: 0 for k in ks}
        reciprocal = 0.0
        misses = []
        for q in questions:
            results = index.search(q["q"], k=max(ks), mode=mode)
            rank = next((i + 1 for i, r in enumerate(results) if q["phrase"].lower() in r["text"].lower()), None)
            if rank is None:
                misses.append(q["q"])
                continue
            reciprocal += 1.0 / rank
            for k in ks:
                hits_at[k] += int(rank <= k)
        n = len(questions)
        out[mode] = {**{f"recall@{k}": hits_at[k] / n for k in ks}, "mrr": reciprocal / n, "misses": misses}
    return out
