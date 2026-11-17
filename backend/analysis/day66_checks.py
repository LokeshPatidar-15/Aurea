import asyncio
import json
import logging
import py_compile
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services.candle_pipeline import (
    CandlePipeline,
    PipelineBusy,
    PipelineTooSoon,
    build_signal_event,
    expected_candle_open,
    seconds_until_next_run,
    to_ms,
)
from services.cycle_lock import CYCLE_LOCK_KEY, run_exclusive, skipped_log
from services.ws_hub import Hub

ROOT = Path(__file__).resolve().parent.parent
logging.getLogger("aurea.pipeline").setLevel(logging.CRITICAL)
logging.getLogger("aurea.cycle").setLevel(logging.CRITICAL)
results = {"passed": 0, "failed": 0}
UTC = timezone.utc
NOW = datetime(2026, 11, 17, 10, 1, 5, tzinfo=UTC)
EXP = datetime(2026, 11, 17, 9, 0, tzinfo=UTC)
OLD = datetime(2026, 11, 17, 8, 0, tzinfo=UTC)
SYMBOLS = ("BTCUSDT", "XAUUSD", "EURUSD")


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def rule(symbol="BTCUSDT", as_of=EXP, status="none", **kw):
    base = {"symbol": symbol, "strategy": "sweep_reversal_v1", "status": status, "reason": "no_setup", "side": "none", "as_of": as_of, "reference_price": 64000.5, "stop_price": None, "rr": 2.0, "risk_atr": None, "atr": 250.0, "stale": False, "data_age_minutes": 1.0, "conditions": {"sweep_bull": False, "volume_ok": True, "trend": "up"}}
    base.update(kw)
    return base


def model(symbol="BTCUSDT", as_of=EXP, **kw):
    base = {"symbol": symbol, "signal": "hold", "confidence": 0.52, "probabilities": {"sell": 0.2, "hold": 0.52, "buy": 0.28}, "as_of": as_of, "data_age_minutes": 1.0, "stale": False, "model": {"type": "xgboost", "walk_forward": {"folds": [1, 2, 3], "note": "big object that must not be pushed"}}}
    base.update(kw)
    return base


def make_hub(**kw):
    kw.setdefault("wall_ms", lambda: to_ms(NOW))
    return Hub(**kw)


def subscribe_all(hub):
    client = hub.add_client()
    client.control.clear()
    hub.handle_message(client, json.dumps({"action": "subscribe", "symbols": list(SYMBOLS)}))
    msgs = [json.loads(t) for t in client.control]
    client.control.clear()
    return client, msgs


def messages(client):
    out = [json.loads(t) for t in client.control]
    client.control.clear()
    return out


class FakeLock:
    def __init__(self, acquire=True, unlock_fails=False, try_fails=False):
        self.acquire = acquire
        self.unlock_fails = unlock_fails
        self.try_fails = try_fails
        self.events = []
        self.keys = []

    def try_lock(self, key):
        self.events.append("try_lock")
        self.keys.append(key)
        if self.try_fails:
            raise ConnectionError("db down")
        return self.acquire

    def unlock(self, key):
        self.events.append("unlock")
        if self.unlock_fails:
            raise ConnectionError("lost")

    def discard(self):
        self.events.append("discard")

    def close(self):
        self.events.append("close")


class Sleeper:
    def __init__(self):
        self.calls = []

    async def __call__(self, seconds):
        self.calls.append(seconds)
        await asyncio.sleep(0)


def make_pipe(hub, cycle=None, rule_fn=None, model_fn=None, now=None, **kw):
    clock_now = now or (lambda: NOW)
    cycle = cycle or (lambda: {"skipped": False, "tick": {"filled": 0, "closed": 0, "rejected": 0, "processed_candles": 0}, "symbols": {}, "errors": []})
    rule_fn = rule_fn or (lambda s: rule(s))
    model_fn = model_fn or (lambda s: model(s))
    kw.setdefault("sleep", Sleeper())
    return CandlePipeline(hub, cycle, rule_fn, model_fn, SYMBOLS, now=clock_now, **kw)


