import math
from datetime import datetime, timedelta, timezone

START_EQUITY = 10_000.0
PERIODS = ("day", "week", "month")
GROUP_KEYS = ("symbol", "side", "source", "exit_reason")
SIDES = {"long": 1, "short": -1}
STALE_MARK_HOURS = 3.0
THIN_GROUP_TRADES = 10
MAX_BUCKET_LOOPS = 20_000


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _f(value) -> float:
    return _num(value) or 0.0


def closed_rows(trades: list) -> list:
    rows = [t for t in trades if t.get("exit_time") is not None and _num(t.get("net_pnl")) is not None]
    return sorted(rows, key=lambda t: (_utc(t["exit_time"]), t.get("id", 0)))


def bucket_start(dt: datetime, period: str) -> datetime:
    day = _utc(dt).replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "day":
        return day
    if period == "week":
        return day - timedelta(days=day.weekday())
    if period == "month":
        return day.replace(day=1)
    raise ValueError("period must be day, week or month")


def next_bucket(start: datetime, period: str) -> datetime:
    if period == "day":
        return start + timedelta(days=1)
    if period == "week":
        return start + timedelta(days=7)
    if period == "month":
        return start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1)
    raise ValueError("period must be day, week or month")


def pnl_by_period(trades: list, period: str = "day", limit: int = 90, start_equity: float = START_EQUITY) -> list:
    if period not in PERIODS:
        raise ValueError("period must be day, week or month")
    rows = closed_rows(trades)
    if not rows:
        return []
    buckets: dict = {}
    for r in rows:
        b = buckets.setdefault(bucket_start(r["exit_time"], period), {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "gross_pnl": 0.0, "fees": 0.0})
        net = _f(r["net_pnl"])
        b["trades"] += 1
        b["wins"] += 1 if net > 0 else 0
        b["losses"] += 1 if net < 0 else 0
        b["net_pnl"] += net
        b["gross_pnl"] += _f(r.get("gross_pnl"))
        b["fees"] += _f(r.get("fees"))
    first, last = min(buckets), max(buckets)
    out = []
    cursor, cumulative, loops = first, 0.0, 0
    while cursor <= last and loops < MAX_BUCKET_LOOPS:
        b = buckets.get(cursor) or {"trades": 0, "wins": 0, "losses": 0, "net_pnl": 0.0, "gross_pnl": 0.0, "fees": 0.0}
        cumulative += b["net_pnl"]
        out.append({"period_start": cursor, **b, "cumulative_pnl": cumulative, "equity_end": start_equity + cumulative})
        cursor = next_bucket(cursor, period)
        loops += 1
    return out[-max(1, limit):]


def journal_row(t: dict) -> dict:
    net = _f(t.get("net_pnl"))
    risk = _num(t.get("risk_amount"))
    notional = _num(t.get("notional"))
    fees = _num(t.get("fees"))
    entry, exit_ = t.get("entry_time"), t.get("exit_time")
    hold = (_utc(exit_) - _utc(entry)).total_seconds() / 3600 if entry is not None and exit_ is not None else None
    return {
        "id": t.get("id"),
        "symbol": t.get("symbol"),
        "side": t.get("side"),
        "source": t.get("source"),
        "entry_time": entry,
        "entry_price": _num(t.get("entry_price")),
        "exit_time": exit_,
        "exit_price": _num(t.get("exit_price")),
        "exit_reason": t.get("exit_reason"),
        "notional": notional,
        "risk_amount": risk,
        "gross_pnl": _num(t.get("gross_pnl")),
        "fees": fees,
        "net_pnl": net,
        "outcome": "win" if net > 0 else "loss" if net < 0 else "flat",
        "r_multiple": net / risk if risk and risk > 0 else None,
        "hold_hours": hold,
        "bars_held": t.get("bars_seen"),
        "cost_bps": fees / notional * 10_000 if fees is not None and notional and notional > 0 else None,
    }


def journal(trades: list) -> list:
    return [journal_row(t) for t in reversed(closed_rows(trades))]


