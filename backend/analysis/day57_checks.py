from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from analysis.backtest import performance as backtest_performance
from analysis.backtest import run_backtest
from analysis.features import compute_features
from analysis.strategy import StrategyParams, generate_signals
from services.paper_analytics import equity_curve, longest_streak, performance, r_interval
from services.paper_engine import Limits, PaperPos, apply_candle

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


t0 = datetime(2026, 3, 1, tzinfo=timezone.utc)


def trade(i, net, risk=100.0, symbol="BTCUSDT", side="long", reason="target", fees=10.0, bars=5):
    return {"id": i, "symbol": symbol, "side": side, "entry_time": t0 + timedelta(hours=2 * i), "exit_time": t0 + timedelta(hours=2 * i + 1),
            "net_pnl": net, "gross_pnl": net + fees, "fees": fees, "risk_amount": risk, "exit_reason": reason, "bars_seen": bars}


print("empty and tiny ledgers")
check("no trades: zero counts and a clear warning", performance([])["trades"] == 0 and "No closed trades" in performance([])["sample_warning"])
check("no trades: empty curve", equity_curve([]) == [])
check("open or pending positions are ignored", performance([{"id": 1, "exit_time": None, "net_pnl": None}])["trades"] == 0)

print("hand-made ledger with known answers")
hand = [trade(1, 200), trade(2, -100), trade(3, -100), trade(4, 300), trade(5, -100)]
p = performance(hand)
check("net pnl and end equity", abs(p["net_pnl"] - 200) < 1e-9 and abs(p["end_equity"] - 10_200) < 1e-9)
check("win rate 2 of 5", abs(p["win_rate"] - 0.4) < 1e-12)
check("profit factor = 500 / 300", abs(p["profit_factor"] - 500 / 300) < 1e-9, f"{p['profit_factor']:.3f}")
check("payoff ratio = 250 / 100", abs(p["payoff_ratio"] - 2.5) < 1e-9)
check("expectancy in R = mean(pnl/risk) = 0.4", abs(p["expectancy_r"] - 0.4) < 1e-9)
check("longest losing streak is 2", p["longest_losing_streak"] == 2)
curve = equity_curve(hand)
check("curve has a start point plus one point per trade", len(curve) == 6 and curve[0]["equity"] == 10_000 and curve[-1]["equity"] == 10_200)
check("max drawdown = 200 from the 10,200 peak", abs(p["max_drawdown_usd"] - 200) < 1e-9 and abs(p["max_drawdown"] - 200 / 10_200) < 1e-12, f"{p['max_drawdown']:.4f}")
check("current drawdown = 100 below the 10,300 peak", abs(p["current_drawdown"] - 100 / 10_300) < 1e-12)
check("fees add up", abs(p["fees"] - 50) < 1e-9 and abs(p["gross_pnl"] - 250) < 1e-9 and abs(p["fees_share_of_gross"] - 0.2) < 1e-9)
check("exit reasons are counted", p["exit_reasons"] == {"target": 5})
check("fewer than 30 trades carries the noise warning", p["sample_warning"] is not None and "noise" in p["sample_warning"])
check("5 trades are too few for an interval", p["expectancy_r_low"] is None)
mixed = [trade(1, 100, symbol="BTCUSDT"), trade(2, -50, symbol="XAUUSD", side="short")]
pm = performance(mixed)
check("per-symbol and per-side breakdown", pm["by_symbol"]["BTCUSDT"]["net_pnl"] == 100 and pm["by_symbol"]["XAUUSD"]["trades"] == 1 and pm["by_side"]["short"]["net_pnl"] == -50)
check("only wins gives no profit factor (not infinity)", performance([trade(1, 50), trade(2, 70)])["profit_factor"] is None)
shuffled = [hand[3], hand[0], hand[4], hand[1], hand[2]]
check("input order does not matter (sorted by exit time)", performance(shuffled)["max_drawdown_usd"] == p["max_drawdown_usd"])

print("bootstrap interval for expectancy")
rng = np.random.default_rng(5)
noise = rng.normal(0, 1.0, 60)
noise = noise - noise.mean()
low, high = r_interval(noise)
check("same data and seed give the same interval", r_interval(noise) == (low, high))
check("a sample with mean exactly zero has an interval around zero", low < 0 < high, f"[{low:.2f}, {high:.2f}]")
big = performance([trade(i, 100 + (i % 3) * 10, risk=100.0) for i in range(1, 61)])
check("a clearly positive edge has an interval above zero and no luck warning", big["expectancy_r_low"] > 0 and big["sample_warning"] is None, f"[{big['expectancy_r_low']:.2f}, {big['expectancy_r_high']:.2f}]")
coin = performance([trade(i, 100 if i % 2 else -100) for i in range(1, 61)])
check("a coin-flip ledger of 60 trades warns that it is indistinguishable from luck", coin["sample_warning"] is not None and "luck" in coin["sample_warning"])
check("longest_streak helper", longest_streak([False, True, True, False, True]) == 2 and longest_streak([]) == 0)

