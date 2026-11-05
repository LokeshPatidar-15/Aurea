import time
from datetime import datetime, timedelta, timezone

from services import paper_service, strategy_service

INTERVAL_MS = 3_600_000
INGEST_HOURS = 48
RUN_OFFSET_SECONDS = 60
LAST_RUN: dict = {}


def seconds_until_next_run(now: datetime, offset_seconds: int = RUN_OFFSET_SECONDS) -> float:
    this_hour = now.replace(minute=0, second=0, microsecond=0)
    target = this_hour + timedelta(seconds=offset_seconds)
    if now >= target:
        target = this_hour + timedelta(hours=1, seconds=offset_seconds)
    return (target - now).total_seconds()


def decide(signal: dict, already_ordered: bool, place_orders: bool) -> tuple[str, str]:
    if signal["status"] != "signal":
        return "skip", signal["reason"]
    if already_ordered:
        return "skip", "already_ordered_for_this_candle"
    if not place_orders:
        return "skip", "orders_disabled"
    return "order", "setup_confirmed"


def ingest_recent(symbols, hours: int = INGEST_HOURS) -> dict:
    from database import SessionLocal
    from services.binance_history import HistoryError, fetch_range
    from services.history_store import upsert_candles

    end_ms = int(time.time() * 1000)
    end_ms -= end_ms % INTERVAL_MS
    start_ms = end_ms - hours * INTERVAL_MS
    out = {}
    for symbol in symbols:
        try:
            candles = fetch_range(symbol, "1h", start_ms, end_ms)
            with SessionLocal() as session:
                out[symbol] = {"fetched": len(candles), "inserted": upsert_candles(session, symbol, "1h", candles) if candles else 0}
        except HistoryError as exc:
            out[symbol] = {"error": str(exc)}
    return out


def _already_ordered(symbol: str, signal_time) -> bool:
    from sqlalchemy import select

    from database import SessionLocal
    from models.paper import PaperPosition

    with SessionLocal() as session:
        stmt = select(PaperPosition.id).where(
            PaperPosition.symbol == symbol, PaperPosition.signal_time == signal_time, PaperPosition.source == strategy_service.STRATEGY_NAME
        ).limit(1)
        return session.execute(stmt).first() is not None


def run_cycle(ingest: bool = True, place_orders: bool = True, symbols=None) -> dict:
    symbols = list(symbols or paper_service.SUPPORTED_SYMBOLS)
    log = {"started_at": datetime.now(timezone.utc), "ingest": None, "tick": None, "symbols": {}, "errors": []}
    if ingest:
        log["ingest"] = ingest_recent(symbols)
        log["errors"] += [f"ingest {s}: {r['error']}" for s, r in log["ingest"].items() if "error" in r]
    try:
        log["tick"] = paper_service.tick()
    except Exception as exc:
        log["errors"].append(f"tick: {exc}")
    for symbol in symbols:
        entry = {"signal": None, "action": "skip", "why": None, "position_id": None}
        try:
            sig = strategy_service.latest_signal(symbol)
            entry["signal"] = f"{sig['status']}:{sig['side']}"
            ordered = _already_ordered(symbol, sig["as_of"]) if sig["status"] == "signal" else False
            action, why = decide(sig, ordered, place_orders)
            entry["action"], entry["why"] = action, why
            if action == "order":
                try:
                    pos = paper_service.create_order(symbol, "1h", sig["side"], sig["stop_price"], sig["rr"], strategy_service.STRATEGY_NAME)
                    entry["position_id"] = pos["id"]
                except paper_service.OrderRejected as exc:
                    entry["action"], entry["why"], entry["position_id"] = "rejected", ", ".join(exc.reasons), exc.position_id
        except Exception as exc:
            entry["action"], entry["why"] = "error", str(exc)[:200]
            log["errors"].append(f"{symbol}: {exc}")
        log["symbols"][symbol] = entry
    log["finished_at"] = datetime.now(timezone.utc)
    LAST_RUN.clear()
    LAST_RUN.update(log)
    return log


def format_cycle(log: dict) -> str:
    tick = log.get("tick") or {}
    parts = [f"{log['finished_at']:%Y-%m-%d %H:%M:%S}Z", f"tick f{tick.get('filled', 0)}/c{tick.get('closed', 0)}"]
    parts += [f"{s}:{e['action']}({e['why']})" for s, e in log["symbols"].items()]
    if log["errors"]:
        parts.append(f"ERRORS {len(log['errors'])}")
    return " | ".join(parts)