def breakdown(trades: list, by: str) -> dict:
    if by not in GROUP_KEYS:
        raise ValueError("by must be one of " + ", ".join(GROUP_KEYS))
    rows = closed_rows(trades)
    groups: dict = {}
    for r in rows:
        groups.setdefault(r.get(by) or "unknown", []).append(r)
    out = []
    for name, part in groups.items():
        nets = [_f(r["net_pnl"]) for r in part]
        wins = [x for x in nets if x > 0]
        losses = [x for x in nets if x < 0]
        rs = [x["r_multiple"] for x in (journal_row(r) for r in part) if x["r_multiple"] is not None]
        out.append(
            {
                "name": name,
                "trades": len(part),
                "share_of_trades": len(part) / len(rows),
                "wins": len(wins),
                "win_rate": len(wins) / len(part),
                "net_pnl": sum(nets),
                "gross_pnl": sum(_f(r.get("gross_pnl")) for r in part),
                "fees": sum(_f(r.get("fees")) for r in part),
                "avg_net_pnl": sum(nets) / len(part),
                "avg_r": sum(rs) / len(rs) if rs else None,
                "profit_factor": sum(wins) / -sum(losses) if losses else None,
                "thin": len(part) < THIN_GROUP_TRADES,
            }
        )
    out.sort(key=lambda g: (-g["trades"], g["name"]))
    return {"by": by, "total_trades": len(rows), "groups": out, "note": f"Groups with fewer than {THIN_GROUP_TRADES} trades are marked thin: their numbers are noise, not skill."}


