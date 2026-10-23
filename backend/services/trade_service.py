from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Trade

PRICE_FIELDS = ("entry_price", "exit_price", "quantity")


class TradeNotFoundError(Exception):
    pass


def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def calculate_pnl(entry_price, exit_price, quantity, direction) -> Decimal:
    entry_price, exit_price, quantity = _dec(entry_price), _dec(exit_price), _dec(quantity)
    diff = exit_price - entry_price
    if direction == "short":
        diff = -diff
    return round(diff * quantity, 2)


def _recalculate(trade: Trade) -> None:
    trade.pnl = calculate_pnl(trade.entry_price, trade.exit_price, trade.quantity, trade.direction)


def create_trade(db: Session, data: dict) -> Trade:
    trade = Trade(
        symbol=data["symbol"].upper(),
        direction=data["direction"],
        entry_price=_dec(data["entry_price"]),
        exit_price=_dec(data["exit_price"]),
        quantity=_dec(data["quantity"]),
        notes=data.get("notes", ""),
        pnl=Decimal("0"),
    )
    _recalculate(trade)
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def list_trades(db: Session, limit: int = 10, direction: str | None = None, symbol: str | None = None) -> list[Trade]:
    stmt = select(Trade)
    if direction:
        stmt = stmt.where(Trade.direction == direction)
    if symbol:
        stmt = stmt.where(Trade.symbol == symbol.upper())
    stmt = stmt.order_by(Trade.id.desc()).limit(limit)
    return list(reversed(db.scalars(stmt).all()))


def get_trade(db: Session, trade_id: int) -> Trade:
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise TradeNotFoundError(f"Trade {trade_id} not found")
    return trade


def update_trade(db: Session, trade_id: int, changes: dict) -> Trade:
    trade = get_trade(db, trade_id)
    for field, value in changes.items():
        if value is None:
            continue
        if field == "symbol":
            value = value.upper()
        elif field in PRICE_FIELDS:
            value = _dec(value)
        setattr(trade, field, value)
    _recalculate(trade)
    db.commit()
    db.refresh(trade)
    return trade


def replace_trade(db: Session, trade_id: int, data: dict) -> Trade:
    trade = get_trade(db, trade_id)
    trade.symbol = data["symbol"].upper()
    trade.direction = data["direction"]
    trade.entry_price = _dec(data["entry_price"])
    trade.exit_price = _dec(data["exit_price"])
    trade.quantity = _dec(data["quantity"])
    trade.notes = data.get("notes", "")
    _recalculate(trade)
    db.commit()
    db.refresh(trade)
    return trade


def delete_trade(db: Session, trade_id: int) -> None:
    trade = get_trade(db, trade_id)
    db.delete(trade)
    db.commit()