def test_lock():
    print("cycle lock: one cycle at a time")
    lock = FakeLock()
    calls = []
    out = run_exclusive(lambda: calls.append(1) or {"ok": True}, factory=lambda: lock)
    check("lock free: the cycle runs, then unlock, then close", out == {"ok": True} and calls == [1] and lock.events == ["try_lock", "unlock", "close"], str(lock.events))
    check("the documented advisory key is used", lock.keys == [CYCLE_LOCK_KEY] and isinstance(CYCLE_LOCK_KEY, int))
    lock = FakeLock(acquire=False)
    calls = []
    out = run_exclusive(lambda: calls.append(1), factory=lambda: lock)
    check("lock busy: the cycle does NOT run and a skipped log comes back", calls == [] and out["skipped"] is True and "already running" in out["errors"][0])
    check("busy: no unlock for a lock we never held, connection closed", lock.events == ["try_lock", "close"], str(lock.events))
    log = skipped_log()
    check("the skipped log has every field the loop router and format_cycle read", {"started_at", "finished_at", "ingest", "tick", "symbols", "errors"} <= set(log) and log["symbols"] == {} and log["tick"] is None)
    lock = FakeLock()

    def boom():
        raise RuntimeError("cycle blew up")

    try:
        run_exclusive(boom, factory=lambda: lock)
        raised = False
    except RuntimeError:
        raised = True
    check("an exception inside the cycle propagates and the lock is still released", raised and lock.events == ["try_lock", "unlock", "close"], str(lock.events))
    lock = FakeLock(unlock_fails=True)
    out = run_exclusive(lambda: {"ok": 1}, factory=lambda: lock)
    check("if the unlock fails, the connection is discarded (so the lock cannot leak into the pool) and the result is kept", out == {"ok": 1} and lock.events == ["try_lock", "unlock", "discard", "close"], str(lock.events))
    lock = FakeLock(try_fails=True)
    try:
        run_exclusive(lambda: {}, factory=lambda: lock)
        raised = False
    except ConnectionError:
        raised = True
    check("a database error while locking fails closed (no cycle without the lock)", raised and lock.events == ["try_lock", "close"], str(lock.events))


def test_helpers():
    print("time helpers")
    check("10:01:05 -> the candle that opened at 09:00 just closed", expected_candle_open(NOW) == EXP)
    check("exactly 10:00:00 -> still 09:00", expected_candle_open(datetime(2026, 11, 17, 10, 0, tzinfo=UTC)) == EXP)
    check("09:59:59 -> 08:00", expected_candle_open(datetime(2026, 11, 17, 9, 59, 59, tzinfo=UTC)) == OLD)
    check("midnight rolls the date back", expected_candle_open(datetime(2026, 11, 18, 0, 5, tzinfo=UTC)) == datetime(2026, 11, 17, 23, 0, tzinfo=UTC))
    check("a naive datetime is read as UTC", expected_candle_open(datetime(2026, 11, 17, 10, 1, 5)) == EXP)
    ist = timezone(timedelta(hours=5, minutes=30))
    check("a datetime in IST is converted to UTC first", expected_candle_open(datetime(2026, 11, 17, 15, 31, 5, tzinfo=ist)) == EXP)
    check("to_ms is epoch milliseconds in UTC", to_ms(EXP) == 1_794_906_000_000, str(to_ms(EXP)))
    check("10:00:30 -> run in 30 s", seconds_until_next_run(datetime(2026, 11, 17, 10, 0, 30, tzinfo=UTC)) == 30.0)
    check("10:01:00 exactly -> next hour (3600 s)", seconds_until_next_run(datetime(2026, 11, 17, 10, 1, 0, tzinfo=UTC)) == 3600.0)
    check("10:30:00 -> 31 minutes", seconds_until_next_run(datetime(2026, 11, 17, 10, 30, 0, tzinfo=UTC)) == 1860.0)
    check("23:59:59 -> 61 s (the run after midnight)", seconds_until_next_run(datetime(2026, 11, 17, 23, 59, 59, tzinfo=UTC)) == 61.0)


