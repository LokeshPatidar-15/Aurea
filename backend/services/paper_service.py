from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from analysis.indicators import atr
from database import SessionLocal
from models import PriceHistory
from models.paper import PaperFill, PaperPosition
from services import paper_engine as engine
from services.prediction_service import (
    INTERVAL_MINUTES,
    SUPPORTED_SYMBOLS,
    NotEnoughDataError,
    UnsupportedSymbolError,
    load_recent_candles,
)

LIMITS = engine.Limits()
SIDES = {"long": 1, "short": -1}
NAMES = {1: "long", -1: "short"}


class OrderRejected(Exception):
    def __init__(self, reasons: list, position_id: int):
        super().__init__(", ".join(reasons))
        self.reasons = reasons
        self.position_id = position_id


class OrderNotFound(Exception):
    pass


class OrderNotCancellable(Exception):
    pass


def to_dict(row: PaperPosition) -> dict:
    out = {column.name: getattr(row, column.name) for column in PaperPosition.__table__.columns}
    out["stop_price"] = float(out["stop_price"])
    return out


def median_atr_bps(candles) -> float:
    values = atr(candles["high"], candles["low"], candles["close"], 14) / candles["close"] * 10_000
    values = values.dropna().tail(300)
    return float(values.median()) if len(values) else 0.0


def load_state(session):
    rows = session.execute(select(PaperPosition)).scalars().all()
    closed = [(r.exit_time, r.net_pnl) for r in rows if r.status == "closed" and r.exit_time is not None]
    live = [r for r in rows if r.status in ("pending", "open")]
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    equity, peak, today = engine.equity_state(closed, today_start)
    return equity, peak, today, live, rows


