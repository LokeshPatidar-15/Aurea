from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from services.price_service import (
    InvalidSymbolError,
    PriceServiceError,
    UnsupportedSymbolError,
)
from services.trade_service import TradeNotFoundError


def _make_handler(status_code: int):
    async def handler(request: Request, exc: Exception):
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(InvalidSymbolError, _make_handler(400))
    app.add_exception_handler(UnsupportedSymbolError, _make_handler(404))
    app.add_exception_handler(TradeNotFoundError, _make_handler(404))
    app.add_exception_handler(PriceServiceError, _make_handler(502))
