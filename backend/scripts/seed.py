import argparse
import sys
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from config import settings
from database import engine
from models import PriceHistory, Trade, User
from services.price_service import PriceServiceError, get_candles
from services.trade_service import calculate_pnl

DEMO_EMAIL = "demo@aurea.dev"

DEMO_TRADES = [
    ("BTCUSDT", "long", "61200", "63480", "0.05", "Liquidity sweep + bullish engulfing. Held through a minor pullback."),
    ("XAUUSD", "long", "1961.2", "1952.4", "2", "Entered against the ML signal on a hunch. Trust the model more."),
    ("EURUSD", "long", "1.0860", "1.0912", "1000", "RSI reversal template, clean setup."),
    ("BTCUSDT", "short", "64000", "63000", "0.1", "Rejected at resistance."),
    ("XAUUSD", "short", "1950", "1960", "1", "Stopped out."),
    ("EURUSD", "short", "1.0950", "1.0900", "2000", "Range-bound, small win."),
]


def make_trade(symbol, direction, entry, exit_, qty, notes):
    entry, exit_, qty = Decimal(entry), Decimal(exit_), Decimal(qty)
    return Trade(
        symbol=symbol,
        direction=direction,
        entry_price=entry,
        exit_price=exit_,
        quantity=qty,
        pnl=calculate_pnl(entry, exit_, qty, direction),
        notes=notes,
    )


def seed_demo_user(session: Session, reset: bool) -> None:
    user = session.scalars(select(User).where(User.email == DEMO_EMAIL)).first()

    if user and reset:
        session.delete(user)
        session.commit()
        user = None
        print("demo user and their trades deleted (--reset)")

    if user:
        print("demo user exists, trades skipped (run with --reset to recreate)")
        return

    user = User(email=DEMO_EMAIL, hashed_password="!seed-account-login-disabled")
    user.trades = [make_trade(*row) for row in DEMO_TRADES]
    session.add(user)
    session.commit()
    print(f"demo user created with {len(DEMO_TRADES)} trades")


def seed_candles(session: Session) -> None:
    try:
        candles = get_candles("BTCUSDT", "1h", 100)
    except PriceServiceError as e:
        print(f"candles skipped (Binance unreachable): {e}")
        return

    rows = [
        {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "open_time": datetime.fromtimestamp(c["time"] / 1000, tz=timezone.utc),
            "open": Decimal(str(c["open"])),
            "high": Decimal(str(c["high"])),
            "low": Decimal(str(c["low"])),
            "close": Decimal(str(c["close"])),
            "volume": Decimal(str(c["volume"])),
        }
        for c in candles
    ]
    scope = (PriceHistory.symbol == "BTCUSDT", PriceHistory.timeframe == "1h")
    before = session.scalar(select(func.count()).select_from(PriceHistory).where(*scope))
    session.execute(pg_insert(PriceHistory.__table__).values(rows).on_conflict_do_nothing())
    session.commit()
    after = session.scalar(select(func.count()).select_from(PriceHistory).where(*scope))
    inserted = after - before
    print(f"BTCUSDT 1h candles: {inserted} inserted, {len(rows) - inserted} already present")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Aurea dev database.")
    parser.add_argument("--reset", action="store_true", help="recreate the demo user and their trades")
    args = parser.parse_args()

    if settings.is_production:
        sys.exit("Refusing to seed: APP_ENV is production.")

    with Session(engine) as session:
        seed_demo_user(session, args.reset)
        seed_candles(session)


if __name__ == "__main__":
    main()
