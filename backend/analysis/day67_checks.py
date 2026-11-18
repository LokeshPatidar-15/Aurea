import copy
import json
import py_compile
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from services import paper_analytics
from services import portfolio_analytics as pa

ROOT = Path(__file__).resolve().parent.parent
results = {"passed": 0, "failed": 0}
UTC = timezone.utc
T0 = datetime(2026, 3, 1, tzinfo=UTC)
LIMITS = {"max_drawdown_halt": 0.15, "daily_loss_limit": 0.03, "max_gross_exposure": 1.5, "max_open_positions": 3, "risk_per_trade": 0.01}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def trade(i, net, exit_time=None, symbol="BTCUSDT", side="long", reason="target", fees=10.0, risk=100.0, notional=5000.0, source="manual", entry_time=None):
    exit_time = exit_time or T0 + timedelta(days=i, hours=1)
    return {"id": i, "symbol": symbol, "side": side, "source": source, "status": "closed", "entry_time": entry_time or exit_time - timedelta(hours=4), "entry_price": 100.0,
            "exit_time": exit_time, "exit_price": 101.0, "net_pnl": net, "gross_pnl": net + fees, "fees": fees, "risk_amount": risk, "notional": notional,
            "exit_reason": reason, "bars_seen": 4}


def approx(a, b, tol=1e-9):
    return a is not None and abs(a - b) <= tol


def test_buckets():
    print("period buckets")
    wed = datetime(2026, 11, 18, 15, 30, tzinfo=UTC)
    check("day bucket is midnight UTC", pa.bucket_start(wed, "day") == datetime(2026, 11, 18, tzinfo=UTC))
    check("week bucket starts on Monday", pa.bucket_start(wed, "week") == datetime(2026, 11, 16, tzinfo=UTC))
    check("a Monday stays in its own week", pa.bucket_start(datetime(2026, 11, 16, 0, 0, tzinfo=UTC), "week") == datetime(2026, 11, 16, tzinfo=UTC))
    check("a Sunday belongs to the previous Monday", pa.bucket_start(datetime(2026, 11, 22, 23, 59, tzinfo=UTC), "week") == datetime(2026, 11, 16, tzinfo=UTC))
    check("month bucket is the 1st", pa.bucket_start(wed, "month") == datetime(2026, 11, 1, tzinfo=UTC))
    check("naive datetimes are read as UTC", pa.bucket_start(datetime(2026, 11, 18, 15), "day") == datetime(2026, 11, 18, tzinfo=UTC))
    ist = timezone(timedelta(hours=5, minutes=30))
    check("a time in IST is converted to UTC first (00:30 IST = previous day UTC)", pa.bucket_start(datetime(2026, 11, 18, 0, 30, tzinfo=ist), "day") == datetime(2026, 11, 17, tzinfo=UTC))
    check("December rolls into January of the next year", pa.next_bucket(datetime(2026, 12, 1, tzinfo=UTC), "month") == datetime(2027, 1, 1, tzinfo=UTC))
    check("February has 28 days in 2027 (month step lands on the 1st)", pa.next_bucket(datetime(2027, 2, 1, tzinfo=UTC), "month") == datetime(2027, 3, 1, tzinfo=UTC))
    for bad in ("hour", "", "DAY"):
        try:
            pa.bucket_start(wed, bad)
            raised = False
        except ValueError:
            raised = True
        check(f"bad period {bad!r} is refused", raised)


