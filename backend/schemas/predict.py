from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class Probabilities(BaseModel):
    sell: float
    hold: float
    buy: float


class WalkForwardSummary(BaseModel):
    folds: int
    mean_balanced_accuracy: float
    std_balanced_accuracy: float
    mean_net_bps_per_trade: float
    folds_with_positive_net: int
    pooled_net_bps_per_trade: float
    pooled_p_value: float


class ModelInfo(BaseModel):
    type: str
    trained_through: str
    trained_rows: int
    created_at: str
    walk_forward: WalkForwardSummary


class PredictionResponse(BaseModel):
    symbol: str
    timeframe: Literal["1h"]
    signal: Literal["sell", "hold", "buy"]
    confidence: float
    probabilities: Probabilities
    as_of: datetime
    data_age_minutes: float
    stale: bool
    model: ModelInfo
    calibrated: bool
    research_only: bool
    disclaimer: str
