import numpy as np

START_EQUITY = 10_000.0
MIN_TRADES_FOR_CONFIDENCE = 30
MIN_TRADES_FOR_INTERVAL = 10
BOOTSTRAP_RUNS = 2000


def _sorted_closed(trades: list) -> list:
    rows = [t for t in trades if t.get("exit_time") is not None and t.get("net_pnl") is not None]
    return sorted(rows, key=lambda t: (t["exit_time"], t.get("id", 0)))


def equity_curve(trades: list, start: float = START_EQUITY) -> list:
    rows = _sorted_closed(trades)
    if not rows:
        return []
    points = [{"time": rows[0].get("entry_time") or rows[0]["exit_time"], "equity": start, "drawdown": 0.0, "position_id": None}]
    equity, peak = start, start
    for t in rows:
        equity += t["net_pnl"]
        peak = max(peak, equity)
        points.append({"time": t["exit_time"], "equity": equity, "drawdown": (peak - equity) / peak if peak > 0 else 0.0, "position_id": t.get("id")})
    return points


def r_interval(r_values: np.ndarray, runs: int = BOOTSTRAP_RUNS, seed: int = 0) -> tuple | None:
    if len(r_values) < MIN_TRADES_FOR_INTERVAL:
        return None
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(r_values), size=(runs, len(r_values)))
    means = r_values[picks].mean(axis=1)
    return float(np.percentile(means, 5)), float(np.percentile(means, 95))


def longest_streak(flags: list) -> int:
    best = run = 0
    for flag in flags:
        run = run + 1 if flag else 0
        best = max(best, run)
    return best


def _group(rows: list, key: str) -> dict:
    out = {}
    for name in sorted({r[key] for r in rows}):
        part = [r for r in rows if r[key] == name]
        pnl = np.array([r["net_pnl"] for r in part])
        out[name] = {"trades": len(part), "net_pnl": float(pnl.sum()), "win_rate": float((pnl > 0).mean())}
    return out


def performance(trades: list, start: float = START_EQUITY) -> dict:
    rows = _sorted_closed(trades)
    n = len(rows)
    if n == 0:
        return {"trades": 0, "start_equity": start, "end_equity": start, "sample_warning": "No closed trades yet."}
    pnl = np.array([r["net_pnl"] for r in rows], dtype=float)
    gross = np.array([r["gross_pnl"] or 0.0 for r in rows], dtype=float)
    fees = np.array([r["fees"] or 0.0 for r in rows], dtype=float)
    risk = np.array([r["risk_amount"] or np.nan for r in rows], dtype=float)
    r_values = pnl / risk
    r_values = r_values[np.isfinite(r_values)]
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    curve = equity_curve(rows, start)
    equities = np.array([p["equity"] for p in curve])
    peaks = np.maximum.accumulate(equities)
    drawdowns = (peaks - equities) / peaks
    deepest = int(np.argmax(drawdowns))
    interval = r_interval(r_values)
    gross_total = float(gross.sum())
    reasons = {}
    for r in rows:
        reasons[r["exit_reason"]] = reasons.get(r["exit_reason"], 0) + 1
    out = {
        "trades": n,
        "start_equity": start,
        "end_equity": float(equities[-1]),
        "net_pnl": float(pnl.sum()),
        "return_pct": float(pnl.sum() / start),
        "win_rate": float((pnl > 0).mean()),
        "avg_win": float(wins.mean()) if len(wins) else None,
        "avg_loss": float(losses.mean()) if len(losses) else None,
        "payoff_ratio": float(wins.mean() / -losses.mean()) if len(wins) and len(losses) else None,
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else None,
        "expectancy_usd": float(pnl.mean()),
        "expectancy_r": float(r_values.mean()) if len(r_values) else None,
        "expectancy_r_low": interval[0] if interval else None,
        "expectancy_r_high": interval[1] if interval else None,
        "gross_pnl": gross_total,
        "fees": float(fees.sum()),
        "fees_share_of_gross": float(fees.sum() / abs(gross_total)) if abs(gross_total) > 1e-9 else None,
        "max_drawdown": float(drawdowns[deepest]),
        "max_drawdown_usd": float(peaks[deepest] - equities[deepest]),
        "current_drawdown": float(drawdowns[-1]),
        "longest_losing_streak": longest_streak([p < 0 for p in pnl]),
        "avg_bars_held": float(np.mean([r.get("bars_seen") or 0 for r in rows])),
        "exit_reasons": reasons,
        "by_symbol": _group(rows, "symbol"),
        "by_side": _group(rows, "side"),
        "sample_warning": None,
    }
    if n < MIN_TRADES_FOR_CONFIDENCE:
        out["sample_warning"] = f"Only {n} closed trades. Fewer than {MIN_TRADES_FOR_CONFIDENCE} trades say almost nothing about edge: treat every number here as noise."
    elif interval and interval[0] <= 0 <= interval[1]:
        out["sample_warning"] = "The 90% interval for expectancy (in R) includes zero: the result cannot be told apart from luck."
    return out
