# Data and features

## Price data
Candles come from the Binance klines API and are stored in the price_history table with symbol, timeframe, open time, open, high, low, close and volume. Ingestion is idempotent: running it again never creates duplicate rows. Only closed candles are stored, so the candle that is still forming is never in the database.

## Cleaning
Before features are computed, candles are cleaned. Duplicate timestamps are removed, candles with impossible prices (for example a high below the low) are dropped, small gaps of up to 3 missing candles are filled and marked as filled, and extreme outliers are flagged. Filled and outlier candles are never used to create trading signals.

## Features
Features are computed from past candles only. They include log returns over 1, 4 and 24 candles, RSI, MACD histogram, Bollinger band position and width, distance from the 20 period EMA, ATR as a percentage of price, a volume z-score, the distance to the last confirmed swing high and swing low measured in ATR, liquidity sweep flags, and volume profile measures such as the distance to the point of control and whether price is inside the value area.

## Liquidity sweeps
A bullish liquidity sweep happens when a candle wicks below the last confirmed swing low but closes back above it. A bearish sweep is the mirror image above a swing high. Swings are only confirmed after a delay of several candles, so a swing level is never used before it could have been known.

## Labels and leakage
The training label uses the triple-barrier method: after each candle, price must hit +2 ATR (buy), -2 ATR (sell) or neither within 12 candles (hold). Because a label looks 12 candles into the future, the training and test sets are split in time order with a purge gap, and scalers are fitted on training data only. This prevents leakage, which is when information from the future leaks into training and makes results look better than they are.
