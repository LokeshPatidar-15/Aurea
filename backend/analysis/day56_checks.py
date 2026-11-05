from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from analysis.cleaning import clean_candles
from analysis.features import compute_features
from analysis.strategy import StrategyParams, generate_signals
from services.strategy_service import LOOKBACK, compute_signal
from services.trading_loop import decide, seconds_until_next_run

results = {"passed": 0, "failed": 0}


def check(name: str, ok: bool, detail: str = "") -> None:
    results["passed" if ok else "failed"] += 1
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" ({detail})" if detail else ""))


def make_candles(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0, 0.004, n) * (1 + 1.5 * (rng.random(n) < 0.03))
    close = 100 * np.exp(np.cumsum(returns))
    open_ = np.concatenate([[100.0], close[:-1]]) * (1 + rng.normal(0, 0.0007, n))
    return pd.DataFrame(
        {"open": open_, "high": np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.003, n))),
         "low": np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.003, n))), "close": close, "volume": rng.uniform(50, 150, n)},
        index=pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC", name="open_time"),
    )


candles = make_candles(3000, 21)
P_ANY = StrategyParams(trend="none")
cleaned_full, _ = clean_candles(candles, "1h")
batch = generate_signals(cleaned_full, compute_features(cleaned_full), P_ANY)
signal_bars = [i for i in range(LOOKBACK, len(batch)) if batch["side"].iloc[i] != 0]
no_signal_bars = [i for i in range(LOOKBACK, len(batch), 37) if batch["side"].iloc[i] == 0]

print("live signal versus the batch signals used in the backtest")
print(f"  info: {len(signal_bars)} setup bars and {len(no_signal_bars)} quiet bars to compare")
same_setup = same_stop = 0
for i in signal_bars:
    t = candles.index[i]
    live = compute_signal(candles.loc[:t], "TEST", "1h", P_ANY, now=t + timedelta(hours=1, minutes=5))
    want_side = "long" if batch["side"].iloc[i] == 1 else "short"
    in_band = P_ANY.min_risk_atr <= batch["side"].iloc[i] * (cleaned_full["close"].iloc[i] - batch["stop"].iloc[i]) / batch["atr"].iloc[i] <= P_ANY.max_risk_atr
    if in_band:
        same_setup += int(live["status"] == "signal" and live["side"] == want_side)
        same_stop += int(live["status"] == "signal" and abs(live["stop_price"] - batch["stop"].iloc[i]) < 1e-9 * abs(batch["stop"].iloc[i]) + 1e-9)
    else:
        same_setup += int(live["status"] == "none" and live["reason"] == "risk_outside_band")
        same_stop += 1
check("every setup bar gives the same side as the full-history batch", same_setup == len(signal_bars), f"{same_setup}/{len(signal_bars)}")
check("the stop price is identical to the batch stop", same_stop == len(signal_bars), f"{same_stop}/{len(signal_bars)}")
quiet_ok = sum(
    compute_signal(candles.loc[:candles.index[i]], "TEST", "1h", P_ANY, now=candles.index[i] + timedelta(hours=1, minutes=5))["status"] == "none"
    for i in no_signal_bars
)
check("quiet bars stay quiet", quiet_ok == len(no_signal_bars), f"{quiet_ok}/{len(no_signal_bars)}")

print("no look-ahead: a later candle never changes an earlier signal")
i = signal_bars[len(signal_bars) // 2]
t = candles.index[i]
now = t + timedelta(hours=1, minutes=5)
a = compute_signal(candles.loc[:t], "TEST", "1h", P_ANY, now=now)
b = compute_signal(candles.loc[:t].copy(), "TEST", "1h", P_ANY, now=now)
check("same candles give the same answer (deterministic)", (a["status"], a["side"], a["stop_price"]) == (b["status"], b["side"], b["stop_price"]))
before = candles.loc[:t].copy()
compute_signal(before, "TEST", "1h", P_ANY, now=now)
check("the input candles are not modified", before.equals(candles.loc[:t]))

print("freshness and risk band")
stale = compute_signal(candles.loc[:t], "TEST", "1h", P_ANY, now=t + timedelta(hours=6))
check("old data never produces a signal", stale["status"] == "none" and stale["stale"] and (stale["reason"] in ("stale_data", "risk_outside_band")), stale["reason"])
strict = compute_signal(candles.loc[:t], "TEST", "1h", StrategyParams(trend="none", min_risk_atr=50.0, max_risk_atr=60.0), now=now)
check("a stop outside the risk band is not traded", strict["status"] == "none" and strict["reason"] == "risk_outside_band", strict["reason"])
live = compute_signal(candles.loc[:t], "TEST", "1h", P_ANY, now=now)
if live["status"] == "signal":
    gap = live["side"] == "long" and live["stop_price"] < live["reference_price"] or live["side"] == "short" and live["stop_price"] > live["reference_price"]
    check("long stop is below price, short stop above", gap, f"{live['side']} stop {live['stop_price']:.3f} vs close {live['reference_price']:.3f}")
check("response carries the research_only flag and the conditions", live["research_only"] is True and set(live["conditions"]) == {"sweep_bull", "sweep_bear", "volume_ok", "trend"})

print("loop decisions and timing")
sig = {"status": "signal", "reason": "setup_confirmed"}
none = {"status": "none", "reason": "no_setup"}
check("a fresh signal places an order", decide(sig, False, True) == ("order", "setup_confirmed"))
check("the same candle never orders twice", decide(sig, True, True)[0] == "skip")
check("no setup means skip", decide(none, False, True) == ("skip", "no_setup"))
check("orders can be switched off", decide(sig, False, False) == ("skip", "orders_disabled"))
utc = timezone.utc
check("10:00:30 waits 30 s for the 10:01 run", abs(seconds_until_next_run(datetime(2026, 1, 1, 10, 0, 30, tzinfo=utc)) - 30) < 1e-6)
check("10:30:00 waits until 11:01", abs(seconds_until_next_run(datetime(2026, 1, 1, 10, 30, 0, tzinfo=utc)) - 31 * 60) < 1e-6)
check("exactly 10:01:00 waits a full hour", abs(seconds_until_next_run(datetime(2026, 1, 1, 10, 1, 0, tzinfo=utc)) - 3600) < 1e-6)

print(f"\n{results['passed']} passed, {results['failed']} failed")
raise SystemExit(1 if results["failed"] else 0)
