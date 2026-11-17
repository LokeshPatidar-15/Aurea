import asyncio
import logging
import math
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger("aurea.pipeline")

OFFSET_SECONDS = 60
RETRY_SECONDS = 30.0
MAX_ATTEMPTS = 6
CYCLE_TIMEOUT_SECONDS = 300.0
MIN_GAP_REFRESH_SECONDS = 10.0
MIN_GAP_FULL_SECONDS = 30.0


class PipelineBusy(Exception):
    pass


class PipelineTooSoon(Exception):
    def __init__(self, retry_after: int):
        super().__init__(f"try again in {retry_after} s")
        self.retry_after = retry_after


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def to_ms(dt: datetime) -> int:
    return int(_utc(dt).timestamp() * 1000)


def expected_candle_open(now: datetime) -> datetime:
    return _utc(now).replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)


def seconds_until_next_run(now: datetime, offset_seconds: int = OFFSET_SECONDS) -> float:
    now = _utc(now)
    this_hour = now.replace(minute=0, second=0, microsecond=0)
    target = this_hour + timedelta(seconds=offset_seconds)
    if now >= target:
        target = this_hour + timedelta(hours=1, seconds=offset_seconds)
    return (target - now).total_seconds()


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _time_ms(value):
    return to_ms(value) if isinstance(value, datetime) else None


def build_signal_event(symbol: str, rule, model, rule_error, model_error, expected_ms: int, now_ms: int) -> dict:
    rule_out = None
    rule_time = None
    if rule is not None:
        rule_time = _time_ms(rule.get("as_of"))
        conditions = rule.get("conditions") or {}
        rule_out = {
            "strategy": rule.get("strategy"),
            "status": rule.get("status"),
            "reason": rule.get("reason"),
            "side": rule.get("side"),
            "reference_price": _num(rule.get("reference_price")),
            "stop_price": _num(rule.get("stop_price")),
            "rr": _num(rule.get("rr")),
            "risk_atr": _num(rule.get("risk_atr")),
            "atr": _num(rule.get("atr")),
            "stale": bool(rule.get("stale")),
            "data_age_minutes": _num(rule.get("data_age_minutes")),
            "as_of": rule_time,
            "conditions": {str(k): v for k, v in conditions.items() if isinstance(v, (bool, str))},
        }
    model_out = None
    model_time = None
    if model is not None:
        model_time = _time_ms(model.get("as_of"))
        info = model.get("model") or {}
        probabilities = model.get("probabilities") or {}
        model_out = {
            "type": info.get("type"),
            "signal": model.get("signal"),
            "confidence": _num(model.get("confidence")),
            "probabilities": {str(k): _num(v) for k, v in probabilities.items()},
            "stale": bool(model.get("stale")),
            "data_age_minutes": _num(model.get("data_age_minutes")),
            "as_of": model_time,
            "calibrated": False,
        }
    times = [t for t in (rule_time, model_time) if t is not None]
    event = {
        "type": "signal",
        "symbol": symbol,
        "timeframe": "1h",
        "candle_time": min(times) if times else expected_ms,
        "expected_candle_time": expected_ms,
        "fresh": bool(times) and all(t == expected_ms for t in times),
        "computed_at": now_ms,
        "rule": rule_out,
        "rule_error": rule_error,
        "model": model_out,
        "model_error": model_error,
        "research_only": True,
    }
    if len(set(times)) > 1:
        event["candle_mismatch"] = True
    return event


def compact_cycle(cycle) -> dict | None:
    if not isinstance(cycle, dict):
        return None
    tick = cycle.get("tick") or {}
    symbols = cycle.get("symbols") or {}
    return {
        "skipped": bool(cycle.get("skipped")),
        "filled": int(tick.get("filled", 0)),
        "closed": int(tick.get("closed", 0)),
        "rejected": int(tick.get("rejected", 0)),
        "orders_placed": sum(1 for e in symbols.values() if e.get("action") == "order"),
        "orders_rejected": sum(1 for e in symbols.values() if e.get("action") == "rejected"),
        "errors": len(cycle.get("errors") or []),
    }


