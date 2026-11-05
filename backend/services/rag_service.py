from pathlib import Path

from rag.chunker import corpus_hash, load_corpus
from rag.index import RagIndex, load_index

BASE = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE / "knowledge"
INDEX_DIR = BASE / "artifacts" / "rag_index"
_cache: dict = {}


class IndexMissing(Exception):
    pass


def get_index() -> RagIndex:
    if "index" not in _cache:
        if not (INDEX_DIR / "meta.json").exists():
            raise IndexMissing("no knowledge index yet. Run: python3 -m scripts.build_rag_index")
        _cache["index"] = load_index(INDEX_DIR)
    return _cache["index"]


def reload_index() -> None:
    _cache.clear()


def status() -> dict:
    index = get_index()
    meta = index.meta
    corpus = load_corpus(KNOWLEDGE_DIR)
    current = corpus_hash(corpus, meta["max_chars"], meta["overlap_chars"])
    return {
        "embedder": meta["embedder"], "chunks": meta["n_chunks"], "dim": meta["dim"], "built_at": meta["built_at"],
        "documents": sorted({c.doc for c in index.chunks}), "stale": current != meta["corpus_hash"],
    }


def search(query: str, k: int = 5, mode: str = "hybrid") -> list:
    return get_index().search(query, k=k, mode=mode)
