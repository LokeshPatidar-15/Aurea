from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from analysis.backtest import run_backtest
from analysis.features import compute_features
from analysis.strategy import StrategyParams, generate_signals
from services.paper_engine import Limits, PaperPos, apply_candle, check_order, equity_state, position_size, tradability

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


L = Limits()
t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)

print("tradability screen (cost versus hourly volatility)")
btc = tradability(20, 70, L.max_cost_to_atr)
eur = tradability(20, 7, L.max_cost_to_atr)
check("70 bps ATR with 20 bps cost is tradable", btc["tradable"], f"{btc['cost_to_atr']:.2f} ATR")
check("7 bps ATR with 20 bps cost is NOT tradable", not eur["tradable"], f"{eur['cost_to_atr']:.1f} ATR")
check("zero volatility is never tradable", not tradability(20, 0, 0.5)["tradable"])

print("position sizing")
s = position_size(10_000, 100.0, 98.0, 1, L)
check("2% stop, 1% risk: notional is half the equity", abs(s["notional"] - 5000) < 1e-9 and abs(s["risk_amount"] - 100) < 1e-9 and not s["capped"])
s = position_size(10_000, 100.0, 99.5, 1, L)
check("0.5% stop would need 2x: capped at 1x, risk is only 50", abs(s["notional"] - 10_000) < 1e-9 and abs(s["risk_amount"] - 50) < 1e-9 and s["capped"])
check("short with the stop below entry is invalid", position_size(10_000, 100.0, 98.0, -1, L) is None)

print("risk engine")
base = dict(side=1, symbol="BTCUSDT", reference_price=100.0, stop=98.0, equity=10_000.0, peak_equity=10_000.0, realized_today=0.0, open_positions=[], atr_bps=70.0, stale=False, limits=L)
check("clean order is approved", check_order(**base)["approved"])
check("stale data is refused", "stale_data" in check_order(**{**base, "stale": True})["reasons"])
check("wrong-side stop is refused", "invalid_stop" in check_order(**{**base, "stop": 102.0})["reasons"])
check("symbol already open is refused", "symbol_already_open" in check_order(**{**base, "open_positions": [{"symbol": "BTCUSDT", "notional": 1000}]})["reasons"])
three = [{"symbol": s, "notional": 1000} for s in ("XAUUSD", "EURUSD", "ETHUSDT")]
check("more than 3 open positions is refused", "max_open_positions" in check_order(**{**base, "open_positions": three})["reasons"])
check("gross exposure above 1.5x is refused", "gross_exposure_limit" in check_order(**{**base, "open_positions": [{"symbol": "XAUUSD", "notional": 7000}, {"symbol": "EURUSD", "notional": 4000}]})["reasons"])
check("a 3% down day stops new orders", "daily_loss_limit" in check_order(**{**base, "equity": 9_700.0, "realized_today": -300.0, "peak_equity": 10_000.0})["reasons"])
check("a 15% drawdown halts trading", "drawdown_halt" in check_order(**{**base, "equity": 8_500.0, "peak_equity": 10_000.0})["reasons"])
check("an untradable symbol is refused", any(r.startswith("not_tradable") for r in check_order(**{**base, "atr_bps": 7.0})["reasons"]))

print("equity bookkeeping")
day = datetime(2026, 3, 10, tzinfo=timezone.utc)
equity, peak, today = equity_state([(day - timedelta(days=2), 500.0), (day - timedelta(days=1), -200.0), (day + timedelta(hours=3), -50.0)], day)
check("equity, peak and today's pnl", (equity, peak, today) == (10_250.0, 10_500.0, -50.0), f"{equity}, {peak}, {today}")

print("paper broker lifecycle")


def candle(i, o, h, l, c):
    return {"time": t0 + timedelta(hours=i), "open": o, "high": h, "low": l, "close": c}


