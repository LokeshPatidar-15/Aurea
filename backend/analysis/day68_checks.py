import asyncio
import copy
import json
import py_compile
import random
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from analysis.day66_checks import EXP, OLD, SYMBOLS, make_hub, make_pipe, messages, model, rule, subscribe_all
from services import signal_accountability as sa
from services.candle_pipeline import build_signal_event, to_ms

ROOT = Path(__file__).resolve().parent.parent
results = {"passed": 0, "failed": 0}
UTC = timezone.utc
H = sa.HOUR_MS
T0 = int(datetime(2026, 11, 1, tzinfo=UTC).timestamp() * 1000)


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def approx(a, b, tol=1e-6):
    return a is not None and abs(a - b) <= tol


def event(symbol="BTCUSDT", candle=to_ms(EXP), rule_obj="default", model_obj="default", fresh=True):
    r = rule(symbol, as_of=EXP, status="signal", side="long") if rule_obj == "default" else rule_obj
    m = model(symbol, as_of=EXP, signal="buy") if model_obj == "default" else model_obj
    ev = build_signal_event(symbol, r, m, None, None, candle, candle)
    ev["candle_time"] = candle
    ev["fresh"] = fresh
    return ev


def series(n, drift=0.005, start=100.0, noise=0.0, seed=0, t0=T0):
    rng = random.Random(seed)
    price, out = start, []
    for i in range(n):
        nxt = price * (1 + drift + (rng.gauss(0, noise) if noise else 0.0))
        out.append((t0 + i * H, price, nxt))
        price = nxt
    return out


def sig(i, symbol="BTCUSDT", kind="rule", direction=1, t0=T0):
    return {"id": i, "symbol": symbol, "kind": kind, "candle_time": t0 + i * H, "direction": direction, "signal": "long" if direction > 0 else "short" if direction < 0 else "none", "status": None, "confidence": None, "reference_price": None}


def test_rows():
    print("recording: events to rows")
    rows = sa.rows_from_event(event())
    check("a fresh event gives one rule row and one model row", [r["kind"] for r in rows] == ["rule", "model"])
    r, m = rows
    check("rule long signal: direction +1, signal long, status kept", r["direction"] == 1 and r["signal"] == "long" and r["status"] == "signal")
    check("model buy: direction +1 and confidence kept", m["direction"] == 1 and m["signal"] == "buy" and approx(m["confidence"], 0.52) and m["status"] is None)
    check("candle time is a UTC datetime of the signal candle", r["candle_time"] == EXP and r["candle_time"].tzinfo is not None and r["timeframe"] == "1h" and r["source"] == "pipeline")
    short = sa.rows_from_event(event(rule_obj=rule(as_of=EXP, status="signal", side="short"), model_obj=model(as_of=EXP, signal="sell")))
    check("short and sell are -1", short[0]["direction"] == -1 and short[1]["direction"] == -1)
    flat = sa.rows_from_event(event(rule_obj=rule(as_of=EXP, status="none", side="none"), model_obj=model(as_of=EXP, signal="hold")))
    check("no setup and hold are recorded as direction 0 (so coverage is honest)", [x["direction"] for x in flat] == [0, 0] and flat[0]["signal"] == "none")
    odd = sa.rows_from_event(event(rule_obj=rule(as_of=EXP, status="signal", side="sideways"), model_obj=model(as_of=EXP, signal="maybe")))
    check("a rule status 'signal' with an unknown side is direction 0; an unknown model signal is not recorded", [x["kind"] for x in odd] == ["rule"] and odd[0]["direction"] == 0)
    check("a stale (not fresh) event records nothing: late signals are never judged", sa.rows_from_event(event(fresh=False)) == [])
    check("rule and model on different candles: the odd one out is dropped", [x["kind"] for x in sa.rows_from_event(event(rule_obj=rule(as_of=OLD, status="signal", side="long")))] == ["model"])
    only_rule = sa.rows_from_event(event(model_obj=None))
    check("a missing model records only the rule", [x["kind"] for x in only_rule] == ["rule"])
    check("nan confidence becomes null", sa.rows_from_event(event(model_obj=model(as_of=EXP, signal="buy", confidence=float("nan"))))[1]["confidence"] is None)
    bad = [None, [], {"fresh": True}, {**event(), "candle_time": True}, {**event(), "candle_time": 0}, {**event(), "timeframe": "4h"}, {**event(), "symbol": 5}, {**event(), "fresh": 1}]
    check("malformed events record nothing and never raise", all(sa.rows_from_event(b) == [] for b in bad))
    check("the same event always gives the same rows (the unique key makes re-recording a no-op)", sa.rows_from_event(event()) == sa.rows_from_event(event()))
    ev = event()
    before = copy.deepcopy(ev)
    sa.rows_from_event(ev)
    check("the event is not modified", ev == before)
    check("rows are JSON friendly apart from the datetime", json.dumps({k: v for k, v in r.items() if k != "candle_time"}) != "")


