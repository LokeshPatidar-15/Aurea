import re
from datetime import datetime, timezone

from rag.copilot import DISCLAIMER, validate_question
from rag.intent import REFUSALS, detect

HEADER = "Live data from the Aurea API (read-only, fetched just now):"
FOOTER = "These numbers come straight from the API, not from a language model."
MAX_ERROR_CHARS = 200
SAFE_NAME = re.compile(r"[^A-Za-z0-9 _.\-]")

REASON_TEXT = {
    "no_setup": "none of the entry conditions were met on the last closed candle",
    "risk_outside_band": "a setup exists but its stop distance is outside the allowed risk band",
    "stale_data": "a setup exists but the data is too old to act on",
    "setup_confirmed": "all entry conditions are met",
}
SOURCES = {
    "price": "latest closed 1h candle in the stored history",
    "signal": "GET /strategy/signal/{symbol}",
    "prediction": "GET /predict/{symbol}",
    "patterns": "GET /strategy/patterns/{symbol}",
    "summary": "GET /paper/summary",
    "performance": "GET /paper/performance",
    "tradability": "GET /paper/tradability",
    "trials": "GET /strategy/trials",
}
TOOL_NAMES = tuple(SOURCES)


def clean_text(value, limit: int = 40) -> str:
    return SAFE_NAME.sub("", str(value))[:limit]


def plain(value, limit: int = 200) -> str:
    text = "".join(ch if ch.isprintable() else " " for ch in str(value))
    return " ".join(text.split())[:limit]


def fmt_price(x) -> str:
    x = float(x)
    return f"{x:,.2f}" if abs(x) >= 100 else f"{x:,.3f}" if abs(x) >= 10 else f"{x:,.5f}"


def fmt_money(x) -> str:
    x = float(x)
    return f"-${abs(x):,.2f}" if x < 0 else f"${x:,.2f}"


def fmt_signed_money(x) -> str:
    x = float(x)
    return f"{'+' if x >= 0 else '-'}${abs(x):,.2f}"


def fmt_pct(x, digits: int = 0) -> str:
    return f"{float(x) * 100:.{digits}f}%"