def mark_position(row: dict, last_price, mark_time, now: datetime) -> dict:
    side = SIDES.get(row.get("side"), 0)
    entry, notional, risk = _num(row.get("entry_price")), _num(row.get("notional")), _num(row.get("risk_amount"))
    last = _num(last_price)
    pnl = side * (last - entry) / entry * notional if last is not None and entry and entry > 0 and notional is not None else None
    age_h = (_utc(now) - _utc(mark_time)).total_seconds() / 3600 if mark_time is not None else None
    return {
        "id": row.get("id"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "entry_price": entry,
        "last_price": last,
        "mark_time": mark_time,
        "mark_stale": age_h is None or age_h > STALE_MARK_HOURS,
        "notional": notional,
        "risk_amount": risk,
        "stop_price": _num(row.get("stop_price")),
        "target_price": _num(row.get("target_price")),
        "unrealized_pnl": pnl,
        "unrealized_pct": pnl / notional if pnl is not None and notional else None,
        "unrealized_r": pnl / risk if pnl is not None and risk and risk > 0 else None,
    }


def exposure(open_positions: list, live_count: int, equity: float, max_gross: float, max_positions: int) -> dict:
    by_symbol: dict = {}
    long_n = short_n = 0.0
    for p in open_positions:
        n = _f(p.get("notional"))
        slot = by_symbol.setdefault(p["symbol"], {"long": 0.0, "short": 0.0})
        if p.get("side") == "long":
            slot["long"] += n
            long_n += n
        else:
            slot["short"] += n
            short_n += n
    gross = long_n + short_n
    gross_pct = gross / equity if equity > 0 else None
    return {
        "gross_notional": gross,
        "long_notional": long_n,
        "short_notional": short_n,
        "net_notional": long_n - short_n,
        "gross_pct_of_equity": gross_pct,
        "max_gross_pct": max_gross,
        "headroom_pct": max_gross - gross_pct if gross_pct is not None else None,
        "slots_used": live_count,
        "slots_max": max_positions,
        "by_symbol": {s: {**v, "net": v["long"] - v["short"], "gross": v["long"] + v["short"]} for s, v in sorted(by_symbol.items())},
    }


def equity_curve(trades: list, start: float = START_EQUITY) -> list:
    rows = closed_rows(trades)
    if not rows:
        return []
    points = [{"time": rows[0].get("entry_time") or rows[0]["exit_time"], "equity": start, "drawdown": 0.0, "position_id": None}]
    equity, peak = start, start
    for t in rows:
        equity += _f(t["net_pnl"])
        peak = max(peak, equity)
        points.append({"time": t["exit_time"], "equity": equity, "drawdown": (peak - equity) / peak if peak > 0 else 0.0, "position_id": t.get("id")})
    return points


def underwater(curve: list, now: datetime) -> dict:
    if not curve:
        return {"points": 0, "peak_equity": None, "peak_time": None, "current_equity": None, "current_drawdown": 0.0, "current_drawdown_usd": 0.0,
                "max_drawdown": 0.0, "max_drawdown_time": None, "underwater_now": False, "days_underwater": 0.0, "longest_underwater_days": 0.0}
    now = _utc(now)
    peak = curve[0]["equity"]
    peak_time = _utc(curve[0]["time"])
    max_dd, max_dd_time = 0.0, None
    under_since = None
    longest = timedelta(0)
    for p in curve[1:]:
        t = _utc(p["time"])
        eq = p["equity"]
        if eq >= peak:
            if under_since is not None:
                longest = max(longest, t - under_since)
                under_since = None
            peak, peak_time = eq, t
        else:
            if under_since is None:
                under_since = peak_time
            dd = (peak - eq) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd, max_dd_time = dd, t
    last_eq = curve[-1]["equity"]
    current = max(0.0, (peak - last_eq) / peak) if peak > 0 else 0.0
    current_for = timedelta(0)
    if under_since is not None:
        current_for = max(timedelta(0), now - under_since)
        longest = max(longest, current_for)
    return {
        "points": len(curve),
        "peak_equity": peak,
        "peak_time": peak_time,
        "current_equity": last_eq,
        "current_drawdown": current,
        "current_drawdown_usd": max(0.0, peak - last_eq),
        "max_drawdown": max_dd,
        "max_drawdown_time": max_dd_time,
        "underwater_now": under_since is not None,
        "days_underwater": current_for.total_seconds() / 86400,
        "longest_underwater_days": longest.total_seconds() / 86400,
    }


def daily_limit(today_realized: float, realized_equity: float, limit_pct: float) -> dict:
    start_of_day = realized_equity - today_realized
    limit_usd = limit_pct * start_of_day
    used = max(0.0, -today_realized) / limit_usd if limit_usd > 0 else None
    return {"realized_today": today_realized, "limit_pct": limit_pct, "limit_usd": limit_usd, "used_pct": used, "hit": today_realized <= -limit_usd if limit_usd > 0 else False}


def build_overview(closed: list, open_rows: list, pending_count: int, now: datetime, limits: dict, start_equity: float = START_EQUITY) -> dict:
    now = _utc(now)
    rows = closed_rows(closed)
    realized_pnl = sum(_f(r["net_pnl"]) for r in rows)
    realized_equity = start_equity + realized_pnl
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = sum(_f(r["net_pnl"]) for r in rows if _utc(r["exit_time"]) >= today_start)
    marked = [p for p in open_rows]
    known = [p["unrealized_pnl"] for p in marked if p["unrealized_pnl"] is not None]
    unrealized = sum(known)
    equity_with_open = realized_equity + unrealized
    curve = equity_curve(rows, start_equity)
    water = underwater(curve, now)
    dd_halt = water["current_drawdown"] >= limits["max_drawdown_halt"]
    daily = daily_limit(today, realized_equity, limits["daily_loss_limit"])
    return {
        "as_of": now,
        "start_equity": start_equity,
        "realized_equity": realized_equity,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized,
        "equity_with_open": equity_with_open,
        "total_pnl": equity_with_open - start_equity,
        "total_return_pct": (equity_with_open - start_equity) / start_equity,
        "closed_trades": len(rows),
        "pending_orders": pending_count,
        "open_positions": marked,
        "marks_missing": len(marked) - len(known),
        "marks_stale": sum(1 for p in marked if p["mark_stale"]),
        "exposure": exposure(marked, pending_count + len(marked), realized_equity, limits["max_gross_exposure"], limits["max_open_positions"]),
        "drawdown": water,
        "daily_limit": daily,
        "halts": {"drawdown_halt": dd_halt, "max_drawdown_halt": limits["max_drawdown_halt"], "daily_loss_limit_hit": daily["hit"], "new_orders_blocked": dd_halt or daily["hit"]},
        "next_trade_risk_usd": realized_equity * limits["risk_per_trade"],
        "mark_price_source": "last_closed_1h_candle",
        "unrealized_includes_exit_costs": False,
        "research_only": True,
    }
