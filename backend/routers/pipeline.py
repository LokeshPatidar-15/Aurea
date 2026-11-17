from typing import Literal

from fastapi import APIRouter, HTTPException

from services import candle_pipeline

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


def _pipe():
    pipe = candle_pipeline.get_pipeline()
    if pipe is None:
        raise HTTPException(status_code=503, detail="the candle pipeline has not started")
    return pipe


@router.get("/status", summary="Candle-close pipeline: scheduler, next run, last run summary")
def pipeline_status():
    return _pipe().status()


@router.post("/run", summary="Run the pipeline now. refresh = recompute and push signals only; full = ingest, paper tick, signals, push")
async def pipeline_run(mode: Literal["refresh", "full"] = "refresh"):
    pipe = _pipe()
    try:
        return await pipe.run_manual(mode)
    except candle_pipeline.PipelineBusy:
        raise HTTPException(status_code=429, detail="a pipeline run is already in progress", headers={"Retry-After": "10"})
    except candle_pipeline.PipelineTooSoon as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={"Retry-After": str(exc.retry_after)})
