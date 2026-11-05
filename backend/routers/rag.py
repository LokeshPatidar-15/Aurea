import time
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from schemas.rag import SearchOut, StatusOut
from services import rag_service

router = APIRouter(prefix="/rag", tags=["Copilot knowledge"])


@router.get("/search", response_model=SearchOut, summary="Find the knowledge-base passages that best match a question")
def search(q: str = Query(min_length=1, max_length=500), k: int = Query(5, ge=1, le=10), mode: Literal["bm25", "dense", "hybrid"] = "hybrid"):
    started = time.perf_counter()
    try:
        hits = rag_service.search(q, k, mode)
        embedder = rag_service.get_index().meta["embedder"]
    except rag_service.IndexMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except ImportError as exc:
        raise HTTPException(status_code=503, detail=f"embedding library missing: {exc}")
    return {"query": q, "mode": mode, "embedder": embedder, "took_ms": round((time.perf_counter() - started) * 1000, 1), "hits": hits}


@router.get("/status", response_model=StatusOut, summary="Which embedder and documents the knowledge index was built from")
def status():
    try:
        return rag_service.status()
    except rag_service.IndexMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc))