def test_pnl():
    print("P&L per period")
    check("no trades: empty list", pa.pnl_by_period([], "day") == [])
    check("open or pending rows are ignored", pa.pnl_by_period([{"id": 1, "exit_time": None, "net_pnl": None}], "day") == [])
    d1 = datetime(2026, 3, 2, 10, tzinfo=UTC)
    d3 = datetime(2026, 3, 4, 10, tzinfo=UTC)
    ledger = [trade(1, 200, d1), trade(2, -100, d1 + timedelta(hours=1)), trade(3, 50, d3)]
    out = pa.pnl_by_period(ledger, "day")
    check("three calendar days: the empty day in the middle is filled with zeros", [b["trades"] for b in out] == [2, 0, 1], str([b["trades"] for b in out]))
    check("net pnl per day", [b["net_pnl"] for b in out] == [100.0, 0.0, 50.0])
    check("cumulative pnl and equity at the end of each day", [b["cumulative_pnl"] for b in out] == [100.0, 100.0, 150.0] and out[-1]["equity_end"] == 10_150.0)
    check("wins and losses are counted", out[0]["wins"] == 1 and out[0]["losses"] == 1)
    check("fees and gross are summed", approx(out[0]["fees"], 20.0) and approx(out[0]["gross_pnl"], 120.0))
    sliced = pa.pnl_by_period(ledger, "day", limit=2)
    check("limit keeps the newest buckets but cumulative still counts older ones", len(sliced) == 2 and sliced[-1]["cumulative_pnl"] == 150.0 and sliced[0]["cumulative_pnl"] == 100.0)
    edge = pa.pnl_by_period([trade(1, 10, datetime(2026, 3, 2, 23, 59, 59, tzinfo=UTC)), trade(2, 20, datetime(2026, 3, 3, 0, 0, 0, tzinfo=UTC))], "day")
    check("23:59:59 and 00:00:00 land on different days", [b["net_pnl"] for b in edge] == [10.0, 20.0])
    weekly = pa.pnl_by_period([trade(1, 10, datetime(2026, 11, 16, 1, tzinfo=UTC)), trade(2, 20, datetime(2026, 11, 22, 23, tzinfo=UTC)), trade(3, 5, datetime(2026, 11, 23, 1, tzinfo=UTC))], "week")
    check("weekly buckets run Monday to Sunday", [b["trades"] for b in weekly] == [2, 1] and weekly[0]["net_pnl"] == 30.0)
    monthly = pa.pnl_by_period([trade(1, 10, datetime(2026, 11, 30, 23, tzinfo=UTC)), trade(2, 20, datetime(2027, 2, 1, tzinfo=UTC))], "month")
    check("monthly buckets fill December and January", [b["trades"] for b in monthly] == [1, 0, 0, 1] and monthly[-1]["period_start"] == datetime(2027, 2, 1, tzinfo=UTC))
    check("custom start equity is used", pa.pnl_by_period([trade(1, 10)], "day", start_equity=500.0)[0]["equity_end"] == 510.0)
    long_gap = pa.pnl_by_period([trade(1, 10, datetime(2006, 1, 1, tzinfo=UTC)), trade(2, 5, datetime(2026, 1, 1, tzinfo=UTC))], "day", limit=5)
    check("a 20 year gap still finishes and the last bucket is right", len(long_gap) == 5 and long_gap[-1]["cumulative_pnl"] == 15.0)
    original = copy.deepcopy(ledger)
    pa.pnl_by_period(ledger, "week")
    check("the input is never modified", ledger == original)
    big = [trade(i, (i % 7) - 3, T0 + timedelta(minutes=30 * i)) for i in range(1, 5001)]
    start = time.time()
    pa.pnl_by_period(big, "day")
    pa.breakdown(big, "symbol")
    pa.journal(big)
    check("5000 trades are processed in under 2 seconds", time.time() - start < 2.0, f"{time.time() - start:.2f}s")


