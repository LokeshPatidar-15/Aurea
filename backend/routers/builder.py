from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from analysis.rule_builder import validate_payload
from analysis.rules import RuleError
from analysis.templates import template_ids
from schemas.builder import PreviewOut, StrategyIn, TemplateOut, ValidateOut
from services import builder_service
from services.prediction_service import NotEnoughDataError, UnsupportedSymbolError

router = APIRouter(prefix="/strategy", tags=["Strategy builder"])


@router.get("/templates", response_model=list[TemplateOut], summary="Ready-made strategies built from named conditions")
def templates():
    return builder_service.list_templates()


@router.get("/templates/{template_id}", response_model=TemplateOut, summary="One template")
def template(template_id: str):
    if template_id not in template_ids():
        raise HTTPException(status_code=404, detail=f"unknown template {template_id!r}. Valid: {', '.join(template_ids())}")
    return builder_service.template_detail(template_id)


@router.post("/validate", response_model=ValidateOut, summary="Check a rule strategy and explain it in words (never executes anything)")
def validate(body: StrategyIn):
    return validate_payload(body.strategy)


@router.post("/preview/{symbol}", response_model=PreviewOut, summary="What would this strategy say on the latest closed candle")
def preview(symbol: str, body: StrategyIn, timeframe: str = "1h"):
    try:
        return builder_service.preview(symbol, body.strategy, timeframe)
    except RuleError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UnsupportedSymbolError as exc:
        raise HTTPException(status_code=404 if "symbol" in str(exc) else 422, detail=str(exc))
    except NotEnoughDataError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="database unavailable")
