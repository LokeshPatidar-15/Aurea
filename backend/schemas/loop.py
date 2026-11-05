from datetime import datetime

from pydantic import BaseModel


class SymbolAction(BaseModel):
    signal: str | None = None
    action: str
    why: str | None = None
    position_id: int | None = None


class CycleOut(BaseModel):
    started_at: datetime
    finished_at: datetime
    ingest: dict | None = None
    tick: dict | None = None
    symbols: dict[str, SymbolAction]
    errors: list[str]