def test_event_builder():
    print("signal event builder")
    exp_ms = to_ms(EXP)
    ev = build_signal_event("BTCUSDT", rule(status="signal", side="long", stop_price=63500.0, risk_atr=1.2), model(), None, None, exp_ms, 5)
    check("both fresh: fresh true, candle_time is the expected candle", ev["fresh"] is True and ev["candle_time"] == exp_ms and ev["expected_candle_time"] == exp_ms)
    check("rule fields are copied and typed", ev["rule"]["status"] == "signal" and ev["rule"]["side"] == "long" and ev["rule"]["stop_price"] == 63500.0 and ev["rule"]["as_of"] == exp_ms and ev["rule"]["conditions"]["trend"] == "up")
    check("model fields are copied, calibrated is false, type comes from the model info", ev["model"]["signal"] == "hold" and ev["model"]["confidence"] == 0.52 and ev["model"]["type"] == "xgboost" and ev["model"]["calibrated"] is False)
    check("the big walk-forward block is NOT pushed", "walk_forward" not in json.dumps(ev) and "big object" not in json.dumps(ev))
    check("research_only is always true", ev["research_only"] is True)
    check("the event is strict JSON", bool(json.dumps(ev, allow_nan=False)))
    ev = build_signal_event("BTCUSDT", rule(reference_price=float("nan"), atr=float("inf"), rr=True), model(confidence=float("nan")), None, None, exp_ms, 5)
    check("nan, inf and bool numbers become null instead of breaking JSON", ev["rule"]["reference_price"] is None and ev["rule"]["atr"] is None and ev["rule"]["rr"] is None and ev["model"]["confidence"] is None and bool(json.dumps(ev, allow_nan=False)))
    ev = build_signal_event("BTCUSDT", rule(as_of=OLD), model(as_of=OLD), None, None, exp_ms, 5)
    check("an old candle is marked not fresh and keeps its own candle_time", ev["fresh"] is False and ev["candle_time"] == to_ms(OLD))
    ev = build_signal_event("BTCUSDT", rule(), None, None, "ModelNotFoundError", exp_ms, 5)
    check("a missing model does not make the rule signal stale", ev["fresh"] is True and ev["model"] is None and ev["model_error"] == "ModelNotFoundError")
    ev = build_signal_event("BTCUSDT", None, None, "NotEnoughDataError", "ModelNotFoundError", exp_ms, 5)
    check("both missing: not fresh, candle_time falls back to the expected one", ev["fresh"] is False and ev["candle_time"] == exp_ms and ev["rule"] is None)
    ev = build_signal_event("BTCUSDT", rule(as_of=OLD), model(), None, None, exp_ms, 5)
    check("rule and model on different candles are flagged", ev.get("candle_mismatch") is True and ev["candle_time"] == to_ms(OLD) and ev["fresh"] is False)
    ev = build_signal_event("BTCUSDT", rule(conditions={"a": True, "b": "up", "c": object(), "d": 5}), None, None, None, exp_ms, 5)
    check("only bool and text condition values are pushed", ev["rule"]["conditions"] == {"a": True, "b": "up"})


