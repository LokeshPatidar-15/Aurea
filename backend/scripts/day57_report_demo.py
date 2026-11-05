import sys

from analysis.backtest import run_backtest
from analysis.ml_features import load_inputs
from analysis.strategy import StrategyParams, generate_signals
from services import paper_analytics
from services.paper_engine import Limits, PaperPos, apply_candle, START_EQUITY

SYMBOL = sys.argv[1].upper() if len(sys.argv) > 1 else "BTCUSDT"
params = StrategyParams()
limits = Limits(risk_per_trade=params.risk_frac, max_leverage=params.max_leverage, cost_bps=params.cost_bps, max_bars=params.max_bars)

feats, cleaned = load_inputs(SYMBOL, "1h")
cleaned = cleaned.loc[feats.index]
trades = run_backtest(cleaned, generate_signals(cleaned, feats, params), params)
trades = trades[trades["reason"] != "end"].reset_index(drop=True)
index_of = {t: i for i, t in enumerate(cleaned.index)}

equity, ledger = START_EQUITY, []
for k, tr in trades.iterrows():
    pos = PaperPos(side=int(tr["side"]), stop=float(tr["stop"]), rr=params.rr, max_bars=params.max_bars)
    j = index_of[tr["entry_time"]]
    while pos.status in ("pending", "open") and j < len(cleaned):
        row = cleaned.iloc[j]
        apply_candle(pos, {"time": cleaned.index[j], "open": row["open"], "high": row["high"], "low": row["low"], "close": row["close"]}, equity, limits)
        j += 1
    equity += pos.net_pnl
    ledger.append({"id": k + 1, "symbol": SYMBOL, "side": "long" if pos.side == 1 else "short", "entry_time": pos.entry_time, "exit_time": pos.exit_time,
                   "net_pnl": pos.net_pnl, "gross_pnl": pos.gross_pnl, "fees": pos.fees, "risk_amount": pos.risk_amount,
                   "exit_reason": pos.exit_reason, "bars_seen": pos.bars_seen})

p = paper_analytics.performance(ledger)
print(f"Replay of the Day 54 strategy on stored {SYMBOL} 1h history through the paper broker (nothing is written to the database)")
if p["trades"] == 0:
    print(p["sample_warning"])
    sys.exit(0)
pct = lambda v: "n/a" if v is None else f"{v:.1%}"
num = lambda v, f="{:.2f}": "n/a" if v is None else f.format(v)
print(f"  trades {p['trades']} | win rate {pct(p['win_rate'])} | exit reasons {p['exit_reasons']}")
print(f"  equity {p['start_equity']:,.0f} -> {p['end_equity']:,.0f} ({pct(p['return_pct'])}) | max drawdown {pct(p['max_drawdown'])} (${p['max_drawdown_usd']:,.0f}) | longest losing streak {p['longest_losing_streak']}")
print(f"  avg win {num(p['avg_win'])} | avg loss {num(p['avg_loss'])} | payoff {num(p['payoff_ratio'])} | profit factor {num(p['profit_factor'])}")
print(f"  expectancy {num(p['expectancy_r'], '{:+.3f}')} R per trade, 90% interval [{num(p['expectancy_r_low'], '{:+.3f}')}, {num(p['expectancy_r_high'], '{:+.3f}')}]")
print(f"  gross pnl (before fees) ${p['gross_pnl']:,.0f} | fees ${p['fees']:,.0f} | net ${p['net_pnl']:,.0f}")
for side, g in p["by_side"].items():
    print(f"  {side:5} trades {g['trades']:3} | net ${g['net_pnl']:,.0f} | win rate {g['win_rate']:.0%}")
if p["sample_warning"]:
    print("  WARNING:", p["sample_warning"])
