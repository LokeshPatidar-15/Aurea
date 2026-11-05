from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from errors import register_exception_handlers
from routers import predict, prices, trades

from routers import paper as paper_router
from routers import strategy as strategy_router
from routers import loop as loop_router
from routers import paper_report as paper_report_router
from routers import rag as rag_router
app = FastAPI(
    title=settings.app_name,
    description="Backend for the Aurea trading platform: prices, trades, and (soon) signals.",
    version="0.1.0",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

register_exception_handlers(app)

app.include_router(prices.router)
app.include_router(trades.router)
app.include_router(predict.router)
app.include_router(paper_router.router)
app.include_router(paper_report_router.router)
app.include_router(rag_router.router)
app.include_router(strategy_router.router)
app.include_router(loop_router.router)


@app.get("/", tags=["Health"], summary="Is the backend alive?")
def read_root():
    return {"message": "Aurea backend is alive", "environment": settings.app_env}


@app.get("/health/db", tags=["Health"], summary="Can the backend reach the database?")
def db_health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        raise HTTPException(status_code=503, detail="Database unavailable")
    return {"database": "ok"}
