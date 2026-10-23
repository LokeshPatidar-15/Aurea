from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TradeCreate(BaseModel):
    symbol: str = Field(..., min_length=3, description="Trading pair symbol, e.g. BTCUSDT")
    entry_price: float = Field(..., gt=0)
    exit_price: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0)
    direction: Literal["long", "short"]
    notes: str = Field("", max_length=500)


class TradeUpdate(BaseModel):
    symbol: str | None = Field(None, min_length=3)
    entry_price: float | None = Field(None, gt=0)
    exit_price: float | None = Field(None, gt=0)
    quantity: float | None = Field(None, gt=0)
    direction: Literal["long", "short"] | None = None
    notes: str | None = Field(None, max_length=500)


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    direction: str
    notes: str
    pnl: float
    created_at: datetime
