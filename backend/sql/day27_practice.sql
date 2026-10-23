\echo '=== 0. SETUP: table aur view ==='
DROP VIEW IF EXISTS practice_trade_pnl;
DROP TABLE IF EXISTS practice_trades;

CREATE TABLE practice_trades (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    direction VARCHAR(5) NOT NULL CHECK (direction IN ('long', 'short')),
    entry_price NUMERIC(18, 8) NOT NULL CHECK (entry_price > 0),
    exit_price NUMERIC(18, 8) NOT NULL CHECK (exit_price > 0),
    quantity NUMERIC(18, 8) NOT NULL CHECK (quantity > 0),
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE VIEW practice_trade_pnl AS
SELECT id, symbol, direction, entry_price, exit_price, quantity, notes,
       ROUND(
           (CASE WHEN direction = 'long' THEN exit_price - entry_price
                 ELSE entry_price - exit_price END) * quantity,
           2
       ) AS pnl
FROM practice_trades;

\echo ''
\echo '=== 1. INSERT: 6 trades add karo ==='
INSERT INTO practice_trades (symbol, direction, entry_price, exit_price, quantity, notes) VALUES
    ('BTCUSDT', 'long',  61200,  63480,  0.05, 'liquidity sweep + engulfing'),
    ('XAUUSD',  'long',  1961.2, 1952.4, 2,    'against ML signal'),
    ('EURUSD',  'long',  1.0860, 1.0912, 1000, 'RSI reversal'),
    ('BTCUSDT', 'short', 64000,  63000,  0.1,  'rejected at resistance'),
    ('XAUUSD',  'short', 1950,   1960,   1,    'stopped out'),
    ('EURUSD',  'short', 1.0950, 1.0900, 2000, '');

\echo ''
\echo '=== 2. SELECT: sab rows ==='
SELECT id, symbol, direction, entry_price, exit_price, quantity, notes
FROM practice_trades
ORDER BY id;

\echo ''
\echo '=== 3. SELECT with computed P&L (view se) ==='
SELECT id, symbol, direction, pnl FROM practice_trade_pnl ORDER BY id;

\echo ''
\echo '=== 4. WHERE: sirf losing trades ==='
SELECT id, symbol, pnl FROM practice_trade_pnl WHERE pnl < 0 ORDER BY pnl;

\echo ''
\echo '=== 5. ORDER BY + LIMIT: top 3 profitable ==='
SELECT id, symbol, pnl FROM practice_trade_pnl ORDER BY pnl DESC LIMIT 3;

\echo ''
\echo '=== 6. Aggregate: total trades, total P&L, win rate ==='
SELECT COUNT(*) AS trades,
       SUM(pnl) AS total_pnl,
       ROUND(100.0 * COUNT(*) FILTER (WHERE pnl > 0) / COUNT(*), 1) AS win_rate_pct
FROM practice_trade_pnl;

\echo ''
\echo '=== 7. GROUP BY: symbol ke hisaab se ==='
SELECT symbol, COUNT(*) AS trades, SUM(pnl) AS total_pnl
FROM practice_trade_pnl
GROUP BY symbol
ORDER BY total_pnl DESC;

\echo ''
\echo '=== 8. UPDATE: ek trade ke notes badlo (WHERE ke saath) ==='
UPDATE practice_trades SET notes = 'reviewed: entered against the ML signal' WHERE id = 2;
SELECT id, symbol, notes FROM practice_trades WHERE id = 2;

\echo ''
\echo '=== 9. DELETE: trade 6 hatao, phir aggregate dobara ==='
DELETE FROM practice_trades WHERE id = 6;
SELECT COUNT(*) AS trades,
       SUM(pnl) AS total_pnl,
       ROUND(100.0 * COUNT(*) FILTER (WHERE pnl > 0) / COUNT(*), 1) AS win_rate_pct
FROM practice_trade_pnl;

\echo ''
\echo '=== 10. CONSTRAINT: database galat data reject karta hai (ERROR aana expected hai) ==='
INSERT INTO practice_trades (symbol, direction, entry_price, exit_price, quantity)
VALUES ('BTCUSDT', 'long', 100, 110, -1);
INSERT INTO practice_trades (symbol, direction, entry_price, exit_price, quantity)
VALUES ('BTCUSDT', 'sideways', 100, 110, 1);

\echo ''
\echo '=== 11. TRANSACTION: WHERE bhool gaye to ROLLBACK se bach jao ==='
BEGIN;
UPDATE practice_trades SET notes = 'OOPS';
SELECT COUNT(*) AS rows_saying_oops_inside_transaction FROM practice_trades WHERE notes = 'OOPS';
ROLLBACK;
SELECT COUNT(*) AS rows_saying_oops_after_rollback FROM practice_trades WHERE notes = 'OOPS';

\echo ''
\echo '=== 12. TRANSACTION: price badalne se P&L badalta hai, rollback se wapas ==='
BEGIN;
UPDATE practice_trades SET exit_price = 1970 WHERE id = 2;
SELECT id, pnl AS pnl_inside_transaction FROM practice_trade_pnl WHERE id = 2;
ROLLBACK;
SELECT id, pnl AS pnl_after_rollback FROM practice_trade_pnl WHERE id = 2;