def test_outcomes():
    print("outcome of one signal")
    candles = [(T0 + 1 * H, 100.0, 102.0), (T0 + 2 * H, 102.0, 101.0), (T0 + 3 * H, 101.0, 103.0), (T0 + 4 * H, 103.0, 104.0), (T0 + 5 * H, 104.0, 106.0)]
    index, latest = sa.candle_index(candles)
    long_ = sa.outcome_for(sig(0), index, latest, 1)
    check("long, horizon 1: entry = open of the next candle (100), exit = close of that candle (102) = +200 bps gross, +180 net", long_["status"] == "done" and approx(long_["gross_bps"], 200.0) and approx(long_["net_bps"], 180.0))
    check("direction correct and net win flags", long_["direction_correct"] is True and long_["net_win"] is True)
    short = sa.outcome_for(sig(0, direction=-1), index, latest, 1)
    check("short on the same candle loses 200 bps gross, 220 net", approx(short["gross_bps"], -200.0) and approx(short["net_bps"], -220.0) and short["direction_correct"] is False)
    h4 = sa.outcome_for(sig(0), index, latest, 4)
    check("horizon 4: exit is the close of the candle 4 hours after the signal candle (104)", approx(h4["gross_bps"], 400.0))
    small = sa.outcome_for(sig(0), sa.candle_index([(T0 + H, 100.0, 100.1)])[0], T0 + H, 1)
    check("a right call that does not cover the cost is a direction hit but a net loss", small["direction_correct"] is True and small["net_win"] is False and approx(small["net_bps"], 10 - 20))
    check("direction 0 is not a call", sa.outcome_for(sig(0, direction=0), index, latest, 1)["status"] == "not_a_call")
    check("exit candle not there yet (entry exists): pending", sa.outcome_for(sig(2), index, latest, 4)["status"] == "pending")
    check("entry candle not there yet: pending", sa.outcome_for(sig(5), index, latest, 1)["status"] == "pending")
    gap_index, gap_latest = sa.candle_index([(T0 + 1 * H, 100.0, 101.0), (T0 + 5 * H, 100.0, 101.0)])
    check("a hole in the data well in the past is no_data, not pending forever", sa.outcome_for(sig(0), gap_index, gap_latest, 2)["status"] == "no_data")
    check("custom cost is used", approx(sa.outcome_for(sig(0), index, latest, 1, cost_bps=50.0)["net_bps"], 150.0))
    junk, junk_latest = sa.candle_index([(T0, 0.0, 5.0), (T0 + H, float("nan"), 5.0), (T0 + 2 * H, 100.0, float("inf")), ("x", 1.0, 1.0), (T0 + 3 * H, 100.0, 101.0)])
    check("bad candles (zero open, nan, inf, wrong type) are ignored", list(junk) == [T0 + 3 * H])
    hist = sa.history([sig(0), sig(1, symbol="XAUUSD")], {"BTCUSDT": candles})
    check("history attaches 1, 4 and 24 hour outcomes per signal", set(hist[0]["outcomes"]) == {"1", "4", "24"} and hist[0]["outcomes"]["1"]["status"] == "done" and hist[0]["outcomes"]["24"]["status"] == "pending")
    check("a symbol without candles is pending/no_data, never a crash", hist[1]["outcomes"]["1"]["status"] in ("pending", "no_data"))


