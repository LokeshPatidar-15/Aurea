import os
import time

from rag.copilot import DEFAULT_MODEL, RateLimiter, answer_question
from services import rag_service

LIMITER = RateLimiter(max_calls=20, per_seconds=60.0, clock=time.monotonic)
_client: dict = {}


def llm_settings() -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model = os.environ.get("AUREA_LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if not key:
        return {"client": None, "model": model, "reason": "ANTHROPIC_API_KEY is not set: answers are extracted from the knowledge base"}
    if "client" not in _client:
        try:
            import anthropic

            _client["client"] = anthropic.Anthropic(api_key=key, timeout=20.0, max_retries=1)
        except ImportError:
            return {"client": None, "model": model, "reason": "the anthropic package is not installed (pip install anthropic): answers are extracted from the knowledge base"}
    return {"client": _client["client"], "model": model, "reason": None}


def status() -> dict:
    settings = llm_settings()
    return {"mode": "llm" if settings["client"] else "extractive", "model": settings["model"] if settings["client"] else None, "note": settings["reason"]}


def ask(question: str) -> dict:
    settings = llm_settings()
    return answer_question(question, rag_service.get_index(), client=settings["client"], model=settings["model"])
