from typing import Literal

from pydantic import BaseModel, Field


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class SourceOut(BaseModel):
    n: int
    id: str
    doc: str
    title: str
    text: str
    cited: bool


class LiveFact(BaseModel):
    tool: str
    label: str
    text: str
    source: str
    as_of: str | None = None
    stale: bool
    ok: bool


class AskOut(BaseModel):
    question: str
    answer: str
    refused: bool
    mode: Literal["refusal", "extractive", "llm", "live"]
    confidence: Literal["ok", "low", "refuse"]
    coverage: float
    sources: list[SourceOut]
    live: list[LiveFact] = []
    tools_used: list[str] = []
    llm_error: str | None = None
    fallback_reason: str | None = None
    disclaimer: str


class CopilotStatus(BaseModel):
    mode: Literal["llm", "extractive"]
    model: str | None = None
    note: str | None = None
    live_tools: list[str] = []