def test_stats():
    print("statistics")
    lo, hi = sa.wilson(0.5, 100)
    check("Wilson interval around 50% with n=100 is roughly 42% to 58%", 0.41 < lo < 0.43 and 0.57 < hi < 0.59, f"{lo:.3f}-{hi:.3f}")
    check("Wilson stays inside 0..1 at the edges", sa.wilson(1.0, 5)[1] <= 1.0 and sa.wilson(0.0, 5)[0] >= 0.0 and sa.wilson(0.0, 5)[1] > 0)
    check("Wilson with no sample is null", sa.wilson(0.5, 0) == (None, None))
    low, high = sa.mean_interval([1.0, 2.0, 3.0], 3, sa.Z_90)
    check("mean interval = mean +/- z * sd / sqrt(n_eff)", approx(low, 2 - sa.Z_90 / 3 ** 0.5) and approx(high, 2 + sa.Z_90 / 3 ** 0.5))
    check("one value has no interval", sa.mean_interval([5.0], 1, sa.Z_90) == (None, None))
    wide, _ = sa.mean_interval([1.0, 2.0, 3.0], 1.5, sa.Z_90)
    check("a smaller effective sample widens the interval", wide < low)
    check("verdict: too few effective samples", sa.verdict(10, 50.0, 40.0, 60.0) == "insufficient_sample")
    check("verdict: positive only when even the adjusted interval is above zero", sa.verdict(100, 10.0, 1.0, 19.0) == "positive_after_cost_research_only")
    check("verdict: positive mean but interval includes zero", sa.verdict(100, 10.0, -5.0, 25.0) == "positive_but_not_distinguishable_from_luck")
    check("verdict: negative mean, interval includes zero", sa.verdict(100, -10.0, -25.0, 5.0) == "no_edge_after_cost")
    check("verdict: confidently negative", sa.verdict(100, -30.0, -40.0, -20.0) == "negative_after_cost")
    check("verdict: no numbers at all", sa.verdict(100, None, None, None) == "insufficient_sample")


