import math
import statistics
from datetime import datetime, timezone
from statistics import NormalDist

HOUR_MS = 3_600_000
HORIZONS = (1, 4, 24)
COST_BPS = 20.0
MIN_EFFECTIVE_N = 30
KINDS = ("rule", "model")
RULE_DIRECTION = {"long": 1, "short": -1}
MODEL_DIRECTION = {"buy": 1, "sell": -1, "hold": 0}
Z_90 = NormalDist().inv_cdf(0.95)


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def to_ms(value) -> int | None:
    if isinstance(value, datetime):
        value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return int(value.timestamp() * 1000)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def from_ms(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def _row(symbol, kind, candle_ms, direction, signal, status, confidence, reference_price) -> dict:
    return {
        "symbol": symbol,
        "timeframe": "1h",
        "kind": kind,
        "candle_time": from_ms(candle_ms),
        "direction": direction,
        "signal": signal,
        "status": status,
        "confidence": _num(confidence),
        "reference_price": _num(reference_price),
        "source": "pipeline",
    }


def rows_from_event(event) -> list:
    if not isinstance(event, dict) or event.get("fresh") is not True or event.get("timeframe") != "1h":
        return []
    symbol, candle = event.get("symbol"), event.get("candle_time")
    if not isinstance(symbol, str) or isinstance(candle, bool) or not isinstance(candle, int) or candle <= 0:
        return []
    rows = []
    rule = event.get("rule")
    if isinstance(rule, dict) and rule.get("as_of") == candle:
        status, side = rule.get("status"), rule.get("side")
        direction = RULE_DIRECTION.get(side, 0) if status == "signal" else 0
        rows.append(_row(symbol, "rule", candle, direction, side if direction else "none", status, None, rule.get("reference_price")))
    model = event.get("model")
    if isinstance(model, dict) and model.get("as_of") == candle and model.get("signal") in MODEL_DIRECTION:
        signal = model["signal"]
        rows.append(_row(symbol, "model", candle, MODEL_DIRECTION[signal], signal, None, model.get("confidence"), None))
    return rows


def candle_index(candles: list) -> tuple:
    index = {}
    latest = 0
    for open_ms, open_, close in candles:
        o, c = _num(open_), _num(close)
        if isinstance(open_ms, int) and o and o > 0 and c is not None:
            index[open_ms] = (o, c)
            latest = max(latest, open_ms)
    return index, latest


def outcome_for(signal: dict, index: dict, latest_ms: int, horizon: int, cost_bps: float = COST_BPS) -> dict:
    t, direction = to_ms(signal["candle_time"]), signal["direction"]
    base = {"horizon_h": horizon, "status": None, "gross_bps": None, "net_bps": None, "direction_correct": None, "net_win": None}
    if direction == 0:
        return {**base, "status": "not_a_call"}
    entry, exit_ = index.get(t + HOUR_MS), index.get(t + horizon * HOUR_MS)
    if entry is None or exit_ is None:
        return {**base, "status": "pending" if t + horizon * HOUR_MS > latest_ms else "no_data"}
    gross = direction * (exit_[1] - entry[0]) / entry[0] * 10_000
    net = gross - cost_bps
    return {**base, "status": "done", "gross_bps": gross, "net_bps": net, "direction_correct": gross > 0, "net_win": net > 0}


def history(signals: list, candles_by_symbol: dict, horizons=HORIZONS, cost_bps: float = COST_BPS) -> list:
    indexes = {s: candle_index(c) for s, c in candles_by_symbol.items()}
    out = []
    for sig in signals:
        index, latest = indexes.get(sig["symbol"], ({}, 0))
        out.append({**sig, "outcomes": {str(h): outcome_for(sig, index, latest, h, cost_bps) for h in horizons}})
    return out


def wilson(p: float, n: float, z: float = Z_90) -> tuple:
    if n <= 0:
        return None, None
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def mean_interval(values: list, n_eff: float, z: float) -> tuple:
    if len(values) < 2 or n_eff <= 1:
        return None, None
    mean = sum(values) / len(values)
    half = z * statistics.stdev(values) / math.sqrt(n_eff)
    return mean - half, mean + half


def verdict(n_eff: float, mean_net: float | None, low_adj: float | None, high_adj: float | None) -> str:
    if n_eff < MIN_EFFECTIVE_N or mean_net is None or low_adj is None or high_adj is None:
        return "insufficient_sample"
    if low_adj > 0:
        return "positive_after_cost_research_only"
    if high_adj < 0:
        return "negative_after_cost"
    return "positive_but_not_distinguishable_from_luck" if mean_net > 0 else "no_edge_after_cost"


def summarize_cell(done: list, horizon: int, pending: int, no_data: int, looks: int, baseline) -> dict:
    n = len(done)
    n_eff = n / horizon
    gross = [d["gross_bps"] for d in done]
    net = [d["net_bps"] for d in done]
    z_adj = NormalDist().inv_cdf(1 - 0.05 / max(1, looks))
    acc = sum(1 for d in done if d["direction_correct"]) / n if n else None
    acc_low, acc_high = wilson(acc, n_eff) if n else (None, None)
    low, high = mean_interval(net, n_eff, Z_90)
    low_adj, high_adj = mean_interval(net, n_eff, z_adj)
    mean_net = sum(net) / n if n else None
    return {
        "n": n,
        "n_effective": n_eff,
        "pending": pending,
        "no_data": no_data,
        "accuracy": acc,
        "accuracy_low": acc_low,
        "accuracy_high": acc_high,
        "mean_gross_bps": sum(gross) / n if n else None,
        "mean_net_bps": mean_net,
        "net_win_rate": sum(1 for d in done if d["net_win"]) / n if n else None,
        "net_low_bps": low,
        "net_high_bps": high,
        "net_low_adj_bps": low_adj,
        "net_high_adj_bps": high_adj,
        "baseline_long_gross_bps": baseline,
        "verdict": verdict(n_eff, mean_net, low_adj, high_adj),
    }


def accountability(signals: list, candles_by_symbol: dict, horizons=HORIZONS, cost_bps: float = COST_BPS) -> dict:
    rows = history(signals, candles_by_symbol, horizons, cost_bps)
    indexes = {s: candle_index(c) for s, c in candles_by_symbol.items()}
    baselines: dict = {}
    for symbol in {r["symbol"] for r in rows}:
        index, latest = indexes.get(symbol, ({}, 0))
        times = sorted({to_ms(r["candle_time"]) for r in rows if r["symbol"] == symbol})
        for h in horizons:
            vals = []
            for t in times:
                entry, exit_ = index.get(t + HOUR_MS), index.get(t + h * HOUR_MS)
                if entry and exit_:
                    vals.append((exit_[1] - entry[0]) / entry[0] * 10_000)
            baselines[(symbol, h)] = sum(vals) / len(vals) if vals else None
    cells: dict = {}
    for r in rows:
        if r["direction"] == 0:
            continue
        for h in horizons:
            for symbol in (r["symbol"], "ALL"):
                cell = cells.setdefault((r["kind"], symbol, h), {"done": [], "pending": 0, "no_data": 0})
                o = r["outcomes"][str(h)]
                if o["status"] == "done":
                    cell["done"].append(o)
                elif o["status"] == "pending":
                    cell["pending"] += 1
                elif o["status"] == "no_data":
                    cell["no_data"] += 1
    looks = max(1, sum(1 for (kind, symbol, h), c in cells.items() if symbol != "ALL" and c["done"]))
    groups = []
    for (kind, symbol, h), c in sorted(cells.items(), key=lambda kv: (kv[0][0], kv[0][1] != "ALL", kv[0][1], kv[0][2])):
        if symbol == "ALL":
            base_vals = [baselines[(s, h)] for s in {r["symbol"] for r in rows} if baselines.get((s, h)) is not None]
            baseline = sum(base_vals) / len(base_vals) if base_vals else None
        else:
            baseline = baselines.get((symbol, h))
        groups.append({"kind": kind, "symbol": symbol, "horizon_h": h, **summarize_cell(c["done"], h, c["pending"], c["no_data"], looks, baseline)})
    by_kind = {}
    for kind in KINDS:
        mine = [r for r in rows if r["kind"] == kind]
        by_kind[kind] = {"recorded": len(mine), "directional": sum(1 for r in mine if r["direction"] != 0), "hold_or_none": sum(1 for r in mine if r["direction"] == 0)}
    return {
        "cost_bps": cost_bps,
        "horizons_h": list(horizons),
        "looks": looks,
        "coverage": {"recorded": len(rows), "by_kind": by_kind},
        "groups": groups,
        "notes": [
            "Only signals recorded live, in real time, are judged. No backfill: a model scored on candles it was trained on would look better than it is.",
            "Entry is the open of the candle after the signal, exit is the close after the horizon, round-trip cost is charged. This is a fixed-horizon test, not the stop/target logic of the paper ledger.",
            "Consecutive signals share candles, so the effective sample is n divided by the horizon. Intervals use that smaller number.",
            "Adjusted intervals correct for the number of kind/symbol/horizon cells looked at (Bonferroni): with many cells, some look good by chance.",
            "baseline_long_gross_bps is what simply buying every recorded candle earned before cost: compare it to see whether a signal adds anything beyond market drift.",
            "A verdict never says profitable. positive_after_cost_research_only still needs live paper trading and a long out-of-sample record.",
        ],
        "research_only": True,
    }