def test_journal():
    print("trade journal")
    rows = pa.journal([trade(1, 200, risk=100.0, fees=10.0, notional=5000.0), trade(2, -50, risk=100.0), trade(3, 0, risk=None)])
    check("newest first", [r["id"] for r in rows] == [3, 2, 1])
    by_id = {r["id"]: r for r in rows}
    check("R multiple = net pnl / risk", approx(by_id[1]["r_multiple"], 2.0) and approx(by_id[2]["r_multiple"], -0.5))
    check("no risk amount: R is null, not a crash or infinity", by_id[3]["r_multiple"] is None)
    check("outcome labels", by_id[1]["outcome"] == "win" and by_id[2]["outcome"] == "loss" and by_id[3]["outcome"] == "flat")
    check("hold time in hours", approx(by_id[1]["hold_hours"], 4.0))
    check("cost in bps = fees / notional", approx(by_id[1]["cost_bps"], 20.0), str(by_id[1]["cost_bps"]))
    broken = pa.journal_row({"id": 9, "net_pnl": 5.0, "fees": None, "notional": 0, "risk_amount": 0})
    check("zero notional or zero risk gives nulls, never a division error", broken["cost_bps"] is None and broken["r_multiple"] is None and broken["hold_hours"] is None)
    check("nan and inf fields become null", pa.journal_row({"id": 1, "net_pnl": 1.0, "entry_price": float("nan"), "fees": float("inf")})["entry_price"] is None)


def test_breakdown():
    print("breakdown")
    ledger = [trade(1, 100, symbol="BTCUSDT"), trade(2, -50, symbol="BTCUSDT"), trade(3, 30, symbol="XAUUSD", side="short"), trade(4, 20, symbol="BTCUSDT", source=None)]
    out = pa.breakdown(ledger, "symbol")
    groups = {g["name"]: g for g in out["groups"]}
    btc = groups["BTCUSDT"]
    check("trade counts per symbol, biggest group first", btc["trades"] == 3 and groups["XAUUSD"]["trades"] == 1 and out["groups"][0]["name"] == "BTCUSDT")
    check("net pnl, win rate and profit factor", approx(btc["net_pnl"], 70.0) and approx(btc["win_rate"], 2 / 3) and approx(btc["profit_factor"], 120 / 50))
    check("profit factor is null when there is no loss", groups["XAUUSD"]["profit_factor"] is None)
    check("average R", approx(btc["avg_r"], (1.0 - 0.5 + 0.2) / 3))
    check("shares of trades add up to one", approx(sum(g["share_of_trades"] for g in out["groups"]), 1.0))
    check("every group here is thin (under 10 trades) and says so", all(g["thin"] for g in out["groups"]) and "noise" in out["note"])
    check("group with 10 trades is not thin", not pa.breakdown([trade(i, 1) for i in range(1, 11)], "symbol")["groups"][0]["thin"])
    check("missing source becomes 'unknown'", {g["name"] for g in pa.breakdown(ledger, "source")["groups"]} == {"manual", "unknown"})
    check("by side and by exit reason work", {g["name"] for g in pa.breakdown(ledger, "side")["groups"]} == {"long", "short"} and pa.breakdown(ledger, "exit_reason")["groups"][0]["name"] == "target")
    check("empty ledger gives an empty list", pa.breakdown([], "symbol") == {"by": "symbol", "total_trades": 0, "groups": [], "note": out["note"]})
    try:
        pa.breakdown(ledger, "hour_of_day")
        raised = False
    except ValueError:
        raised = True
    check("an unknown grouping is refused (no hour-of-day slicing: that only finds noise)", raised)