def test_accountability():
    print("accountability end to end")
    up = series(130)
    signals = [sig(i) for i in range(100)]
    out = sa.accountability(signals, {"BTCUSDT": up})
    cells = {(g["kind"], g["symbol"], g["horizon_h"]): g for g in out["groups"]}
    cell = cells[("rule", "BTCUSDT", 1)]
    check("steady +0.5%/hour, 100 long calls: all 100 judged at 1h, none pending", cell["n"] == 100 and cell["pending"] == 0)
    check("gross +50 bps, net +30 bps after the 20 bps cost", approx(cell["mean_gross_bps"], 50.0, 1e-6) and approx(cell["mean_net_bps"], 30.0, 1e-6), f"{cell['mean_gross_bps']:.4f} / {cell['mean_net_bps']:.4f}")
    check("accuracy 100% and net win rate 100%", cell["accuracy"] == 1.0 and cell["net_win_rate"] == 1.0)
    check("the market baseline (buy every candle) is the same +50 bps", approx(cell["baseline_long_gross_bps"], 50.0, 1e-6))
    check("a perfectly steady path is the only way to be 'positive': research-only label, never 'profitable'", cell["verdict"] == "positive_after_cost_research_only")
    long_h = sa.accountability([sig(i) for i in range(110)], {"BTCUSDT": series(130)})
    h24 = {(g["kind"], g["symbol"], g["horizon_h"]): g for g in long_h["groups"]}[("rule", "BTCUSDT", 24)]
    check("with signals up to candle 109 and candles up to 129 the 24h horizon has pending calls", h24["pending"] > 0 and h24["n"] + h24["pending"] == 110, f"n={h24['n']} pending={h24['pending']}")
    check("n_effective = n / horizon", approx(h24["n_effective"], h24["n"] / 24))
    all_cell = cells[("rule", "ALL", 1)]
    check("an ALL row pools the symbols", all_cell["n"] == 100)
    check("looks counts only per-symbol cells that have results (3 horizons here), not the pooled ALL row", out["looks"] == 3, str(out["looks"]))
    check("coverage counts", out["coverage"]["recorded"] == 100 and out["coverage"]["by_kind"]["rule"] == {"recorded": 100, "directional": 100, "hold_or_none": 0} and out["coverage"]["by_kind"]["model"]["recorded"] == 0)
    mixed = [sig(0, direction=1), sig(1, direction=0), sig(2, kind="model", direction=-1), sig(3, kind="model", direction=0)]
    cov = sa.accountability(mixed, {"BTCUSDT": up})["coverage"]["by_kind"]
    check("hold / no-setup rows are counted as coverage but never judged", cov["rule"] == {"recorded": 2, "directional": 1, "hold_or_none": 1} and cov["model"] == {"recorded": 2, "directional": 1, "hold_or_none": 1})
    short_out = sa.accountability([sig(i, direction=-1) for i in range(50)], {"BTCUSDT": series(80, drift=-0.005)})
    short_cell = {(g["kind"], g["symbol"], g["horizon_h"]): g for g in short_out["groups"]}[("rule", "BTCUSDT", 1)]
    check("shorts in a falling market earn the same +50 gross", approx(short_cell["mean_gross_bps"], 50.0, 1e-4) and short_cell["baseline_long_gross_bps"] < 0)
    two = sa.accountability([sig(i, symbol="BTCUSDT") for i in range(40)] + [sig(i, symbol="XAUUSD", kind="model") for i in range(40)], {"BTCUSDT": series(60), "XAUUSD": series(60, drift=0.0)})
    kinds = {(g["kind"], g["symbol"]) for g in two["groups"]}
    check("rule and model are reported separately, per symbol and pooled", {("rule", "BTCUSDT"), ("rule", "ALL"), ("model", "XAUUSD"), ("model", "ALL")} <= kinds)
    check("the output is strict JSON and no verdict or note claims profit", bool(json.dumps(out, allow_nan=False)) and "profitable" not in json.dumps(out["groups"]) and any("never" in n for n in out["notes"]))
    check("notes explain no-backfill, cost, overlap and multiple looks", sum(1 for k in ("backfill", "round-trip cost", "effective sample", "Bonferroni") if any(k in n for n in out["notes"])) == 4)
    snapshot = copy.deepcopy(signals)
    sa.accountability(signals, {"BTCUSDT": up})
    check("inputs are not modified", signals == snapshot)
    empty = sa.accountability([], {})
    check("no signals at all: empty groups, zero coverage, no crash", empty["groups"] == [] and empty["coverage"]["recorded"] == 0 and empty["looks"] == 1)
    big_signals = [sig(i, symbol=("BTCUSDT", "XAUUSD", "EURUSD")[i % 3], kind=("rule", "model")[i % 2]) for i in range(5000)]
    big_candles = {s: series(5100, noise=0.003, seed=n) for n, s in enumerate(("BTCUSDT", "XAUUSD", "EURUSD"))}
    start = time.time()
    sa.accountability(big_signals, big_candles)
    sa.history(big_signals[:200], big_candles)
    check("5000 signals over 3 symbols are judged in under 3 seconds", time.time() - start < 3.0, f"{time.time() - start:.2f}s")


def false_positive_rate(horizon, runs, cost_bps, n_signals=200):
    hits = 0
    for seed in range(runs):
        out = sa.accountability([sig(i) for i in range(n_signals)], {"BTCUSDT": series(n_signals + 40, drift=0.0, noise=0.004, seed=seed)}, horizons=(horizon,), cost_bps=cost_bps)
        cell = out["groups"][0]
        hits += cell["verdict"] == "positive_after_cost_research_only"
    return hits / runs


def test_calibration():
    print("calibration: does the test cry 'edge' on pure noise?")
    rate1 = false_positive_rate(1, 300, 0.0)
    check("zero-drift noise, no cost, 1h horizon: false 'positive' rate stays near the 5% the interval promises", rate1 <= 0.10, f"{rate1:.1%}")
    rate4 = false_positive_rate(4, 300, 0.0)
    check("same for the overlapping 4h horizon (this is what the effective-sample correction is for)", rate4 <= 0.10, f"{rate4:.1%}")
    rate_cost = false_positive_rate(1, 300, 20.0)
    check("with the real 20 bps cost, noise is never called positive", rate_cost == 0.0, f"{rate_cost:.1%}")