def test_hub_events():
    print("hub: signal and paper_tick events")
    hub = make_hub()
    check("hello announces the event types", json.loads(hub.add_client().control[0])["events"] == ["tick", "signal", "paper_tick"])
    hub = make_hub()
    a, _ = subscribe_all(hub)
    b = hub.add_client()
    b.control.clear()
    hub.handle_message(b, json.dumps({"action": "subscribe", "symbols": ["XAUUSD"]}))
    b.control.clear()
    idle = hub.add_client()
    idle.control.clear()
    ev = build_signal_event("BTCUSDT", rule(), model(), None, None, to_ms(EXP), to_ms(NOW))
    check("a valid signal event is accepted", hub.publish_signal(ev))
    got_a, got_b, got_idle = messages(a), messages(b), messages(idle)
    check("only subscribers of that symbol receive it", len(got_a) == 1 and got_a[0]["type"] == "signal" and not got_b and not got_idle)
    check("seq and server_time are added by the hub", got_a[0]["seq"] == 1 and got_a[0]["server_time"] == to_ms(NOW))
    hub.publish_signal(build_signal_event("BTCUSDT", rule(), model(), None, None, to_ms(EXP), to_ms(NOW)))
    check("event sequence numbers increase", messages(a)[0]["seq"] == 2)
    st = hub.status()["signals"]
    check("status summarises the cached signals", st["BTCUSDT"]["rule"] == "none" and st["BTCUSDT"]["model"] == "hold" and st["BTCUSDT"]["fresh"] is True)
    late = hub.add_client()
    late.control.clear()
    hub.handle_message(late, json.dumps({"action": "subscribe", "symbols": ["BTCUSDT", "EURUSD"]}))
    got = messages(late)
    check("a late subscriber gets 'subscribed' and then the cached signal (none for a symbol without one)", [m["type"] for m in got] == ["subscribed", "signal"] and got[1]["symbol"] == "BTCUSDT", str([m["type"] for m in got]))
    hub.handle_message(late, json.dumps({"action": "subscribe", "symbols": ["BTCUSDT"]}))
    check("subscribing again to the same symbol does not resend the signal", [m["type"] for m in messages(late)] == ["subscribed"])

    bad = {
        "not a dict": [1],
        "unknown symbol": {**ev, "symbol": "DOGE"},
        "no fresh": {k: v for k, v in ev.items() if k != "fresh"},
        "fresh not bool": {**ev, "fresh": 1},
        "rule not dict": {**ev, "rule": "x"},
        "model not dict": {**ev, "model": [1]},
        "no candle_time": {k: v for k, v in ev.items() if k != "candle_time"},
        "candle_time bool": {**ev, "candle_time": True},
        "candle_time text": {**ev, "candle_time": "1"},
        "candle_time zero": {**ev, "candle_time": 0},
        "computed_at float": {**ev, "computed_at": 1.5},
        "nan inside": {**ev, "rule": {"x": float("nan")}},
        "too large": {**ev, "rule": {"x": "y" * 9000}},
        "not serialisable": {**ev, "rule": {"x": object()}},
    }
    before = dict(hub.latest_signals)
    count = hub.stats["signals_published"]
    for name, bad_ev in bad.items():
        check(f"rejected: {name}", hub.publish_signal(bad_ev) is False)
    check("rejected events are counted, never cached or sent", hub.stats["signals_published"] == count and hub.latest_signals == before and sum(v for k, v in hub.rejected.items() if k.startswith("signal_")) == len(bad), str(dict(hub.rejected)))

    hub = make_hub()
    idle = hub.add_client()
    idle.control.clear()
    ok = hub.publish_paper_tick({"type": "x", "candle_time": to_ms(EXP), "computed_at": to_ms(NOW), "filled": 1, "closed": 0})
    got = messages(idle)
    check("paper_tick goes to every client, even without subscriptions, and the type is forced", ok and len(got) == 1 and got[0]["type"] == "paper_tick" and got[0]["filled"] == 1)
    check("paper_tick is not cached", hub.latest_signals == {} and hub.publish_paper_tick({"candle_time": 0, "computed_at": 5}) is False and hub.rejected["paper_tick_bad_time"] == 1)

    hub = make_hub()
    hub.publish({"symbol": "BTCUSDT", "price": 1.0, "ts": to_ms(NOW), "source": "binance-ws", "mock": False})
    hub.publish_signal(build_signal_event("BTCUSDT", rule(), None, None, None, to_ms(EXP), to_ms(NOW)))
    hub.publish({"symbol": "BTCUSDT", "price": 2.0, "ts": to_ms(NOW) + 1, "source": "binance-ws", "mock": False})
    check("event numbering does not disturb tick numbering", hub.latest["BTCUSDT"][0]["seq"] == 2 and hub.latest_signals["BTCUSDT"][0]["seq"] == 1)

    hub = make_hub(max_control_backlog=3)
    stuck, _ = subscribe_all(hub)
    fine = hub.add_client()
    fine.control.clear()
    hub.handle_message(fine, json.dumps({"action": "subscribe", "symbols": ["BTCUSDT"]}))
    fine.control.clear()
    for i in range(6):
        hub.publish_signal(build_signal_event("BTCUSDT", rule(), None, None, None, to_ms(EXP), to_ms(NOW) + i))
        messages(fine)
    check("a client that never reads is closed when its backlog fills, a healthy client is not", stuck.closed and stuck.close_reason == "backlog" and not fine.closed)


