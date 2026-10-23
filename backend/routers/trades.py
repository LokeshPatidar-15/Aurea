from typing import Literal

from fastapi import APIRouter, Query, Response

from schemas.trade import TradeCreate, TradeResponse, TradeUpdate
from services import trade_service

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.post("", response_model=TradeResponse, status_code=201, summary="Create a trade")
def create_trade(trade: TradeCreate):
    return trade_service.create_trade(trade.model_dump())


@router.get("", response_model=list[TradeResponse], summary="List trades (latest first limited)")
def list_trades(
    limit: int = Query(10, ge=1, le=200),
    direction: Literal["long", "short"] | None = None,
    symbol: str | None = None,
):
    return trade_service.list_trades(limit, direction, symbol)


@router.get("/{trade_id}", response_model=TradeResponse, summary="Get one trade")
def get_trade(trade_id: int):
    return trade_service.get_trade(trade_id)


@router.put("/{trade_id}", response_model=TradeResponse, summary="Replace a trade")
def replace_trade(trade_id: int, trade: TradeCreate):
    return trade_service.replace_trade(trade_id, trade.model_dump())


@router.patch("/{trade_id}", response_model=TradeResponse, summary="Update some fields of a trade")
def update_trade(trade_id: int, changes: TradeUpdate):
    return trade_service.update_trade(trade_id, changes.model_dump(exclude_unset=True))


@router.delete("/{trade_id}", status_code=204, summary="Delete a trade")
def delete_trade(trade_id: int):
    trade_service.delete_trade(trade_id)
    return Response(status_code=204)
