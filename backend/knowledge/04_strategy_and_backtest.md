# Strategy and backtest

## The sweep reversal strategy
The rule-based strategy trades liquidity sweeps. It goes long after a bullish sweep when volume is not below average and the 50 period EMA is above the 200 period EMA. It goes short after a bearish sweep when volume is not below average and the 50 EMA is below the 200 EMA. The decision is made at the close of the signal candle and the order is filled at the open of the next candle.

## Exits and size
The stop is placed at the sweep candle extreme plus or minus 0.25 ATR. The target is 2R, meaning twice the distance to the stop. If neither is hit, the trade is closed after 24 candles (time stop). A signal is skipped when the stop distance is outside 0.5 to 3 ATR. Position size risks 1 percent of equity per trade with leverage capped at 1x.

## How the backtester is kept honest
The backtester is pessimistic. If a candle touches both the stop and the target, the stop wins. If price gaps through the stop, the fill is at the worse open price. A flat cost of 20 basis points per round trip is charged. No parameters were fitted to the data.

## Result: no edge
The strategy failed the promotion gate on all three symbols. Compared with random entries that use the same stops and targets, p-values were 0.92 for BTCUSDT, 0.65 for XAUUSD and 0.95 for EURUSD. Replaying the strategy through the paper broker on stored history gave for BTCUSDT 126 trades, a 27.8 percent win rate and an expectancy of minus 0.49 R per trade, and for XAUUSD 127 trades with expectancy of minus 0.63 R. The gross profit before fees was already negative or zero.

## The promotion gate
Rules are only promoted from research_only to a real signal source when all of this holds: net profit after costs is positive, the p-value against random entries is below 0.05, at least two of three time slices are positive, and at least two symbols pass.

## Why a low win rate is not the problem
With a 2R target the break-even win rate is about 33 percent before costs. After costs the real payoff ratio falls to about 1.25 on BTCUSDT, which needs roughly a 44 percent win rate to break even, while the actual win rate was 28 percent. The gap exists because the entry signal has no predictive edge, not because of the win rate itself.