def cycle_returning(**kw):
    base = {"skipped": False, "tick": {"filled": 1, "closed": 2, "rejected": 0, "processed_candles": 5}, "symbols": {"BTCUSDT": {"action": "order"}, "XAUUSD": {"action": "skip"}, "EURUSD": {"action": "rejected"}}, "errors": ["x"]}
    base.update(kw)
    calls = []

    def cycle():
        calls.append(1)
        return base

    cycle.calls = calls
    return cycle


async def test_pipeline_runs():
    print("pipeline: full run, refresh, retries, failures")
    hub = make_hub()
    client, _ = subscribe_all(hub)
    cycle = cycle_returning()
    pipe = make_pipe(hub, cycle=cycle)
    summary = await pipe.run_once("full")
    got = messages(client)
    types = sorted(m["type"] for m in got)
    check("a full run pushes one signal per symbol and one paper_tick", types == ["paper_tick", "signal", "signal", "signal"], str(types))
    check("the cycle ran once and its numbers are in the summary", len(cycle.calls) == 1 and summary["attempts"] == 1 and summary["cycle"] == {"skipped": False, "filled": 1, "closed": 2, "rejected": 0, "orders_placed": 1, "orders_rejected": 1, "errors": 1}, str(summary["cycle"]))
    tick = [m for m in got if m["type"] == "paper_tick"][0]
    check("paper_tick carries counts only", set(tick) == {"type", "seq", "server_time", "candle_time", "computed_at", "filled", "closed", "rejected", "orders_placed", "orders_rejected", "refetch"}, str(sorted(tick)))
    raw = json.dumps(got)
    check("no equity, pnl or balance is ever pushed (paper data stays behind REST and, later, login)", not any(word in raw.lower() for word in ("equity", "pnl", "balance", "unrealized")))
    check("the client is told which REST endpoints to refetch", tick["refetch"] == ["/paper/summary", "/paper/positions"])
    check("the summary is JSON serialisable and published flags are true", bool(json.dumps(summary)) and all(s["published"] for s in summary["symbols"].values()))
    check("status shows the last run", pipe.status()["last_summary"]["mode"] == "full" and pipe.status()["runs"] == 1 and pipe.status()["running"] is False)

    hub = make_hub()
    client, _ = subscribe_all(hub)
    cycle = cycle_returning()
    pipe = make_pipe(hub, cycle=cycle)
    summary = await pipe.run_once("refresh")
    types = sorted(m["type"] for m in messages(client))
    check("refresh mode never touches the cycle (no ingest, no ledger) and sends no paper_tick", cycle.calls == [] and types == ["signal"] * 3 and summary["cycle"] is None)
    try:
        await pipe.run_once("nonsense")
        raised = False
    except ValueError:
        raised = True
    check("an unknown mode is refused", raised)

    hub = make_hub()
    client, _ = subscribe_all(hub)
    state = {"cycles": 0}

    def cycle_fn():
        state["cycles"] += 1
        return {"skipped": False, "tick": {}, "symbols": {}, "errors": []}

    def rule_fn(symbol):
        return rule(symbol, as_of=EXP if state["cycles"] >= 3 else OLD)

    def model_fn(symbol):
        return model(symbol, as_of=EXP if state["cycles"] >= 3 else OLD)

    sleeper = Sleeper()
    pipe = make_pipe(hub, cycle=cycle_fn, rule_fn=rule_fn, model_fn=model_fn, sleep=sleeper, retry_s=30.0, max_attempts=6)
    summary = await pipe.run_once("full")
    got = [m for m in messages(client) if m["type"] == "signal"]
    check("the new candle is missing at first: the pipeline waits 30 s and retries until it appears", summary["attempts"] == 3 and sleeper.calls == [30.0, 30.0] and state["cycles"] == 3, f"attempts={summary['attempts']} sleeps={sleeper.calls}")
    check("only the final, fresh signals are pushed (stale intermediate results are not)", len(got) == 3 and all(m["fresh"] is True for m in got) and hub.stats["signals_published"] == 3)

    hub = make_hub()
    client, _ = subscribe_all(hub)
    sleeper = Sleeper()
    pipe = make_pipe(hub, rule_fn=lambda s: rule(s, as_of=OLD), model_fn=lambda s: model(s, as_of=OLD), sleep=sleeper, max_attempts=3)
    summary = await pipe.run_once("full")
    got = [m for m in messages(client) if m["type"] == "signal"]
    check("the candle never arrives: after the last attempt the signals go out once, marked fresh=false", summary["attempts"] == 3 and len(sleeper.calls) == 2 and len(got) == 3 and all(m["fresh"] is False and m["candle_time"] == to_ms(OLD) for m in got))

    hub = make_hub()
    client, _ = subscribe_all(hub)

    def missing_model(symbol):
        raise FileNotFoundError("/secret/path/model.joblib")

    pipe = make_pipe(hub, model_fn=missing_model)
    summary = await pipe.run_once("full")
    got = [m for m in messages(client) if m["type"] == "signal"]
    check("a missing model: the rule signal still goes out, fresh, with the error class only", len(got) == 3 and all(m["model"] is None and m["model_error"] == "FileNotFoundError" and m["rule"] is not None and m["fresh"] is True for m in got) and summary["attempts"] == 1)
    check("the exception text (a file path) is never pushed", "secret" not in json.dumps(got) and "secret" not in json.dumps(summary))

    hub = make_hub()
    client, _ = subscribe_all(hub)

    def broken_rule(symbol):
        raise RuntimeError("password=hunter2 host=db")

    pipe = make_pipe(hub, rule_fn=broken_rule, max_attempts=2)
    summary = await pipe.run_once("refresh")
    got = [m for m in messages(client) if m["type"] == "signal"]
    check("a failing rule engine: model signal still goes out, error class only", len(got) == 3 and all(m["rule"] is None and m["rule_error"] == "RuntimeError" and m["model"] is not None for m in got) and "hunter2" not in json.dumps(got) + json.dumps(summary))

    hub = make_hub()
    client, _ = subscribe_all(hub)

    def failing_cycle():
        raise RuntimeError("database is down")

    pipe = make_pipe(hub, cycle=failing_cycle, max_attempts=1)
    summary = await pipe.run_once("full")
    types = sorted(m["type"] for m in messages(client))
    check("a failing cycle is recorded, signals still go out, no paper_tick is sent", summary["errors"] == ["cycle: RuntimeError"] and types == ["signal"] * 3 and summary["cycle"] is None)

    hub = make_hub()
    client, _ = subscribe_all(hub)
    pipe = make_pipe(hub, cycle=lambda: skipped_log(), max_attempts=1)
    summary = await pipe.run_once("full")
    types = sorted(m["type"] for m in messages(client))
    check("another cycle holds the lock: signals go out, no paper_tick, the skip is reported", types == ["signal"] * 3 and summary["cycle"]["skipped"] is True and any("skipped" in e for e in summary["errors"]))

    hub = make_hub()
    client, _ = subscribe_all(hub)

    def slow_cycle():
        time.sleep(0.3)
        return {"skipped": False, "tick": {}, "symbols": {}, "errors": []}

    pipe = make_pipe(hub, cycle=slow_cycle, cycle_timeout_s=0.05, max_attempts=1)
    summary = await pipe.run_once("full")
    check("a cycle that hangs is abandoned after the timeout, the pipeline carries on", summary["errors"] == ["cycle: TimeoutError"] and len([m for m in messages(client) if m["type"] == "signal"]) == 3)


