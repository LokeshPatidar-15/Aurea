# Models and results

## Models
Aurea trains four kinds of models to predict buy, hold or sell: logistic regression, XGBoost, a small feed-forward neural network, and an LSTM that reads the last 48 candles. All of them are evaluated with walk-forward testing: five expanding folds in time order, so every prediction is made on data that comes after the training data.

## How results are judged
Plain accuracy is misleading because the hold class is large, so Aurea reports balanced accuracy, where random guessing on three classes scores about 0.33. The number that matters most is net basis points per trade after a 20 bps round-trip trading cost. A permutation test gives a p-value for whether the result could be luck.

## What was found
Balanced accuracy for the models was around 0.42 to 0.45, better than random guessing. But every model lost money after costs: roughly minus 16 to minus 20 basis points per trade on BTCUSDT, and the p-values were not significant. In short, the models learned a little about direction but not enough to beat the cost of trading. All model predictions therefore stay flagged research_only.

## The predict endpoint
GET /predict/{symbol} returns the signal (buy, hold or sell), a confidence, the three probabilities, the time of the last candle used, the age of the data, a stale flag, and the model details. The model query parameter chooses xgboost (default), logistic or lstm. If the stored candles are older than two intervals the response is marked stale. Unknown symbols return 404 and unsupported timeframes return 422.

## Why the LSTM looked best
The LSTM had the best balanced accuracy and the least negative net result per trade, but its p-value was still not significant and the gap to the other models was small. With only a year of hourly data no model can be called a clear winner, and none of them beats the trading cost.
