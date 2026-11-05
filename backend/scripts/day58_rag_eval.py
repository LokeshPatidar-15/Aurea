import tempfile
from pathlib import Path

from rag.chunker import chunk_corpus, load_corpus
from rag.embedders import LsaEmbedder, SentenceTransformerEmbedder
from rag.evaluate import evaluate, gold_problems, load_questions
from rag.index import build_index
from services import rag_service

corpus = load_corpus(rag_service.KNOWLEDGE_DIR)
questions = load_questions(rag_service.KNOWLEDGE_DIR / "eval_questions.json")
problems = gold_problems(questions, chunk_corpus(corpus))
print(f"{len(corpus)} documents, {len(questions)} test questions")
if problems:
    print("these questions have a phrase that is in no chunk (fix the question set):", problems)
embedders = [LsaEmbedder()]
try:
    import sentence_transformers  # noqa: F401
    embedders.append(SentenceTransformerEmbedder())
except ImportError:
    print("sentence-transformers is not installed: only the offline LSA embedder is compared (pip install sentence-transformers to add the neural one)")

print(f"\n{'embedder':48} {'mode':7} {'recall@1':>8} {'recall@3':>8} {'recall@5':>8} {'MRR':>6}")
for embedder in embedders:
    index = build_index(corpus, embedder, Path(tempfile.mkdtemp()))
    for mode, r in evaluate(index, questions).items():
        print(f"{embedder.name:48} {mode:7} {r['recall@1']:8.2f} {r['recall@3']:8.2f} {r['recall@5']:8.2f} {r['mrr']:6.2f}")
        for q in r["misses"]:
            print(f"{'':48}   missed in top 5: {q}")
print("\nrecall@k = share of questions whose answer-bearing passage is in the top k hits. MRR = average of 1/rank of that passage.")
print("note: the questions were written by the same person who wrote the documents, so the scores are optimistic. Add your own questions to knowledge/eval_questions.json.")