async def test_concurrency_and_schedule():
    print("pipeline: single flight, manual rate limit, scheduler")
    hub = make_hub()
    subscribe_all(hub)

    def slow_cycle():
        time.sleep(0.15)
        return {"skipped": False, "tick": {}, "symbols": {}, "errors": []}

    pipe = make_pipe(hub, cycle=slow_cycle, max_attempts=1)
    first = asyncio.create_task(pipe.run_once("full"))
    await asyncio.sleep(0.03)
    results_ = []
    for call in (lambda: pipe.run_once("full"), lambda: pipe.run_manual("refresh")):
        try:
            await call()
            results_.append("ran")
        except PipelineBusy:
            results_.append("busy")
    check("while a run is in progress, a second one is refused (no double ledger work)", results_ == ["busy", "busy"] and pipe.status()["running"] is True)
    await first
    check("after it finishes a new run is possible", (await pipe.run_once("refresh"))["mode"] == "refresh")

    hub = make_hub()
    clock = {"t": 1000.0}
    pipe = make_pipe(hub, monotonic=lambda: clock["t"], max_attempts=1)
    await pipe.run_manual("refresh")
    clock["t"] += 3
    try:
        await pipe.run_manual("refresh")
        retry = None
    except PipelineTooSoon as exc:
        retry = exc.retry_after
    check("manual runs are rate limited (10 s for refresh) with a Retry-After", retry is not None and 1 <= retry <= 8, str(retry))
    clock["t"] += 20
    check("after the gap a manual run works again", (await pipe.run_manual("refresh"))["mode"] == "refresh")
    try:
        await pipe.run_manual("full")
        retry = None
    except PipelineTooSoon as exc:
        retry = exc.retry_after
    check("the gap for a full run is 30 s", retry is not None and 1 <= retry <= 31, str(retry))

    hub = make_hub()
    subscribe_all(hub)
    clock = {"now": datetime(2026, 11, 17, 10, 0, 10, tzinfo=UTC)}
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)
        clock["now"] += timedelta(seconds=seconds)
        await asyncio.sleep(0)
        if len(sleeps) >= 3:
            raise asyncio.CancelledError()

    cycle = cycle_returning()
    pipe = make_pipe(hub, cycle=cycle, rule_fn=lambda s: rule(s, as_of=expected_candle_open(clock["now"])), model_fn=lambda s: model(s, as_of=expected_candle_open(clock["now"])), now=lambda: clock["now"], sleep=fake_sleep)
    task = asyncio.create_task(pipe.run())
    try:
        await task
    except asyncio.CancelledError:
        pass
    check("the scheduler warms up first (signals cached), then waits until HH:01:00, then every hour", sleeps[:2] == [50.0, 3600.0], str(sleeps))
    check("warm-up does not touch the ledger; each hourly run does exactly one cycle", len(cycle.calls) == 2 and pipe.runs == 3 and pipe.last_summary["mode"] == "full")
    check("the warm-up pushed one signal per symbol before the first hour", hub.stats["signals_published"] >= 9)

    hub = make_hub()
    clock = {"now": datetime(2026, 11, 17, 10, 0, 10, tzinfo=UTC)}
    sleeps = []

    async def early_sleep(seconds):
        sleeps.append(seconds)
        if seconds >= 3000:
            raise asyncio.CancelledError()
        clock["now"] += timedelta(seconds=max(0.0, seconds - 0.5))
        await asyncio.sleep(0)

    cycle = cycle_returning()
    pipe = make_pipe(hub, cycle=cycle, now=lambda: clock["now"], sleep=early_sleep, rule_fn=lambda s: rule(s, as_of=expected_candle_open(clock["now"])), model_fn=lambda s: model(s, as_of=expected_candle_open(clock["now"])))
    try:
        await pipe.run()
    except asyncio.CancelledError:
        pass
    check("waking up half a second early never runs the same candle twice", len(cycle.calls) == 1, f"cycles={len(cycle.calls)} sleeps={sleeps}")

    hub = make_hub()
    pipe = make_pipe(hub, sleep=asyncio.sleep, now=lambda: datetime(2026, 11, 17, 10, 30, tzinfo=UTC))
    task = asyncio.create_task(pipe.run())
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    check("the scheduler can be cancelled while waiting (server shutdown)", task.cancelled())
    check("status reports the wait until the next run", 1800 <= pipe.status()["next_run_in_s"] <= 1860, str(pipe.status()["next_run_in_s"]))


