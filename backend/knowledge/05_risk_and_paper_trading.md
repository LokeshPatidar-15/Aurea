# Risk engine and paper trading

## Paper orders
A paper order starts as pending. It is filled at the open of the next closed candle, the same rule the backtester uses, then it is managed with the stop, the 2R target and the 24 candle time stop. Fills, fees and results are stored in the paper_positions and paper_fills tables. Rejected and cancelled orders are also kept for audit.

## Risk limits
Before an order is accepted the risk engine checks these limits: risk at most 1 percent of equity per trade, leverage at most 1x, at most 3 open or pending positions, only 1 position per symbol, total exposure at most 1.5 times equity, a daily loss limit of 3 percent, and a drawdown halt at 15 percent from the equity peak. Orders are also refused when the price data is stale or when the stop is on the wrong side of the price.

## Tradability screen
Some symbols are too quiet for a flat 20 bps trading cost. The tradability screen compares the cost with the median hourly ATR and refuses a symbol when the cost is more than half of one ATR. Measured values: BTCUSDT has a median hourly ATR of 45.7 bps, so the cost is 0.44 ATR and it is tradable. XAUUSD has 22.7 bps (0.88 ATR) and EURUSD has 7.5 bps (2.66 ATR), so both are blocked at this cost.

## Account and equity
The paper account starts at 10,000. Equity is the start plus the net profit of closed trades. Unrealized profit of open positions is shown separately and is not part of the equity used for risk limits.

## Hourly trading loop
A loop runs every hour at one minute past the hour. It downloads the latest candles, processes open positions, computes the strategy signal for each symbol, and places a paper order when a fresh signal passes the risk engine. The same candle never creates two orders. A failure in one symbol is logged and does not stop the loop. It can be started with python3 -m scripts.run_loop, or run once from the API with POST /loop/run.

## Performance analytics
GET /paper/performance reports win rate, profit factor, payoff ratio, expectancy in R with a 90 percent bootstrap interval, maximum drawdown, fees against gross profit, the longest losing streak and breakdowns by symbol and side. With fewer than 30 closed trades it warns that every number is noise. If the interval for expectancy includes zero it warns that the result cannot be told apart from luck. GET /paper/equity-curve returns the equity after each closed trade.
