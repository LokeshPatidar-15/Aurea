from typing import Literal

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from schemas.predict import PredictionResponse
from services import prediction_service
from services.prediction_service import ModelNotFoundError, NotEnoughDataError, UnsupportedSymbolError

router = APIRouter(prefix="/predict", tags=["Prediction"])

DISCLAIMER = (
    "Research output from a model with no demonstrated edge after costs. "
    "See model.walk_forward for its honest out-of-sample numbers. Not financial advice."
)


@router.get("/{symbol}", response_model=PredictionResponse, summary="Latest buy / sell / hold signal from the ML model")
def get_prediction(symbol: str, timeframe: Literal["1h"] = "1h", model: Literal["xgboost", "logistic", "lstm"] = "xgboost"):
    try:
        result = prediction_service.predict(symbol.upper(), timeframe, model)
    except UnsupportedSymbolError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ModelNotFoundError, NotEnoughDataError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")
    return {**result, "calibrated": False, "research_only": True, "disclaimer": DISCLAIMER}
