# Glossary

## ATR
Average True Range: the typical size of a candle's range over the last 14 candles. Aurea uses it to measure volatility and to set stops and targets in a way that adapts to the market.

## Basis points (bps)
One basis point is 0.01 percent. A trading cost of 20 bps means 0.20 percent of the position value for entering and exiting.

## R-multiple
A trade result measured in units of the initial risk. If the stop was 100 away and the trade made 200, the result is plus 2R. Losing the stop is minus 1R. Measuring in R makes strategies comparable regardless of position size.

## Expectancy
The average result per trade. Expectancy in R is the mean of all R-multiples. Positive expectancy after costs is the minimum requirement for a strategy.

## Profit factor
Total profit of winning trades divided by total loss of losing trades. Above 1 means winners outweigh losers. Aurea strategies so far are around 0.5.

## Payoff ratio
Average winning trade divided by average losing trade.

## Drawdown
The fall from the highest equity so far, as a percentage. A 36 percent drawdown needs a gain of about 56 percent to get back to the old peak.

## Stop, target and time stop
The stop closes a losing trade at a set price. The target closes a winning trade at a set price. The time stop closes the trade after a fixed number of candles if neither was hit.

## Walk-forward testing
Training on past data and testing on the period right after it, then moving the window forward, repeated several times. It imitates how a model would really be used over time.

## Purged split
A train and test split in time order with a gap removed between them, so labels that look into the future do not overlap the test period.

## Balanced accuracy
The average of the recall of each class. It is not fooled by an imbalanced class like hold.

## P-value
The probability of seeing a result at least this good by pure luck if there were no real edge. A small value, below 0.05, means luck is unlikely.

## Stale data
Price data older than two candle intervals. Aurea refuses to trade or to present confident predictions on stale data.

## Paper trading
Trading with simulated money and real market data, to test a strategy without risking real money.

## RAG
Retrieval-augmented generation: the copilot first retrieves the most relevant passages from the Aurea knowledge base, then answers using only those passages, so answers can be checked against a source.