def test_positions_and_exposure():
    print("open positions and exposure")
    now = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)
    fresh = now - timedelta(minutes=30)
    long_row = {"id": 1, "symbol": "BTCUSDT", "side": "long", "entry_price": 100.0, "notional": 5000.0, "risk_amount": 100.0, "stop_price": 98.0, "target_price": 104.0}
    m = pa.mark_position(long_row, 102.0, fresh, now)
    check("long: +2% on 5000 notional = +100, +2.0 R", approx(m["unrealized_pnl"], 100.0) and approx(m["unrealized_pct"], 0.02) and approx(m["unrealized_r"], 1.0))
    s = pa.mark_position({**long_row, "id": 2, "side": "short"}, 102.0, fresh, now)
    check("short: price up 2% loses 100", approx(s["unrealized_pnl"], -100.0))
    check("a recent mark is not stale", m["mark_stale"] is False)
    check("a 5 hour old mark is flagged stale", pa.mark_position(long_row, 102.0, now - timedelta(hours=5), now)["mark_stale"] is True)
    none = pa.mark_position(long_row, None, None, now)
    check("no price at all: pnl null and stale", none["unrealized_pnl"] is None and none["mark_stale"] is True)
    check("nan price: pnl null", pa.mark_position(long_row, float("nan"), fresh, now)["unrealized_pnl"] is None)
    check("zero entry price: no division error", pa.mark_position({**long_row, "entry_price": 0.0}, 5.0, fresh, now)["unrealized_pnl"] is None)
    check("unknown side counts as zero exposure direction, never a crash", pa.mark_position({**long_row, "side": "x"}, 102.0, fresh, now)["unrealized_pnl"] == 0.0)
    ex = pa.exposure([m, {**s, "symbol": "XAUUSD", "notional": 2000.0}, {**m, "id": 3, "notional": 1000.0}], 4, 10_000.0, 1.5, 3)
    check("gross, long, short and net notional", ex["gross_notional"] == 8000.0 and ex["long_notional"] == 6000.0 and ex["short_notional"] == 2000.0 and ex["net_notional"] == 4000.0)
    check("gross as share of equity and headroom to the limit", approx(ex["gross_pct_of_equity"], 0.8) and approx(ex["headroom_pct"], 0.7))
    check("per symbol exposure", ex["by_symbol"]["BTCUSDT"]["gross"] == 6000.0 and ex["by_symbol"]["XAUUSD"]["net"] == -2000.0)
    check("slots used count pending and open", ex["slots_used"] == 4 and ex["slots_max"] == 3)
    check("zero equity: share is null, no division error", pa.exposure([m], 1, 0.0, 1.5, 3)["gross_pct_of_equity"] is None)
    check("nothing open: all zero", pa.exposure([], 0, 10_000.0, 1.5, 3)["gross_notional"] == 0.0)


def test_drawdown_and_limits():
    print("drawdown and daily limit")
    now = datetime(2026, 3, 10, 1, tzinfo=UTC)
    ledger = [trade(1, 200), trade(2, -100), trade(3, 200), trade(4, -500)]
    curve = pa.equity_curve(ledger)
    ref = paper_analytics.equity_curve(ledger)
    check("equity curve matches the Day 57 module exactly", [(p["equity"], p["drawdown"], p["position_id"]) for p in curve] == [(p["equity"], p["drawdown"], p["position_id"]) for p in ref])
    water = pa.underwater(curve, now)
    check("peak, current equity and drawdown", water["peak_equity"] == 10_300.0 and water["current_equity"] == 9_800.0 and approx(water["current_drawdown"], 500 / 10_300) and approx(water["current_drawdown_usd"], 500.0))
    check("max drawdown equals the Day 57 number", approx(water["max_drawdown"], paper_analytics.performance(ledger)["max_drawdown"]))
    peak_time = T0 + timedelta(days=3, hours=1)
    check("peak time is the exit of the 3rd trade", water["peak_time"] == peak_time)
    check("underwater now, counted from the last peak", water["underwater_now"] is True and approx(water["days_underwater"], (now - peak_time).total_seconds() / 86400))
    check("longest underwater stretch is the current one (it is longer than the first dip)", approx(water["longest_underwater_days"], water["days_underwater"]))
    recovered = pa.underwater(pa.equity_curve([trade(1, 200), trade(2, -100), trade(3, 200)]), now)
    check("a recovered curve is not underwater; the first dip took 2 days", recovered["underwater_now"] is False and recovered["days_underwater"] == 0.0 and approx(recovered["longest_underwater_days"], 2.0) and recovered["current_drawdown"] == 0.0)
    empty = pa.underwater([], now)
    check("empty curve: zeros, no crash", empty["points"] == 0 and empty["max_drawdown"] == 0.0 and empty["underwater_now"] is False)
    d = pa.daily_limit(-150.0, 9_850.0, 0.03)
    check("daily limit: 3% of the day's opening equity (10000)", approx(d["limit_usd"], 300.0) and approx(d["used_pct"], 0.5) and d["hit"] is False)
    check("daily limit hit at exactly the limit", pa.daily_limit(-300.0, 9_700.0, 0.03)["hit"] is True)
    check("a profitable day uses none of the limit", pa.daily_limit(250.0, 10_250.0, 0.03)["used_pct"] == 0.0)
    ok = True
    for today, equity in [(-150.0, 9850.0), (-400.0, 9600.0), (0.0, 10000.0), (500.0, 10500.0), (-300.0, 9700.0)]:
        old_formula = today <= -0.03 * (equity - today)
        ok = ok and pa.daily_limit(today, equity, 0.03)["hit"] == old_formula
    check("same rule as /paper/summary (daily_loss_limit_hit) on 5 cases", ok)