def create_order(symbol: str, timeframe: str, side: str, stop_price: float, rr: float, source: str) -> dict:
    symbol = symbol.upper()
    if symbol not in SUPPORTED_SYMBOLS:
        raise UnsupportedSymbolError(f"unsupported symbol {symbol!r}. Supported: {', '.join(SUPPORTED_SYMBOLS)}")
    if timeframe not in INTERVAL_MINUTES:
        raise UnsupportedSymbolError(f"unsupported timeframe {timeframe!r}")
    candles = load_recent_candles(symbol, timeframe, 400)
    last_time = candles.index[-1]
    reference = float(candles["close"].iloc[-1])
    interval_minutes = INTERVAL_MINUTES[timeframe]
    closes_at = last_time.to_pydatetime() + timedelta(minutes=interval_minutes)
    age_minutes = max((datetime.now(timezone.utc) - closes_at).total_seconds() / 60, 0.0)
    stale = age_minutes > 2 * interval_minutes
    atr_bps = median_atr_bps(candles)

    with SessionLocal() as session:
        equity, peak, today, live, _ = load_state(session)
        verdict = engine.check_order(
            side=SIDES[side], symbol=symbol, reference_price=reference, stop=stop_price, equity=equity,
            peak_equity=peak, realized_today=today,
            open_positions=[{"symbol": r.symbol, "notional": r.notional or 0.0} for r in live],
            atr_bps=atr_bps, stale=stale, limits=LIMITS,
        )
        size = verdict["size"]
        row = PaperPosition(
            symbol=symbol, timeframe=timeframe, side=side, status="pending" if verdict["approved"] else "rejected",
            source=source, signal_time=last_time.to_pydatetime(), stop_price=stop_price, rr=rr, max_bars=LIMITS.max_bars,
            notional=size["notional"] if size else None, quantity=size["quantity"] if size else None,
            risk_amount=size["risk_amount"] if size else None,
            reject_reason=", ".join(verdict["reasons"]) or None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        if not verdict["approved"]:
            raise OrderRejected(verdict["reasons"], row.id)
        return to_dict(row)


def cancel_order(position_id: int) -> dict:
    with SessionLocal() as session:
        row = session.get(PaperPosition, position_id)
        if row is None:
            raise OrderNotFound(f"order {position_id} not found")
        if row.status != "pending":
            raise OrderNotCancellable(f"order {position_id} is {row.status}; only pending orders can be cancelled")
        row.status = "cancelled"
        session.commit()
        session.refresh(row)
        return to_dict(row)


def list_positions(status: str | None = None, limit: int = 100) -> list:
    with SessionLocal() as session:
        stmt = select(PaperPosition).order_by(PaperPosition.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(PaperPosition.status == status)
        return [to_dict(r) for r in session.execute(stmt).scalars().all()]


def tick() -> dict:
    stats = {"processed_candles": 0, "filled": 0, "closed": 0, "rejected": 0}
    with SessionLocal() as session:
        rows = session.execute(
            select(PaperPosition).where(PaperPosition.status.in_(("pending", "open"))).order_by(PaperPosition.id)
        ).scalars().all()
        for row in rows:
            after = row.last_candle_time or row.signal_time
            candles = session.execute(
                select(PriceHistory.open_time, PriceHistory.open, PriceHistory.high, PriceHistory.low, PriceHistory.close)
                .where(PriceHistory.symbol == row.symbol, PriceHistory.timeframe == row.timeframe, PriceHistory.open_time > after)
                .order_by(PriceHistory.open_time)
            ).all()
            if not candles:
                continue
            session.flush()
            equity = load_state(session)[0]
            pos = engine.PaperPos(
                side=SIDES[row.side], stop=row.stop_price, rr=row.rr, max_bars=row.max_bars, status=row.status,
                entry=row.entry_price, entry_time=row.entry_time, target=row.target_price, notional=row.notional,
                quantity=row.quantity, risk_amount=row.risk_amount, bars_seen=row.bars_seen,
            )
            for c in candles:
                events = engine.apply_candle(pos, {"time": c.open_time, "open": c.open, "high": c.high, "low": c.low, "close": c.close}, equity, LIMITS)
                stats["processed_candles"] += 1
                stats["filled"] += events.count("filled")
                stats["closed"] += events.count("closed")
                stats["rejected"] += events.count("rejected")
                row.last_candle_time = c.open_time
                if pos.status in ("closed", "rejected"):
                    break
            row.status, row.entry_time, row.entry_price, row.target_price = pos.status, pos.entry_time, pos.entry, pos.target
            row.notional, row.quantity, row.risk_amount, row.bars_seen = pos.notional, pos.quantity, pos.risk_amount, pos.bars_seen
            row.exit_time, row.exit_price, row.exit_reason = pos.exit_time, pos.exit_price, pos.exit_reason
            row.gross_pnl, row.fees, row.net_pnl, row.reject_reason = pos.gross_pnl, pos.fees, pos.net_pnl, pos.reject_reason
            for fill in pos.fills:
                session.add(PaperFill(position_id=row.id, kind=fill["kind"], price=fill["price"], quantity=fill["quantity"], fee=fill["fee"], executed_at=fill["time"]))
        session.commit()
    return stats


def summary() -> dict:
    with SessionLocal() as session:
        equity, peak, today, live, rows = load_state(session)
        open_rows = []
        unrealized = 0.0
        for r in live:
            if r.status != "open":
                continue
            last = session.execute(
                select(PriceHistory.close).where(PriceHistory.symbol == r.symbol, PriceHistory.timeframe == r.timeframe)
                .order_by(PriceHistory.open_time.desc()).limit(1)
            ).scalar_one_or_none()
            pnl = SIDES[r.side] * (last - r.entry_price) / r.entry_price * r.notional if last is not None else None
            unrealized += pnl or 0.0
            open_rows.append({"id": r.id, "symbol": r.symbol, "side": r.side, "status": r.status, "entry_price": r.entry_price, "last_price": last, "unrealized_pnl": pnl})
        closed = [r for r in rows if r.status == "closed"]
        wins = sum(1 for r in closed if (r.net_pnl or 0) > 0)
        drawdown = (peak - equity) / peak if peak > 0 else 0.0
        return {
            "start_equity": engine.START_EQUITY, "realized_equity": equity, "unrealized_pnl": unrealized,
            "equity_with_open": equity + unrealized, "peak_equity": peak, "drawdown": drawdown,
            "realized_today": today, "closed_trades": len(closed), "win_rate": (wins / len(closed)) if closed else None,
            "pending_orders": sum(1 for r in live if r.status == "pending"), "open_positions": open_rows,
            "drawdown_halt": drawdown >= LIMITS.max_drawdown_halt,
            "daily_loss_limit_hit": today <= -LIMITS.daily_loss_limit * (equity - today),
        }


def tradability_report() -> list:
    out = []
    for symbol in SUPPORTED_SYMBOLS:
        candles = load_recent_candles(symbol, "1h", 500)
        atr_bps = median_atr_bps(candles)
        screen = engine.tradability(LIMITS.cost_bps, atr_bps, LIMITS.max_cost_to_atr)
        out.append({"symbol": symbol, "last_close": float(candles["close"].iloc[-1]), "atr_bps": atr_bps,
                    "cost_bps": LIMITS.cost_bps, "cost_to_atr": screen["cost_to_atr"] if screen["cost_to_atr"] != float("inf") else 999.0,
                    "tradable": screen["tradable"]})
    return out