def fmt_time(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def stale_note(data: dict) -> str:
    if data.get("stale"):
        return f" STALE DATA: the last candle closed {data.get('data_age_minutes')} minutes ago, so this may be out of date."
    return ""


def render_price(d: dict, _filter=None) -> tuple:
    text = f"{fmt_price(d['close'])} (close of the last closed 1h candle at {fmt_time(d['as_of'])}, {d['data_age_minutes']} minutes ago; this is not a live tick).{stale_note(d)}"
    return f"{d['symbol']} price", text, d["as_of"], bool(d.get("stale"))


def render_signal(d: dict, _filter=None) -> tuple:
    c = d["conditions"]
    yn = lambda v: "yes" if v else "no"
    if d["status"] == "signal":
        head = f"{d['side'].upper()} signal: reference price {fmt_price(d['reference_price'])}, stop {fmt_price(d['stop_price'])}, risk {d['risk_atr']:.2f} ATR, target {d['rr']:g}R"
    else:
        head = f"no signal ({REASON_TEXT.get(d['reason'], d['reason'])}); reference price {fmt_price(d['reference_price'])}"
    text = f"{head}. Conditions: sweep_bull {yn(c['sweep_bull'])}, sweep_bear {yn(c['sweep_bear'])}, volume_ok {yn(c['volume_ok'])}, trend {c['trend']}. As of {fmt_time(d['as_of'])}.{stale_note(d)}"
    return f"{d['symbol']} rule signal ({clean_text(d['strategy'])})", text, d["as_of"], bool(d.get("stale"))


def render_prediction(d: dict, _filter=None) -> tuple:
    p = d["probabilities"]
    text = (f"{d['signal'].upper()} with {fmt_pct(d['confidence'])} probability (buy {fmt_pct(p.get('buy', 0))}, hold {fmt_pct(p.get('hold', 0))}, sell {fmt_pct(p.get('sell', 0))}). "
            f"As of {fmt_time(d['as_of'])}. This model has not shown an edge after costs.{stale_note(d)}")
    return f"{d['symbol']} model signal ({clean_text(d['model']['type'])})", text, d["as_of"], bool(d.get("stale"))


def render_patterns(d: dict, _filter=None) -> tuple:
    hits = [name for name, on in d["latest"].items() if on]
    sweeps = [name for name, on in d["sweep"].items() if on]
    text = (f"{', '.join(hits) if hits else 'no candlestick pattern'} on the last closed candle; sweep: {', '.join(sweeps) if sweeps else 'none'}. "
            f"{len(d['recent'])} of the last {d['recent_candles']} candles showed a pattern. As of {fmt_time(d['as_of'])}.{stale_note(d)}")
    return f"{d['symbol']} candlestick patterns", text, d["as_of"], bool(d.get("stale"))


def render_summary(d: dict, _filter=None) -> tuple:
    parts = [f"realized equity {fmt_money(d['realized_equity'])} (started at {fmt_money(d['start_equity'])})",
             f"equity including open positions {fmt_money(d['equity_with_open'])}",
             f"peak {fmt_money(d['peak_equity'])}", f"drawdown {fmt_pct(d['drawdown'], 1)}", f"realized today {fmt_signed_money(d['realized_today'])}"]
    if d["closed_trades"]:
        parts.append(f"{d['closed_trades']} closed trades, win rate {fmt_pct(d['win_rate'])}")
    else:
        parts.append("no closed trades yet")
    parts.append(f"{d['pending_orders']} pending order{'s' if d['pending_orders'] != 1 else ''}")
    opens = d["open_positions"]
    if opens:
        shown = []
        for p in opens:
            pnl = f", unrealized {fmt_signed_money(p['unrealized_pnl'])}" if p.get("unrealized_pnl") is not None else ""
            last = f", last {fmt_price(p['last_price'])}" if p.get("last_price") is not None else ""
            shown.append(f"{p['symbol']} {p['side']} (entry {fmt_price(p['entry_price'])}{last}{pnl})")
        parts.append(f"{len(opens)} open position{'s' if len(opens) != 1 else ''}: " + "; ".join(shown))
    else:
        parts.append("no open positions")
    text = "; ".join(parts) + f". Drawdown halt active: {'yes' if d['drawdown_halt'] else 'no'}. Daily loss limit hit: {'yes' if d['daily_loss_limit_hit'] else 'no'}."
    return "Paper account", text, None, False


def render_performance(d: dict, _filter=None) -> tuple:
    if not d.get("trades"):
        return "Paper performance", "no closed paper trades yet, so there is nothing to measure.", None, False
    parts = [f"{d['trades']} closed trades", f"win rate {fmt_pct(d['win_rate'])}", f"net P&L {fmt_signed_money(d['net_pnl'])}"]
    if d.get("expectancy_r") is not None:
        interval = ""
        if d.get("expectancy_r_low") is not None and d.get("expectancy_r_high") is not None:
            interval = f" (90% interval {d['expectancy_r_low']:+.2f} to {d['expectancy_r_high']:+.2f})"
        parts.append(f"expectancy {d['expectancy_r']:+.2f} R{interval}")
    if d.get("profit_factor") is not None:
        parts.append(f"profit factor {d['profit_factor']:.2f}")
    if d.get("fees_share_of_gross") is not None:
        parts.append(f"fees are {fmt_pct(d['fees_share_of_gross'])} of gross P&L")
    if d.get("max_drawdown") is not None:
        parts.append(f"max drawdown {fmt_pct(d['max_drawdown'], 1)}")
    if d.get("longest_losing_streak") is not None:
        parts.append(f"longest losing streak {d['longest_losing_streak']}")
    text = "; ".join(parts) + "."
    if d.get("sample_warning"):
        text += f" Warning: {plain(d['sample_warning'], 220)}"
    return "Paper performance", text, None, False


def render_tradability(rows: list, symbols=None) -> tuple:
    chosen = [r for r in rows if not symbols or r["symbol"] in symbols]
    lines = []
    for r in chosen:
        verdict = "tradable" if r["tradable"] else "NOT tradable"
        lines.append(f"{r['symbol']} {verdict} (round-trip cost {r['cost_bps']:.0f} bps is {r['cost_to_atr']:.2f}x the typical hourly range of {r['atr_bps']:.0f} bps; last close {fmt_price(r['last_close'])})")
    return "Tradability", "; ".join(lines) + ".", None, False


def render_trials(d: dict, _filter=None) -> tuple:
    n = d["strategies_tried"]
    text = f"{n} strategy x symbol test{'s' if n != 1 else ''} run through the backtest endpoint so far. A new result must reach p below {d['bonferroni_threshold']:.5f} (0.05 divided by {n}) to count."
    recent = [f"{clean_text(e['name'])} on {clean_text(e['symbol'], 12)}" for e in d.get("recent", [])[:3]]
    if recent:
        text += " Most recent: " + "; ".join(recent) + "."
    return "Strategies tried", text, None, False


RENDERERS = {"price": render_price, "signal": render_signal, "prediction": render_prediction, "patterns": render_patterns,
             "summary": render_summary, "performance": render_performance, "tradability": render_tradability, "trials": render_trials}


def friendly_error(exc: Exception) -> str:
    if type(exc).__module__.startswith("sqlalchemy"):
        return "database unavailable"
    if type(exc).__name__ in ("NotEnoughDataError", "ModelNotFoundError", "UnsupportedSymbolError"):
        return plain(exc, MAX_ERROR_CHARS) or type(exc).__name__
    return f"unexpected error ({type(exc).__name__})"


def run_tool(spec: dict, symbols, backend: dict) -> dict:
    tool, symbol = spec["tool"], spec["symbol"]
    label = f"{symbol} {tool}" if symbol else tool
    source = SOURCES[tool].replace("{symbol}", symbol or "")
    try:
        fn = backend[tool]
        data = fn(symbol) if symbol else fn()
        label, text, as_of, stale = RENDERERS[tool](data, symbols) if tool == "tradability" else RENDERERS[tool](data)
        return {"tool": tool, "label": label, "text": text, "source": source, "as_of": iso(as_of), "stale": stale, "ok": True}
    except Exception as exc:
        return {"tool": tool, "label": label, "text": f"unavailable: {friendly_error(exc)}", "source": source, "as_of": None, "stale": False, "ok": False}


def base_response(question: str) -> dict:
    return {"question": question, "coverage": 1.0, "confidence": "ok", "disclaimer": DISCLAIMER, "llm_error": None, "fallback_reason": None,
            "sources": [], "live": [], "tools_used": []}


def answer_live(question: str, intent: dict, backend: dict) -> dict:
    out = base_response(question)
    if intent["kind"] == "refuse":
        return {**out, "answer": REFUSALS[intent["reason"]], "refused": True, "mode": "refusal"}
    facts = [run_tool(spec, intent["symbols"], backend) for spec in intent["tools"]]
    lines = [HEADER] + [f"- {f['label']}: {f['text']}" for f in facts] + [FOOTER]
    return {**out, "answer": "\n".join(lines), "refused": False, "mode": "live", "live": facts, "tools_used": sorted({f["tool"] for f in facts})}


def route_question(question: str, backend_factory, kb_answer) -> dict:
    q = validate_question(question)
    intent = detect(q)
    if intent["kind"] == "kb":
        return kb_answer()
    backend = backend_factory() if intent["kind"] == "live" else {}
    return answer_live(q, intent, backend)
