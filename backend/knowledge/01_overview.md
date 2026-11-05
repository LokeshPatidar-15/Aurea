# Aurea overview

## What Aurea is
Aurea is an AI-assisted trading research platform built as a final-year AIML project. It has a React frontend, a FastAPI backend, a PostgreSQL database, machine learning models, a rule-based strategy, a paper-trading broker with a risk engine, and a RAG copilot that answers questions about all of it.

## Symbols and timeframes
Aurea covers three symbols: BTCUSDT, XAUUSD (gold, using the PAXGUSDT market on Binance as a proxy) and EURUSD (using the EURUSDT market as a proxy). The main timeframe is 1 hour. A 15 minute timeframe is also stored.

## Research only, not advice
Every model output and every strategy signal is flagged research_only. No model and no rule-based strategy has shown a net edge after trading costs. Aurea never places real orders: it only paper trades, with a simulated account that starts at 10,000.

## Where the database runs
Aurea uses its own PostgreSQL instance on port 5433, with data stored in the home folder under .aurea/pgdata. It is kept separate from any other database on the machine. The helper script tools/aurea_db.sh starts, stops and opens a shell on that instance. After a computer restart the database must be started again with tools/aurea_db.sh start.

## Backend layout
The backend runs on port 8010. Code is split into routers (HTTP endpoints), schemas (request and response shapes), services (business logic), models (database tables) and analysis (research code such as features, labels, backtests).
