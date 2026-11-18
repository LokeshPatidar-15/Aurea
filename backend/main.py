import asyncio
from contextlib import asynccontextmanager, suppress

import requests
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
from routers import copilot as copilot_router
from routers import patterns as patterns_router

from routers import builder as builder_router

from routers import backtest as backtest_router
from routers import pipeline as pipeline_router
from routers import portfolio as portfolio_router
from routers import ws as ws_router
from services import candle_pipeline, prediction_service, price_service, strategy_service, trading_loop
from services.live_feed import PROXY_FEEDS, BinanceWsFeed, make_websockets_connect, rest_fetcher
from services.tick_poller import PollingTicker
from services.ws_hub import DEFAULT_SYMBOLS, hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.max_clients = settings.ws_max_clients
    hub.meta["poll_seconds"] = settings.ws_poll_seconds
    hub.proxies = dict(PROXY_FEEDS)
    feed = None
    tasks = []
    if settings.ws_feed_enabled:
        feed = BinanceWsFeed(hub, settings.binance_ws_url, make_websockets_connect(), idle_grace_s=settings.ws_idle_grace_seconds)
        hub.meta["feed"] = feed.status
        tasks.append(asyncio.create_task(feed.run(), name="binance-ws-feed"))
    if settings.ws_poll_seconds > 0:
        fetch = rest_fetcher(requests.get, settings.binance_base_url, settings.request_timeout_seconds)
        ticker = PollingTicker(
            hub,
            fetch,
            DEFAULT_SYMBOLS,
            max(1.0, settings.ws_poll_seconds),
            to_tick=lambda raw: raw,
            gate=feed.fallback_wanted if feed else None,
        )
        tasks.append(asyncio.create_task(ticker.run(), name="rest-fallback-poller"))
    pipe = candle_pipeline.CandlePipeline(
        hub,
        cycle=lambda: trading_loop.run_cycle(ingest=True, place_orders=settings.pipeline_place_orders),
        rule_signal=strategy_service.latest_signal,
        model_signal=lambda symbol: prediction_service.predict(symbol, "1h", "xgboost"),
        symbols=DEFAULT_SYMBOLS,
    )
    pipe.scheduler_enabled = settings.pipeline_enabled
    pipe.place_orders = settings.pipeline_place_orders
    candle_pipeline.set_pipeline(pipe)
    hub.meta["pipeline"] = pipe.status
    if settings.pipeline_enabled:
        tasks.append(asyncio.create_task(pipe.run(), name="candle-pipeline"))
    yield
    for task in tasks:
        task.cancel()
    candle_pipeline.set_pipeline(None)
    for task in tasks:
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    lifespan=lifespan,
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
app.include_router(copilot_router.router)
app.include_router(patterns_router.router)
app.include_router(builder_router.router)
app.include_router(backtest_router.router)
app.include_router(strategy_router.router)
app.include_router(loop_router.router)
app.include_router(ws_router.router)
app.include_router(pipeline_router.router)
app.include_router(portfolio_router.router)


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