pos = PaperPos(side=1, stop=98.0, rr=2.0, max_bars=24)
ev = apply_candle(pos, candle(1, 100, 100.5, 99.5, 100), 10_000, L)
check("pending order fills at the OPEN of the next candle", ev == ["filled"] and pos.entry == 100.0 and pos.status == "open")
check("size and target are set at the fill", abs(pos.notional - 5000) < 1e-9 and abs(pos.target - 104.0) < 1e-9)
ev = apply_candle(pos, candle(2, 100, 104.5, 99.9, 104), 10_000, L)
check("target is hit and the position closes", ev == ["closed"] and pos.exit_reason == "target" and pos.status == "closed")
check("net pnl = gross - 20 bps fees on the notional", abs(pos.gross_pnl - 200.0) < 1e-9 and abs(pos.fees - 10.0) < 1e-9 and abs(pos.net_pnl - 190.0) < 1e-9, f"net {pos.net_pnl:.2f}")
check("the ledger has an entry fill and an exit fill", [f["kind"] for f in pos.fills] == ["entry", "exit"] and abs(sum(f["fee"] for f in pos.fills) - pos.fees) < 1e-9)
check("a closed position ignores further candles", apply_candle(pos, candle(3, 50, 50, 50, 50), 10_000, L) == [])

pos = PaperPos(side=1, stop=98.0)
apply_candle(pos, candle(1, 100, 101, 99, 100), 10_000, L)
apply_candle(pos, candle(2, 95, 96, 94, 95), 10_000, L)
check("gap through the stop exits at the worse open", pos.exit_reason == "stop" and pos.exit_price == 95.0)

pos = PaperPos(side=1, stop=98.0)
check("a stop above the fill price is rejected, not traded", apply_candle(pos, candle(1, 97, 98, 96, 97), 10_000, L) == ["rejected"] and pos.status == "rejected")

pos = PaperPos(side=-1, stop=102.0, rr=2.0, max_bars=3)
apply_candle(pos, candle(1, 100, 100.5, 99.5, 100), 10_000, L)
apply_candle(pos, candle(2, 100, 100.5, 99.5, 100), 10_000, L)
ev = apply_candle(pos, candle(3, 100, 100.5, 99.5, 99.8), 10_000, L)
check("time stop closes a short at the close of bar 3", ev == ["closed"] and pos.exit_reason == "time" and pos.exit_price == 99.8)

print("parity with the backtester (same candles, same rules, same pnl)")
rng = np.random.default_rng(11)
n = 3000
returns = rng.normal(0, 0.004, n) * (1 + 1.5 * (rng.random(n) < 0.03))
close = 100 * np.exp(np.cumsum(returns))
open_ = np.concatenate([[100.0], close[:-1]]) * (1 + rng.normal(0, 0.0007, n))
frame = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n))),
                      "low": np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n))), "close": close, "volume": rng.uniform(50, 150, n)},
                     index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"))
params = StrategyParams(trend="none")
signals = generate_signals(frame, compute_features(frame), params)
trades = run_backtest(frame, signals, params)
matched = 0
mismatches = []
index_of = {t: i for i, t in enumerate(frame.index)}
broker_limits = Limits(risk_per_trade=params.risk_frac, max_leverage=params.max_leverage, cost_bps=params.cost_bps, max_bars=params.max_bars)
for _, tr in trades.iterrows():
    if tr["reason"] == "end":
        continue
    sp = PaperPos(side=int(tr["side"]), stop=float(tr["stop"]), rr=params.rr, max_bars=params.max_bars)
    j = index_of[tr["entry_time"]]
    while sp.status in ("pending", "open") and j < n:
        row = frame.iloc[j]
        apply_candle(sp, {"time": frame.index[j], "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"]}, 1.0, broker_limits)
        j += 1
    same = (sp.status == "closed" and sp.exit_reason == tr["reason"] and abs(sp.exit_price - tr["exit"]) < 1e-9
            and sp.exit_time == tr["exit_time"] and abs(sp.net_pnl - tr["notional"] * tr["net_ret"]) < 1e-12)
    matched += int(same)
    if not same:
        mismatches.append((tr["entry_time"], sp.status, sp.exit_reason, tr["reason"]))
compared = int((trades["reason"] != "end").sum())
check("every backtest trade is reproduced exactly by the paper broker", compared > 20 and matched == compared, f"{matched}/{compared} trades, first mismatch {mismatches[:1]}")

print(f"\n{results['passed']} passed, {results['failed']} failed")
raise SystemExit(1 if results["failed"] else 0)
