import math

from fastapi import APIRouter, HTTPException

from schemas.copilot import AskIn, AskOut, CopilotStatus
from services import copilot_service, rag_service

router = APIRouter(prefix="/copilot", tags=["Copilot"])


@router.post("/ask", response_model=AskOut, summary="Ask about Aurea: explanations come from the knowledge base with sources; live numbers come straight from the read-only API")
def ask(body: AskIn):
    allowed, wait = copilot_service.LIMITER.allow()
    if not allowed:
        raise HTTPException(status_code=429, detail="too many questions, slow down", headers={"Retry-After": str(math.ceil(wait))})
    try:
        return copilot_service.ask(body.question)
    except rag_service.IndexMissing as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/status", response_model=CopilotStatus, summary="Whether answers come from Claude or from the knowledge base alone")
def status():
    return copilot_service.status()
