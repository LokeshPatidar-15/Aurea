from datetime import datetime, timezone


class TradeNotFoundError(Exception):
    pass


_trades: dict[int, dict] = {}
_next_id = 1


def calculate_pnl(entry_price: float, exit_price: float, quantity: float, direction: str) -> float:
    diff = exit_price - entry_price
    if direction == "short":
        diff = -diff
    return round(diff * quantity, 2)


def create_trade(data: dict) -> dict:
    global _next_id
    record = dict(data)
    record["id"] = _next_id
    record["pnl"] = calculate_pnl(
        record["entry_price"], record["exit_price"], record["quantity"], record["direction"]
    )
    record["created_at"] = datetime.now(timezone.utc).isoformat()
    _trades[_next_id] = record
    _next_id += 1
    return record


def list_trades(limit: int = 10, direction: str | None = None, symbol: str | None = None) -> list:
    results = sorted(_trades.values(), key=lambda t: t["id"])
    if direction:
        results = [t for t in results if t["direction"] == direction]
    if symbol:
        results = [t for t in results if t["symbol"] == symbol.upper()]
    return results[-limit:]


def get_trade(trade_id: int) -> dict:
    trade = _trades.get(trade_id)
    if trade is None:
        raise TradeNotFoundError(f"Trade {trade_id} not found")
    return trade


def update_trade(trade_id: int, changes: dict) -> dict:
    trade = get_trade(trade_id)
    trade.update(changes)
    trade["pnl"] = calculate_pnl(
        trade["entry_price"], trade["exit_price"], trade["quantity"], trade["direction"]
    )
    return trade


def replace_trade(trade_id: int, data: dict) -> dict:
    existing = get_trade(trade_id)
    record = dict(data)
    record["id"] = trade_id
    record["created_at"] = existing["created_at"]
    record["pnl"] = calculate_pnl(
        record["entry_price"], record["exit_price"], record["quantity"], record["direction"]
    )
    _trades[trade_id] = record
    return record


def delete_trade(trade_id: int) -> None:
    get_trade(trade_id)
    del _trades[trade_id]