def test_pipeline_hook():
    print("pipeline hook")
    calls = []

    def record(events):
        calls.append(list(events))
        return sum(len(sa.rows_from_event(e)) for e in events)

    hub = make_hub()
    client, _ = subscribe_all(hub)
    pipe = make_pipe(hub, record=record)
    summary = asyncio.run(pipe.run_once("full"))
    types = sorted(m["type"] for m in messages(client))
    check("a full run records once with all three symbols' events", len(calls) == 1 and len(calls[0]) == 3)
    check("the number of new rows comes back in the summary (2 per symbol: rule + model)", summary["recorded"] == 6, str(summary.get("recorded")))
    check("recording does not change what is pushed", types == ["paper_tick", "signal", "signal", "signal"])
    hub = make_hub()
    pipe = make_pipe(hub, record=record)
    asyncio.run(pipe.run_once("refresh"))
    check("a refresh (and the start-up warm-up) records too: safe because the unique key ignores repeats", len(calls) == 2)

    def broken(events):
        raise RuntimeError("password=hunter2 host=db")

    hub = make_hub()
    client, _ = subscribe_all(hub)
    pipe = make_pipe(hub, record=broken)
    summary = asyncio.run(pipe.run_once("full"))
    types = sorted(m["type"] for m in messages(client))
    check("a failing recorder is reported as a class name and nothing else breaks", summary["errors"] == ["record: RuntimeError"] and types == ["paper_tick", "signal", "signal", "signal"] and "hunter2" not in json.dumps(summary))
    hub = make_hub()
    pipe = make_pipe(hub)
    summary = asyncio.run(pipe.run_once("refresh"))
    check("without a recorder nothing changes (Day 66 behaviour)", "recorded" not in summary)
    hub = make_hub()
    events = []
    pipe = make_pipe(hub, record=lambda evs: events.extend(evs) or 0, rule_fn=lambda s: rule(s, as_of=OLD), model_fn=lambda s: model(s, as_of=OLD), max_attempts=1)
    asyncio.run(pipe.run_once("full"))
    check("stale events reach the recorder but produce no rows: a late signal is never judged", len(events) == 3 and all(sa.rows_from_event(e) == [] for e in events))
    fresh = [build_signal_event(s, rule(s, as_of=EXP, status="signal", side="long"), model(s, as_of=EXP, signal="sell"), None, None, to_ms(EXP), to_ms(EXP)) for s in SYMBOLS]
    check("real events from the pipeline's builder give 6 rows", sum(len(sa.rows_from_event(e)) for e in fresh) == 6)


def test_schemas():
    print("response schemas")
    try:
        from schemas import signals as ss
    except Exception as exc:
        print(f"  [SKIP] schemas not importable here ({type(exc).__name__})")
        return
    candles = {"BTCUSDT": series(60)}
    signals = [sig(i) for i in range(30)] + [sig(30, direction=0)]
    for s in signals:
        s["candle_time"] = sa.from_ms(s["candle_time"])
    hist = sa.history(signals, candles)
    acc = sa.accountability(signals, candles)
    for name, model_cls, data in (
        ("history page", ss.SignalHistoryOut, {"total": len(hist), "limit": 50, "offset": 0, "items": hist}),
        ("empty history page", ss.SignalHistoryOut, {"total": 0, "limit": 50, "offset": 0, "items": []}),
        ("accountability", ss.AccountabilityOut, acc),
        ("empty accountability", ss.AccountabilityOut, sa.accountability([], {})),
    ):
        try:
            model_cls.model_validate(data)
            ok = True
        except Exception as exc:
            ok = False
            print(str(exc)[:400])
        check(f"{name} validates against its response schema", ok)