print("parity with the backtester (same trades, same equity, same drawdown)")
rng = np.random.default_rng(11)
n = 3000
returns = rng.normal(0, 0.004, n) * (1 + 1.5 * (rng.random(n) < 0.03))
close = 100 * np.exp(np.cumsum(returns))
open_ = np.concatenate([[100.0], close[:-1]]) * (1 + rng.normal(0, 0.0007, n))
frame = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n))),
                      "low": np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n))), "close": close, "volume": rng.uniform(50, 150, n)},
                     index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"))
params = StrategyParams(trend="none")
trades = run_backtest(frame, generate_signals(frame, compute_features(frame), params), params)
trades = trades[trades["reason"] != "end"].reset_index(drop=True)
limits = Limits(risk_per_trade=params.risk_frac, max_leverage=params.max_leverage, cost_bps=params.cost_bps, max_bars=params.max_bars)
index_of = {t: i for i, t in enumerate(frame.index)}
equity, ledger = 10_000.0, []
for k, tr in trades.iterrows():
    sp = PaperPos(side=int(tr["side"]), stop=float(tr["stop"]), rr=params.rr, max_bars=params.max_bars)
    j = index_of[tr["entry_time"]]
    while sp.status in ("pending", "open") and j < n:
        row = frame.iloc[j]
        apply_candle(sp, {"time": frame.index[j], "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"]}, equity, limits)
        j += 1
    equity += sp.net_pnl
    ledger.append({"id": k + 1, "symbol": "SYN", "side": "long" if sp.side == 1 else "short", "entry_time": sp.entry_time, "exit_time": sp.exit_time,
                   "net_pnl": sp.net_pnl, "gross_pnl": sp.gross_pnl, "fees": sp.fees, "risk_amount": sp.risk_amount, "exit_reason": sp.exit_reason, "bars_seen": sp.bars_seen})
mine = performance(ledger)
theirs = backtest_performance(trades, n)
check("same number of trades", mine["trades"] == theirs["trades"], f"{mine['trades']}")
check("same win rate", abs(mine["win_rate"] - theirs["win_rate"]) < 1e-12)
check("same total return (compounded equity)", abs(mine["return_pct"] - theirs["total_return"]) < 1e-9, f"{mine['return_pct']:.4%} vs {theirs['total_return']:.4%}")
check("same max drawdown", abs(mine["max_drawdown"] - (-theirs["max_drawdown"])) < 1e-9, f"{mine['max_drawdown']:.4%}")
check("profit factor is close (compounding weights later trades more)", abs(mine["profit_factor"] - theirs["profit_factor"]) / theirs["profit_factor"] < 0.15, f"{mine['profit_factor']:.3f} vs {theirs['profit_factor']:.3f}")
flat = []
for k, tr in trades.iterrows():
    sp = PaperPos(side=int(tr["side"]), stop=float(tr["stop"]), rr=params.rr, max_bars=params.max_bars)
    j = index_of[tr["entry_time"]]
    while sp.status in ("pending", "open") and j < n:
        row = frame.iloc[j]
        apply_candle(sp, {"time": frame.index[j], "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"]}, 10_000.0, limits)
        j += 1
    flat.append({"id": k + 1, "symbol": "SYN", "side": "long", "entry_time": sp.entry_time, "exit_time": sp.exit_time, "net_pnl": sp.net_pnl,
                 "gross_pnl": sp.gross_pnl, "fees": sp.fees, "risk_amount": sp.risk_amount, "exit_reason": sp.exit_reason, "bars_seen": sp.bars_seen})
check("with fixed sizing the profit factor matches the backtester exactly", abs(performance(flat)["profit_factor"] - theirs["profit_factor"]) < 1e-9)
check("same expectancy in R", abs(mine["expectancy_r"] - theirs["expectancy_R"]) < 1e-9, f"{mine['expectancy_r']:.4f}")

print(f"\n{results['passed']} passed, {results['failed']} failed")
raise SystemExit(1 if results["failed"] else 0)