class CandlePipeline:
    def __init__(
        self,
        hub,
        cycle,
        rule_signal,
        model_signal,
        symbols,
        now=None,
        sleep=asyncio.sleep,
        to_thread=asyncio.to_thread,
        monotonic=time.monotonic,
        offset_s: int = OFFSET_SECONDS,
        retry_s: float = RETRY_SECONDS,
        max_attempts: int = MAX_ATTEMPTS,
        cycle_timeout_s: float = CYCLE_TIMEOUT_SECONDS,
        min_gap_refresh_s: float = MIN_GAP_REFRESH_SECONDS,
        min_gap_full_s: float = MIN_GAP_FULL_SECONDS,
    ):
        self.hub = hub
        self._cycle = cycle
        self._rule_signal = rule_signal
        self._model_signal = model_signal
        self.symbols = tuple(symbols)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep
        self._to_thread = to_thread
        self._monotonic = monotonic
        self.offset_s = offset_s
        self.retry_s = retry_s
        self.max_attempts = max_attempts
        self.cycle_timeout_s = cycle_timeout_s
        self.min_gap_refresh_s = min_gap_refresh_s
        self.min_gap_full_s = min_gap_full_s
        self.scheduler_enabled = True
        self.place_orders = False
        self.runs = 0
        self.last_summary: dict | None = None
        self.last_error_type: str | None = None
        self.last_full_expected: datetime | None = None
        self._busy = asyncio.Lock()
        self._last_manual: float | None = None

    def status(self) -> dict:
        return {
            "scheduler_enabled": self.scheduler_enabled,
            "place_orders": self.place_orders,
            "running": self._busy.locked(),
            "runs": self.runs,
            "last_error_type": self.last_error_type,
            "next_run_in_s": round(seconds_until_next_run(self._now(), self.offset_s)),
            "last_summary": self.last_summary,
        }

    async def _compute_symbol(self, symbol: str, expected_ms: int) -> dict:
        rule = model = rule_error = model_error = None
        try:
            rule = await self._to_thread(self._rule_signal, symbol)
        except Exception as exc:
            rule_error = type(exc).__name__
        try:
            model = await self._to_thread(self._model_signal, symbol)
        except Exception as exc:
            model_error = type(exc).__name__
        return build_signal_event(symbol, rule, model, rule_error, model_error, expected_ms, to_ms(self._now()))

    async def run_once(self, mode: str = "full", wait: bool = False, label: str | None = None) -> dict:
        if mode not in ("full", "refresh"):
            raise ValueError("mode must be full or refresh")
        if self._busy.locked() and not wait:
            raise PipelineBusy()
        async with self._busy:
            return await self._run(mode, label or mode)

    async def run_manual(self, mode: str) -> dict:
        gap = self.min_gap_full_s if mode == "full" else self.min_gap_refresh_s
        now = self._monotonic()
        if self._busy.locked():
            raise PipelineBusy()
        if self._last_manual is not None and now - self._last_manual < gap:
            raise PipelineTooSoon(int(gap - (now - self._last_manual)) + 1)
        self._last_manual = now
        return await self.run_once(mode)

    async def _run(self, mode: str, label: str) -> dict:
        started = self._now()
        expected_ms = to_ms(expected_candle_open(started))
        summary = {"mode": label, "started_at": to_ms(started), "expected_candle_time": expected_ms, "attempts": 0, "cycle": None, "symbols": {}, "errors": []}
        events: dict = {}
        cycle_log = None
        for attempt in range(1, self.max_attempts + 1):
            summary["attempts"] = attempt
            if mode == "full":
                try:
                    cycle_log = await asyncio.wait_for(self._to_thread(self._cycle), self.cycle_timeout_s)
                except Exception as exc:
                    cycle_log = None
                    summary["errors"].append(f"cycle: {type(exc).__name__}")
            events = {symbol: await self._compute_symbol(symbol, expected_ms) for symbol in self.symbols}
            stale = [s for s, e in events.items() if not e["fresh"]]
            if not stale or mode != "full" or attempt == self.max_attempts:
                break
            await self._sleep(self.retry_s)
        summary["cycle"] = compact_cycle(cycle_log)
        for symbol, event in events.items():
            published = self.hub.publish_signal(event)
            summary["symbols"][symbol] = {
                "candle_time": event["candle_time"],
                "fresh": event["fresh"],
                "rule": (event["rule"] or {}).get("status"),
                "model": (event["model"] or {}).get("signal"),
                "rule_error": event["rule_error"],
                "model_error": event["model_error"],
                "published": published,
            }
        if mode == "full" and summary["cycle"] is not None and not summary["cycle"]["skipped"]:
            c = summary["cycle"]
            self.hub.publish_paper_tick(
                {
                    "type": "paper_tick",
                    "candle_time": expected_ms,
                    "computed_at": to_ms(self._now()),
                    "filled": c["filled"],
                    "closed": c["closed"],
                    "rejected": c["rejected"],
                    "orders_placed": c["orders_placed"],
                    "orders_rejected": c["orders_rejected"],
                    "refetch": ["/paper/summary", "/paper/positions"],
                }
            )
        elif mode == "full" and summary["cycle"] is not None:
            summary["errors"].append("cycle skipped: another cycle was running")
        self.runs += 1
        self.last_summary = summary
        return summary

    async def run(self) -> None:
        try:
            await self.run_once("refresh", wait=True, label="warmup")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error_type = type(exc).__name__
            log.warning("pipeline warm-up failed (%s)", self.last_error_type)
        while True:
            await self._sleep(seconds_until_next_run(self._now(), self.offset_s))
            expected = expected_candle_open(self._now())
            if expected == self.last_full_expected:
                await self._sleep(1.0)
                continue
            self.last_full_expected = expected
            try:
                await self.run_once("full", wait=True)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error_type = type(exc).__name__
                log.warning("pipeline run failed (%s)", self.last_error_type)


_pipeline: CandlePipeline | None = None


def set_pipeline(pipeline: CandlePipeline | None) -> None:
    global _pipeline
    _pipeline = pipeline


def get_pipeline() -> CandlePipeline | None:
    return _pipeline
