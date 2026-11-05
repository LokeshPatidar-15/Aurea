from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class HitOut(BaseModel):
    id: str
    doc: str
    title: str
    text: str
    score: float
    bm25_rank: int | None = None
    dense_rank: int | None = None
    dense_score: float | None = None


class SearchOut(BaseModel):
    query: str
    mode: Literal["bm25", "dense", "hybrid"]
    embedder: str
    took_ms: float
    hits: list[HitOut]


class StatusOut(BaseModel):
    embedder: str
    chunks: int
    dim: int
    built_at: datetime
    documents: list[str]
    stale: bool
