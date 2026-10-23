from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from errors import register_exception_handlers
from routers import prices, trades

app = FastAPI(
    title="Aurea API",
    description="Backend for the Aurea trading platform: prices, trades, and (soon) signals.",
    version="0.1.0",
)

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

register_exception_handlers(app)

app.include_router(prices.router)
app.include_router(trades.router)


@app.get("/", tags=["Health"], summary="Is the backend alive?")
def read_root():
    return {"message": "Aurea backend is alive"}
