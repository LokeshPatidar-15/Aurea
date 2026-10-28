import math
from dataclasses import dataclass, field
from datetime import datetime

START_EQUITY = 10_000.0


@dataclass(frozen=True)
class Limits:
    risk_per_trade: float = 0.01
    max_leverage: float = 1.0
    max_open_positions: int = 3
    max_positions_per_symbol: int = 1
    max_gross_exposure: float = 1.5
    daily_loss_limit: float = 0.03
    max_drawdown_halt: float = 0.15
    max_cost_to_atr: float = 0.5
    cost_bps: float = 20.0
    max_bars: int = 24


@dataclass
class PaperPos:
    side: int
    stop: float
    rr: float = 2.0
    max_bars: int = 24
    status: str = "pending"
    entry: float | None = None
    entry_time: datetime | None = None
    target: float | None = None
    notional: float | None = None
    quantity: float | None = None
    risk_amount: float | None = None
    bars_seen: int = 0
    exit_price: float | None = None
    exit_time: datetime | None = None
    exit_reason: str | None = None
    gross_pnl: float | None = None
    fees: float | None = None
    net_pnl: float | None = None
    reject_reason: str | None = None
    fills: list = field(default_factory=list)


def tradability(cost_bps: float, atr_bps: float, max_ratio: float) -> dict:
    ratio = cost_bps / atr_bps if atr_bps and atr_bps > 0 else math.inf
    return {"cost_bps": cost_bps, "atr_bps": atr_bps, "cost_to_atr": ratio, "tradable": bool(ratio <= max_ratio)}


def position_size(equity: float, entry: float, stop: float, side: int, limits: Limits):
    risk = side * (entry - stop)
    if not (math.isfinite(risk) and math.isfinite(entry)) or risk <= 0 or entry <= 0:
        return None
    risk_pct = risk / entry
    wanted = limits.risk_per_trade / risk_pct
    fraction = min(wanted, limits.max_leverage)
    notional = equity * fraction
    return {
        "notional": notional,
        "quantity": notional / entry,
        "risk_amount": notional * risk_pct,
        "risk_pct": risk_pct,
        "capped": bool(wanted > limits.max_leverage),
    }


def equity_state(closed: list, today_start: datetime, start: float = START_EQUITY):
    equity, peak, today = start, start, 0.0
    for when, pnl in sorted(closed, key=lambda item: item[0]):
        equity += pnl
        peak = max(peak, equity)
        if when >= today_start:
            today += pnl
    return equity, peak, today


def check_order(side: int, symbol: str, reference_price: float, stop: float, equity: float, peak_equity: float,
                realized_today: float, open_positions: list, atr_bps: float, stale: bool, limits: Limits = Limits()) -> dict:
    reasons = []
    size = position_size(equity, reference_price, stop, side, limits)
    if size is None:
        reasons.append("invalid_stop")
    if stale:
        reasons.append("stale_data")
    if peak_equity > 0 and (peak_equity - equity) / peak_equity >= limits.max_drawdown_halt:
        reasons.append("drawdown_halt")
    day_start_equity = equity - realized_today
    if day_start_equity > 0 and realized_today <= -limits.daily_loss_limit * day_start_equity:
        reasons.append("daily_loss_limit")
    if len(open_positions) >= limits.max_open_positions:
        reasons.append("max_open_positions")
    if sum(1 for p in open_positions if p["symbol"] == symbol) >= limits.max_positions_per_symbol:
        reasons.append("symbol_already_open")
    if size is not None:
        gross = sum(p.get("notional") or 0.0 for p in open_positions) + size["notional"]
        if equity > 0 and gross / equity > limits.max_gross_exposure:
            reasons.append("gross_exposure_limit")
    screen = tradability(limits.cost_bps, atr_bps, limits.max_cost_to_atr)
    if not screen["tradable"]:
        reasons.append(f"not_tradable_cost_{screen['cost_to_atr']:.1f}_atr")
    return {"approved": not reasons, "reasons": reasons, "size": size}


def _close(pos: PaperPos, price: float, when, reason: str, limits: Limits) -> None:
    gross = pos.side * (price - pos.entry) / pos.entry * pos.notional
    half_fee = pos.notional * limits.cost_bps / 2 / 10_000
    pos.exit_price, pos.exit_time, pos.exit_reason = price, when, reason
    pos.gross_pnl = gross
    pos.fees = 2 * half_fee
    pos.net_pnl = gross - pos.fees
    pos.status = "closed"
    pos.fills.append({"kind": "exit", "price": price, "quantity": pos.quantity, "fee": half_fee, "time": when})


def apply_candle(pos: PaperPos, candle: dict, equity: float, limits: Limits = Limits()) -> list:
    events = []
    if pos.status == "pending":
        entry = float(candle["open"])
        size = position_size(equity, entry, pos.stop, pos.side, limits)
        if size is None:
            pos.status, pos.reject_reason = "rejected", "stop_on_wrong_side_at_fill"
            return ["rejected"]
        pos.entry, pos.entry_time = entry, candle["time"]
        pos.notional, pos.quantity, pos.risk_amount = size["notional"], size["quantity"], size["risk_amount"]
        risk = pos.side * (entry - pos.stop)
        pos.target = entry + pos.side * pos.rr * risk
        pos.status, pos.bars_seen = "open", 0
        pos.fills.append({"kind": "entry", "price": entry, "quantity": pos.quantity, "fee": pos.notional * limits.cost_bps / 2 / 10_000, "time": candle["time"]})
        events.append("filled")
    elif pos.status != "open":
        return events

    first = pos.bars_seen == 0
    price = reason = None
    if pos.side == 1:
        gapped = (not first) and candle["open"] <= pos.stop
        if gapped or candle["low"] <= pos.stop:
            price, reason = (float(candle["open"]) if gapped else pos.stop), "stop"
        elif candle["high"] >= pos.target:
            price, reason = pos.target, "target"
    else:
        gapped = (not first) and candle["open"] >= pos.stop
        if gapped or candle["high"] >= pos.stop:
            price, reason = (float(candle["open"]) if gapped else pos.stop), "stop"
        elif candle["low"] <= pos.target:
            price, reason = pos.target, "target"
    pos.bars_seen += 1
    if reason is None and pos.bars_seen >= pos.max_bars:
        price, reason = float(candle["close"]), "time"
    if reason:
        _close(pos, price, candle["time"], reason, limits)
        events.append("closed")
    return events