def test_overview():
    print("overview")
    now = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    today_exit = datetime(2026, 3, 10, 9, 0, tzinfo=UTC)
    closed = [trade(1, 200), trade(2, -100), trade(3, -150, today_exit)]
    fresh = now - timedelta(minutes=20)
    open_rows = [
        pa.mark_position({"id": 10, "symbol": "BTCUSDT", "side": "long", "entry_price": 100.0, "notional": 4000.0, "risk_amount": 100.0}, 101.0, fresh, now),
        pa.mark_position({"id": 11, "symbol": "XAUUSD", "side": "short", "entry_price": 100.0, "notional": 2000.0, "risk_amount": 50.0}, None, None, now),
    ]
    ov = pa.build_overview(closed, open_rows, 1, now, LIMITS)
    check("realized equity = start + closed pnl", ov["realized_equity"] == 9_950.0 and ov["realized_pnl"] == -50.0)
    check("it matches the Day 57 performance end_equity", approx(ov["realized_equity"], paper_analytics.performance(closed)["end_equity"]))
    check("unrealized pnl sums only the marks that exist, missing marks are counted", approx(ov["unrealized_pnl"], 40.0) and ov["marks_missing"] == 1 and ov["marks_stale"] == 1)
    check("equity with open and total return", approx(ov["equity_with_open"], 9_990.0) and approx(ov["total_pnl"], -10.0) and approx(ov["total_return_pct"], -0.001))
    check("only today's closed trades count as realized today", ov["daily_limit"]["realized_today"] == -150.0)
    check("pending and open positions fill the slots", ov["exposure"]["slots_used"] == 3 and ov["exposure"]["gross_notional"] == 6000.0)
    check("next trade risk is 1% of realized equity", approx(ov["next_trade_risk_usd"], 99.5))
    check("no halt in a small drawdown", ov["halts"]["drawdown_halt"] is False and ov["halts"]["new_orders_blocked"] is False)
    check("the numbers are labelled honestly", ov["mark_price_source"] == "last_closed_1h_candle" and ov["unrealized_includes_exit_costs"] is False and ov["research_only"] is True)
    deep = pa.build_overview([trade(1, -2000)], [], 0, now, LIMITS)
    check("a 20% drawdown halts new orders (limit is 15%)", deep["halts"]["drawdown_halt"] is True and deep["halts"]["new_orders_blocked"] is True)
    hit = pa.build_overview([trade(1, -400, today_exit)], [], 0, now, LIMITS)
    check("a daily loss over 3% blocks new orders", hit["daily_limit"]["hit"] is True and hit["halts"]["new_orders_blocked"] is True)
    fresh_account = pa.build_overview([], [], 0, now, LIMITS)
    check("empty account: start equity, no drawdown, nothing blocked", fresh_account["realized_equity"] == 10_000.0 and fresh_account["total_return_pct"] == 0.0 and fresh_account["halts"]["new_orders_blocked"] is False and fresh_account["drawdown"]["points"] == 0)
    before = copy.deepcopy(closed)
    pa.build_overview(closed, open_rows, 1, now, LIMITS)
    check("the input is never modified", closed == before)
    raw = json.dumps(ov, default=str).lower()
    check("nothing secret or personal in the output", not any(w in raw for w in ("api_key", "password", "token", "email")))


