from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from errors import register_exception_handlers
from routers import prices, trades

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


@app.get("/", tags=["Health"], summary="Is the backend alive?")
def read_root():
    return {"message": "Aurea backend is alive", "environment": settings.app_env}