def test_static():
    print("static: purity and wiring")
    for name in ("services/candle_pipeline.py", "services/cycle_lock.py"):
        src = (ROOT / name).read_text()
        imports = set(re.findall(r"^(?:from|import)\s+([\w\.]+)", src, re.M))
        allowed = {"asyncio", "logging", "math", "time", "datetime", "contextlib"}
        check(f"{name} imports only the standard library at module level", imports <= allowed, str(sorted(imports - allowed)))
    pipeline_src = (ROOT / "services/candle_pipeline.py").read_text()
    check("the pipeline has no direct database or ledger access (everything is injected)", not re.search(r"sqlalchemy|SessionLocal|paper_service|\.execute\(", pipeline_src))
    check("the pipeline logs only the exception class", "type(exc).__name__" in pipeline_src and "str(exc)" not in pipeline_src)
    lock_src = (ROOT / "services/cycle_lock.py").read_text()
    check("the lock uses the session advisory lock on the app's own engine, nothing else", "pg_try_advisory_lock" in lock_src and "pg_advisory_unlock" in lock_src and "from database import engine" in lock_src)
    loop_src = (ROOT / "services/trading_loop.py").read_text()
    check("run_cycle now goes through the lock", "run_exclusive" in loop_src and "def _run_cycle_unlocked" in loop_src)
    for name in ("services/candle_pipeline.py", "services/cycle_lock.py", "services/ws_hub.py", "services/trading_loop.py", "routers/pipeline.py", "main.py", "config.py", "scripts/day66_pipeline_check.py"):
        try:
            py_compile.compile(str(ROOT / name), doraise=True)
            ok = True
        except py_compile.PyCompileError as exc:
            ok = False
            print(exc)
        check(f"{name} compiles", ok)
    main_src = (ROOT / "main.py").read_text()
    check("main.py builds the pipeline with the real rule and model functions", "CandlePipeline(" in main_src and "strategy_service.latest_signal" in main_src and 'prediction_service.predict(symbol, "1h", "xgboost")' in main_src and "pipeline_router.router" in main_src)
    check("orders from the pipeline follow the setting", "place_orders=settings.pipeline_place_orders" in main_src)
    cfg = (ROOT / "config.py").read_text()
    check("config: the pipeline is on by default, placing orders is OFF by default", "pipeline_enabled: bool = True" in cfg and "pipeline_place_orders: bool = False" in cfg)
    router_src = (ROOT / "routers/pipeline.py").read_text()
    check("the router answers 429 with Retry-After when busy or too soon", router_src.count("status_code=429") == 2 and router_src.count("Retry-After") == 2)


def main():
    test_lock()
    test_helpers()
    test_event_builder()
    test_hub_events()
    asyncio.run(test_pipeline_runs())
    asyncio.run(test_concurrency_and_schedule())
    test_static()
    print(f"\n{results['passed']} passed, {results['failed']} failed")
    raise SystemExit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main()