def test_schemas():
    print("response schemas")
    try:
        from schemas import portfolio as sp
    except Exception as exc:
        print(f"  [SKIP] schemas not importable here ({type(exc).__name__})")
        return
    now = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    closed = [trade(1, 200), trade(2, -100, side="short", symbol="XAUUSD"), trade(3, -150, datetime(2026, 3, 10, 9, tzinfo=UTC))]
    open_rows = [pa.mark_position({"id": 10, "symbol": "BTCUSDT", "side": "long", "entry_price": 100.0, "notional": 4000.0, "risk_amount": 100.0}, 101.0, now - timedelta(minutes=5), now)]
    ov = pa.build_overview(closed, open_rows, 0, now, LIMITS)
    ov["evidence"] = {"trades": 3, "win_rate": 0.33, "expectancy_r": None, "expectancy_r_low": None, "expectancy_r_high": None, "sample_warning": "Only 3 closed trades."}
    for name, model, data in (
        ("overview", sp.OverviewOut, ov),
        ("empty overview", sp.OverviewOut, pa.build_overview([], [], 0, now, LIMITS)),
        ("pnl", sp.PnlOut, {"period": "day", "timezone": "UTC", "start_equity": 10_000.0, "buckets": pa.pnl_by_period(closed, "day")}),
        ("trades page", sp.TradesPage, {"total": 3, "limit": 50, "offset": 0, "items": pa.journal(closed)}),
        ("breakdown", sp.BreakdownOut, pa.breakdown(closed, "symbol")),
        ("empty breakdown", sp.BreakdownOut, pa.breakdown([], "side")),
    ):
        try:
            model.model_validate(data)
            ok = True
        except Exception as exc:
            ok = False
            print(str(exc)[:400])
        check(f"{name} validates against its response schema", ok)


def test_static():
    print("static")
    src = (ROOT / "services/portfolio_analytics.py").read_text()
    imports = set(re.findall(r"^(?:from|import)\s+([\w\.]+)", src, re.M))
    check("portfolio_analytics imports only the standard library", imports <= {"math", "datetime"}, str(sorted(imports)))
    check("portfolio_analytics has no database access", not re.search(r"sqlalchemy|SessionLocal|\.execute\(", src))
    service = (ROOT / "services/portfolio_service.py").read_text()
    check("the service is read-only (no insert, update, delete, commit)", not re.search(r"\.add\(|\.commit\(|\.delete\(|insert\(|update\(|\.flush\(", service))
    check("the service caps the page size", "MAX_PAGE = 200" in service and "min(max(limit, 1), MAX_PAGE)" in service)
    check("the service uses the live risk limits, not copies", "from services.paper_service import LIMITS" in service and "LIMITS.max_drawdown_halt" in service)
    router = (ROOT / "routers/portfolio.py").read_text()
    check("four GET routes under /portfolio, none writes", router.count("@router.get(") == 4 and "@router.post" not in router and 'prefix="/portfolio"' in router)
    check("router clamps limit and answers 503 on database errors", "min(max(limit, 1), 400)" in router and "status_code=503" in router)
    check("period and grouping are validated by the framework (Literal)", router.count("Literal[") == 2)
    main_src = (ROOT / "main.py").read_text()
    check("main.py includes the portfolio router", "portfolio_router.router" in main_src)
    for name in ("services/portfolio_analytics.py", "services/portfolio_service.py", "schemas/portfolio.py", "routers/portfolio.py", "main.py", "scripts/day67_portfolio_check.py"):
        try:
            py_compile.compile(str(ROOT / name), doraise=True)
            ok = True
        except py_compile.PyCompileError as exc:
            ok = False
            print(exc)
        check(f"{name} compiles", ok)


def main():
    test_buckets()
    test_pnl()
    test_journal()
    test_breakdown()
    test_positions_and_exposure()
    test_drawdown_and_limits()
    test_overview()
    test_schemas()
    test_static()
    print(f"\n{results['passed']} passed, {results['failed']} failed")
    raise SystemExit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main()
