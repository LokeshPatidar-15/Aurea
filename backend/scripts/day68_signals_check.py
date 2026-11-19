import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

results = {"passed": 0, "failed": 0}


def check(name, ok, detail=""):
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def call(base, path, method="GET"):
    req = urllib.request.Request(base + path, method=method, data=b"" if method == "POST" else None)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode()), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            body = {}
        return exc.code, body, dict(exc.headers)


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8010)
    args = parser.parse_args()
    base = f"http://{args.host}:{args.port}"

    print("recording at candle close")
    code, status, _ = call(base, "/pipeline/status")
    waited = 0
    while not status.get("last_summary") and waited < 90:
        time.sleep(3)
        waited += 3
        code, status, _ = call(base, "/pipeline/status")
    summary = status.get("last_summary") or {}
    check("the pipeline ran its warm-up", bool(summary), f"waited {waited}s")
    check("the warm-up passed through the recorder without an error", "recorded" in summary and not any(e.startswith("record:") for e in summary.get("errors", [])), json.dumps({k: summary.get(k) for k in ("recorded", "errors")}))

    print("signal history")
    code, page, _ = call(base, "/signals/history?limit=200")
    check("GET /signals/history answers 200", code == 200, str(code))
    items = page.get("items", [])
    total = page.get("total", 0)
    check("the latest fresh candle is recorded: rule and model for each symbol (up to 6 rows)", total >= 2, f"{total} rows")
    check("newest first", all(items[i]["candle_time"] >= items[i + 1]["candle_time"] for i in range(len(items) - 1)))
    check("kinds, directions and symbols are valid", all(i["kind"] in ("rule", "model") and i["direction"] in (-1, 0, 1) and i["symbol"] in ("BTCUSDT", "XAUUSD", "EURUSD") for i in items))
    check("every signal is stamped at the top of an hour (the candle it was computed on)", all(parse(i["candle_time"]).astimezone(timezone.utc).minute == 0 and parse(i["candle_time"]).astimezone(timezone.utc).second == 0 for i in items))
    keys = [(i["symbol"], i["kind"], i["candle_time"]) for i in items]
    check("no duplicate (symbol, kind, candle)", len(keys) == len(set(keys)))
    check("every signal carries 1, 4 and 24 hour outcomes", all(set(i["outcomes"]) == {"1", "4", "24"} for i in items))
    check("hold / no-setup rows are never judged", all(o["status"] == "not_a_call" for i in items if i["direction"] == 0 for o in i["outcomes"].values()))
    print(f"      {total} rows so far; newest: {items[0]['symbol']} {items[0]['kind']} {items[0]['signal']} at {items[0]['candle_time']}" if items else "      no rows yet")

    print("same answer as the REST endpoints")
    btc_rule = next((i for i in items if i["symbol"] == "BTCUSDT" and i["kind"] == "rule"), None)
    code, rest_rule, _ = call(base, "/strategy/signal/BTCUSDT")
    if btc_rule and code == 200 and parse(rest_rule["as_of"]) == parse(btc_rule["candle_time"]):
        check("recorded rule status equals /strategy/signal", btc_rule["status"] == rest_rule["status"], f"{btc_rule['status']} vs {rest_rule['status']}")
        check("recorded rule side equals /strategy/signal", (btc_rule["signal"] if btc_rule["direction"] else "none") == rest_rule["side"])
    else:
        check("a BTCUSDT rule row exists for the latest candle", False, "no row or the candle moved on; run again")
    btc_model = next((i for i in items if i["symbol"] == "BTCUSDT" and i["kind"] == "model"), None)
    code, rest_model, _ = call(base, "/predict/BTCUSDT?model=xgboost")
    if btc_model and code == 200 and parse(rest_model["as_of"]) == parse(btc_model["candle_time"]):
        check("recorded model signal equals /predict", btc_model["signal"] == rest_model["signal"], f"{btc_model['signal']} vs {rest_model['signal']}")
    else:
        check("a BTCUSDT model row exists for the latest candle (or the model file is missing)", btc_model is None and code != 200, f"http {code}")

    print("recording the same candle again does nothing")
    code, _, headers = call(base, "/pipeline/run?mode=refresh", "POST")
    if code == 429:
        time.sleep(float(headers.get("Retry-After", headers.get("retry-after", "11"))) + 1)
        code, _, _ = call(base, "/pipeline/run?mode=refresh", "POST")
    check("a manual refresh runs", code == 200, str(code))
    code, after, _ = call(base, "/signals/history?limit=1")
    check("the row count did not change (the unique key ignores repeats)", after.get("total") == total, f"{total} -> {after.get('total')}")
    code, status, _ = call(base, "/pipeline/status")
    check("the refresh recorded 0 new rows", (status.get("last_summary") or {}).get("recorded") == 0, str((status.get("last_summary") or {}).get("recorded")))

    print("filters and limits")
    code, only = call(base, "/signals/history?symbol=btcusdt&limit=200")[:2]
    check("symbol filter works and is case-insensitive", code == 200 and all(i["symbol"] == "BTCUSDT" for i in only["items"]))
    code, only = call(base, "/signals/history?kind=model&limit=200")[:2]
    check("kind filter works", code == 200 and all(i["kind"] == "model" for i in only["items"]))
    check("an unknown symbol is a 422", call(base, "/signals/history?symbol=DOGE")[0] == 422)
    check("an unknown kind is a 422", call(base, "/signals/history?kind=astrology")[0] == 422)
    code, big = call(base, "/signals/history?limit=100000")[:2]
    check("a huge page size is clamped to 200", code == 200 and big.get("limit") == 200)
    code, neg = call(base, "/signals/history?limit=-3&offset=-3")[:2]
    check("negative limit and offset are clamped", code == 200 and neg.get("limit") == 1 and neg.get("offset") == 0)

    print("accountability")
    code, acc, _ = call(base, "/signals/accountability")
    check("GET /signals/accountability answers 200", code == 200, str(code))
    groups = acc.get("groups", [])
    check("research_only and cost are stated", acc.get("research_only") is True and acc.get("cost_bps") == 20.0 and acc.get("horizons_h") == [1, 4, 24])
    check("the honesty notes are included", len(acc.get("notes", [])) >= 5)
    check("coverage matches the history total", acc["coverage"]["recorded"] == min(total, 5000), f"{acc['coverage']['recorded']} vs {total}")
    check("no verdict ever says profitable", "profitable" not in json.dumps(groups))
    check("small samples are labelled insufficient, never a verdict", all(g["verdict"] == "insufficient_sample" for g in groups if g["n_effective"] < 30))
    for kind in ("rule", "model"):
        cell = next((g for g in groups if g["kind"] == kind and g["symbol"] == "ALL" and g["horizon_h"] == 1), None)
        directional = acc["coverage"]["by_kind"][kind]["directional"]
        if cell is not None:
            check(f"{kind}: judged + pending + no_data adds up to the directional calls", cell["n"] + cell["pending"] + cell["no_data"] == directional, f"{cell['n']}+{cell['pending']}+{cell['no_data']} vs {directional}")
        else:
            check(f"{kind}: no directional calls yet, so no cells (normal early on)", directional == 0)
    code, one, _ = call(base, "/signals/accountability?symbol=btcusdt&kind=rule")
    check("filters narrow the accountability report", code == 200 and all(g["kind"] == "rule" and g["symbol"] in ("BTCUSDT", "ALL") for g in one["groups"]))
    judged = [g for g in groups if g["n"] > 0]
    if judged:
        g = judged[0]
        print(f"      first judged cell: {g['kind']} {g['symbol']} {g['horizon_h']}h n={g['n']} net={g['mean_net_bps']:.1f} bps verdict={g['verdict']}")
    else:
        print("      nothing judged yet: outcomes appear about 2 hours after the first recorded candle. That is expected.")

    print("regression")
    for path in ("/health/db", "/pipeline/status", "/ws/status", "/portfolio/overview", "/paper/summary"):
        code, _, _ = call(base, path)
        check(f"GET {path} still answers", code == 200, str(code))

    print(f"\n{results['passed']} passed, {results['failed']} failed")
    sys.exit(1 if results["failed"] else 0)


if __name__ == "__main__":
    main()
