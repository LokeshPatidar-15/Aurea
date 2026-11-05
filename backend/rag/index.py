import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from rag.bm25 import BM25
from rag.chunker import Chunk, chunk_corpus, corpus_hash
from rag.embedders import load_embedder

MODES = ("bm25", "dense", "hybrid")
RRF_K = 60
POOL = 20


class RagIndex:
    def __init__(self, chunks: list, vectors: np.ndarray, embedder, meta: dict):
        self.chunks, self.vectors, self.embedder, self.meta = chunks, vectors, embedder, meta
        self.bm25 = BM25([c.search_text for c in chunks])

    def _rank(self, scores) -> list:
        return [int(i) for i in np.argsort(-np.asarray(scores), kind="stable")]

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if not query or not query.strip():
            raise ValueError("query is empty")
        k = max(1, min(k, len(self.chunks)))
        bm_scores = np.array(self.bm25.scores(query))
        dense_scores = (self.vectors @ self.embedder.encode([query])[0]) if mode != "bm25" else np.zeros(len(self.chunks))
        bm_rank = {i: r for r, i in enumerate(self._rank(bm_scores)) if bm_scores[i] > 0}
        dense_rank = {i: r for r, i in enumerate(self._rank(dense_scores))}
        if mode == "bm25":
            order = [i for i in self._rank(bm_scores) if bm_scores[i] > 0][:k]
            fused = {i: float(bm_scores[i]) for i in order}
        elif mode == "dense":
            order = self._rank(dense_scores)[:k]
            fused = {i: float(dense_scores[i]) for i in order}
        else:
            fused = {}
            for i, r in bm_rank.items():
                if r < POOL:
                    fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
            for i, r in dense_rank.items():
                if r < POOL:
                    fused[i] = fused.get(i, 0.0) + 1.0 / (RRF_K + r + 1)
            order = sorted(fused, key=lambda i: (-fused[i], i))[:k]
        return [
            {"id": self.chunks[i].id, "doc": self.chunks[i].doc, "title": self.chunks[i].title, "text": self.chunks[i].text,
             "score": fused[i], "bm25_rank": bm_rank.get(i), "dense_rank": dense_rank[i] + 1 if mode != "bm25" else None,
             "dense_score": float(dense_scores[i]) if mode != "bm25" else None}
            for i in order
        ]


def build_index(corpus: dict, embedder, folder: Path, max_chars: int = 700, overlap_chars: int = 100) -> RagIndex:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    chunks = chunk_corpus(corpus, max_chars, overlap_chars)
    texts = [c.search_text for c in chunks]
    embedder.fit(texts)
    vectors = embedder.encode(texts)
    meta = {"embedder": embedder.name, "n_chunks": len(chunks), "dim": int(vectors.shape[1]), "corpus_hash": corpus_hash(corpus, max_chars, overlap_chars),
            "max_chars": max_chars, "overlap_chars": overlap_chars, "built_at": datetime.now(timezone.utc).isoformat()}
    np.save(folder / "vectors.npy", vectors)
    (folder / "chunks.json").write_text(json.dumps([asdict(c) for c in chunks], indent=1), encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    embedder.save(folder)
    return RagIndex(chunks, vectors, embedder, meta)


def load_index(folder: Path) -> RagIndex:
    folder = Path(folder)
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    chunks = [Chunk(**c) for c in json.loads((folder / "chunks.json").read_text(encoding="utf-8"))]
    vectors = np.load(folder / "vectors.npy")
    return RagIndex(chunks, vectors, load_embedder(meta["embedder"], folder), meta)
