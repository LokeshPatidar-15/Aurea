import argparse
import json
import sys
import urllib.error
import urllib.request

results = {"passed": 0, "failed": 0}


def check(name, ok, detail=""):
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            body = {}
        return exc.code, body


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) <= tol


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    base = f"http://{args.host}:{args.port}"

    print("overview vs the existing paper endpoints")
    code, ov = get(base, "/portfolio/overview")
    check("GET /portfolio/overview answers 200", code == 200, str(code))
    _, summary = get(base, "/paper/summary")
    _, perf = get(base, "/paper/performance")
    check("realized equity equals /paper/summary", close(ov.get("realized_equity"), summary.get("realized_equity")), f"{ov.get('realized_equity')} vs {summary.get('realized_equity')}")
    check("realized equity equals /paper/performance end_equity", close(ov.get("realized_equity"), perf.get("end_equity")))
    check("unrealized pnl equals /paper/summary", close(ov.get("unrealized_pnl"), summary.get("unrealized_pnl")), f"{ov.get('unrealized_pnl')} vs {summary.get('unrealized_pnl')}")
    check("equity with open equals /paper/summary", close(ov.get("equity_with_open"), summary.get("equity_with_open")))
    check("closed trade count matches", ov.get("closed_trades") == summary.get("closed_trades") == perf.get("trades"), str(ov.get("closed_trades")))
    check("pending and open counts match", ov.get("pending_orders") == summary.get("pending_orders") and len(ov.get("open_positions", [])) == len(summary.get("open_positions", [])))
    check("peak and drawdown match /paper/summary", close(ov["drawdown"]["peak_equity"] or summary.get("peak_equity"), summary.get("peak_equity")) and close(ov["drawdown"]["current_drawdown"], summary.get("drawdown"), 1e-9))
    check("daily limit flag matches /paper/summary", ov["daily_limit"]["hit"] == summary.get("daily_loss_limit_hit"))
    check("drawdown halt flag matches /paper/summary", ov["halts"]["drawdown_halt"] == summary.get("drawdown_halt"))
    check("research_only and honest labels are present", ov.get("research_only") is True and ov.get("mark_price_source") == "last_closed_1h_candle" and ov.get("unrealized_includes_exit_costs") is False)
    check("evidence block carries the sample warning", "evidence" in ov and "trades" in ov["evidence"], str((ov.get("evidence") or {}).get("sample_warning")))
    for p in ov.get("open_positions", []):
        print(f"      open: {p['symbol']} {p['side']} unrealized={p['unrealized_pnl']} stale={p['mark_stale']}")

    print("P&L per period")
    for period in ("day", "week", "month"):
        code, out = get(base, f"/portfolio/pnl?period={period}&limit=400")
        buckets = out.get("buckets", [])
        check(f"{period}: answers 200", code == 200, str(code))
        check(f"{period}: trades add up to the closed trade count", sum(b["trades"] for b in buckets) == ov["closed_trades"])
        if buckets:
            check(f"{period}: last cumulative pnl equals realized pnl", close(buckets[-1]["cumulative_pnl"], ov["realized_pnl"]), f"{buckets[-1]['cumulative_pnl']} vs {ov['realized_pnl']}")
            check(f"{period}: last equity_end equals realized equity", close(buckets[-1]["equity_end"], ov["realized_equity"]))
    code, _ = get(base, "/portfolio/pnl?period=hour")
    check("an unknown period is refused with 422", code == 422, str(code))
    code, out = get(base, "/portfolio/pnl?limit=100000")
    check("a huge limit is clamped, not an error", code == 200 and len(out.get("buckets", [])) <= 400)

    print("trade journal")
    code, page = get(base, "/portfolio/trades?limit=5")
    check("GET /portfolio/trades answers 200", code == 200, str(code))
    check("total equals the closed trade count", page.get("total") == ov["closed_trades"])
    items = page.get("items", [])
    check("at most the requested page size", len(items) <= 5)
    check("newest first", all(items[i]["exit_time"] >= items[i + 1]["exit_time"] for i in range(len(items) - 1)))
    code, big = get(base, "/portfolio/trades?limit=100000")
    check("a huge page size is clamped to 200", code == 200 and big.get("limit") == 200)
    code, neg = get(base, "/portfolio/trades?limit=-5&offset=-9")
    check("negative limit and offset are clamped", code == 200 and neg.get("limit") == 1 and neg.get("offset") == 0)
    if items:
        symbol = items[0]["symbol"]
        code, filtered = get(base, f"/portfolio/trades?symbol={symbol.lower()}&limit=200")
        check("symbol filter works (case-insensitive)", code == 200 and all(t["symbol"] == symbol for t in filtered["items"]), f"{filtered.get('total')} {symbol} trades")
        t = items[0]
        if t.get("risk_amount"):
            check("R multiple = net pnl / risk", close(t["r_multiple"], t["net_pnl"] / t["risk_amount"], 1e-9))
    code, empty = get(base, "/portfolio/trades?symbol=NOPE")
    check("an unknown symbol gives an empty page, not an error", code == 200 and empty["total"] == 0 and empty["items"] == [])

    print("breakdown")
    for by in ("symbol", "side", "source", "exit_reason"):
        code, out = get(base, f"/portfolio/breakdown?by={by}")
        check(f"by {by}: trades add up to the closed trade count", code == 200 and sum(g["trades"] for g in out.get("groups", [])) == ov["closed_trades"], str(code))
    code, out = get(base, "/portfolio/breakdown?by=symbol")
    check("thin groups are flagged", all(g["thin"] == (g["trades"] < 10) for g in out.get("groups", [])))
    code, _ = get(base, "/portfolio/breakdown?by=hour")
    check("an unknown grouping is refused with 422", code == 422, str(code))

    print("regression")
    for path in ("/health/db", "/pipeline/status", "/ws/status", "/paper/equity-curve", "/strategy/signal/BTCUSDT"):
        code, _ = get(base, path)
        check(f"GET {path} still answers", code == 200, str(code))

    print(f"\n{results['passed']} passed, {results['failed']} failed")
    sys.exit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main()