def test_static():
    print("static: migration, model, wiring")
    src = (ROOT / "services/signal_accountability.py").read_text()
    imports = set(re.findall(r"^(?:from|import)\s+([\w\.]+)", src, re.M))
    check("signal_accountability imports only the standard library", imports <= {"math", "statistics", "datetime"}, str(sorted(imports)))
    check("signal_accountability has no database access", not re.search(r"sqlalchemy|SessionLocal|\.execute\(", src))
    versions = ROOT / "alembic/versions"
    revs, downs = {}, set()
    for f in versions.glob("*.py"):
        text = f.read_text()
        rev = re.search(r"^revision(?:: str)? = '(\w+)'", text, re.M)
        down = re.search(r"^down_revision(?:: [^=]+)? = (?:'(\w+)'|None)", text, re.M)
        revs[rev.group(1)] = f.name
        if down and down.group(1):
            downs.add(down.group(1))
    heads = set(revs) - downs
    check("alembic still has exactly one head and it is the new revision", heads == {"a68c0f1d2e34"}, str(heads))
    mig = (versions / revs["a68c0f1d2e34"]).read_text()
    check("the migration continues from the paper trading migration", "down_revision: Union[str, Sequence[str], None] = '82d6e63c93fe'" in mig)
    upgrade = mig.split("def upgrade")[1].split("def downgrade")[0]
    downgrade = mig.split("def downgrade")[1]
    check("upgrade only creates signal_log and its two indexes", upgrade.count("op.create_table") == 1 and "'signal_log'" in upgrade and upgrade.count("op.create_index") == 2 and not re.search(r"op\.(drop|alter|add_column|execute)", upgrade))
    check("upgrade never mentions another table", not re.search(r"paper_|price_history|trades|users|features", upgrade))
    check("downgrade drops only signal_log", downgrade.count("op.drop_table") == 1 and "signal_log" in downgrade and not re.search(r"paper_|price_history", downgrade))
    model_src = (ROOT / "models/signal_log.py").read_text()
    model_cols = re.findall(r"^    (\w+): Mapped", model_src, re.M)
    mig_cols = re.findall(r"sa\.Column\('(\w+)'", upgrade)
    check("the model and the migration have exactly the same columns", model_cols == mig_cols, f"{model_cols} vs {mig_cols}")
    check("the unique key has the same name in model, migration and service", "uq_signal_log_candle" in model_src and "uq_signal_log_candle" in upgrade and "uq_signal_log_candle" in (ROOT / "services/signal_service.py").read_text())
    check("the model is registered for Alembic", "signal_log import SignalLog" in (ROOT / "models/__init__.py").read_text())
    service = (ROOT / "services/signal_service.py").read_text()
    check("the only write is the insert that ignores duplicates", service.count("pg_insert(") == 1 and "on_conflict_do_nothing" in service and not re.search(r"\.delete\(|update\(|\.add\(", service))
    check("page size and row count are capped", "MAX_PAGE = 200" in service and "MAX_SIGNALS = 5000" in service and "min(max(limit, 1), MAX_PAGE)" in service)
    check("only 1h candles and 1h signals are read", service.count('"1h"') >= 2)
    router = (ROOT / "routers/signals.py").read_text()
    check("two GET routes under /signals and an unknown symbol is a 422", router.count("@router.get(") == 2 and "@router.post" not in router and "status_code=422" in router and 'prefix="/signals"' in router)
    check("kind is validated by the framework and database errors are a 503", router.count("Literal[") == 2 and "status_code=503" in router)
    main_src = (ROOT / "main.py").read_text()
    check("main.py wires the router and the recorder", "signals_router.router" in main_src and "record=signal_service.record_events" in main_src)
    check("the pipeline keeps the recorder optional", "record=None" in (ROOT / "services/candle_pipeline.py").read_text() and "self._record" in (ROOT / "services/candle_pipeline.py").read_text())
    for name in ("services/signal_accountability.py", "services/signal_service.py", "models/signal_log.py", "schemas/signals.py", "routers/signals.py", "alembic/versions/a68c0f1d2e34_signal_log.py", "services/candle_pipeline.py", "main.py", "scripts/day68_signals_check.py"):
        try:
            py_compile.compile(str(ROOT / name), doraise=True)
            ok = True
        except py_compile.PyCompileError as exc:
            ok = False
            print(exc)
        check(f"{name} compiles", ok)
    new_files = ["services/signal_accountability.py", "services/signal_service.py", "models/signal_log.py", "routers/signals.py", "alembic/versions/a68c0f1d2e34_signal_log.py"]
    check("no new file mentions port 5432, keys or passwords", not any(re.search(r"5432|api_key|password|secret", (ROOT / n).read_text(), re.I) for n in new_files))


def main():
    test_rows()
    test_outcomes()
    test_stats()
    test_accountability()
    test_calibration()
    test_pipeline_hook()
    test_schemas()
    test_static()
    print(f"\n{results['passed']} passed, {results['failed']} failed")
    raise SystemExit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main()
