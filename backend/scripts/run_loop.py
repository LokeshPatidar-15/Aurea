import argparse
import sys
import time
from datetime import datetime, timezone

from services import trading_loop


def main() -> None:
    parser = argparse.ArgumentParser(description="Hourly paper-trading loop: ingest, tick, signals, orders.")
    parser.add_argument("--once", action="store_true", help="run one cycle and exit")
    parser.add_argument("--no-ingest", action="store_true", help="skip the Binance download (use stored candles)")
    parser.add_argument("--no-orders", action="store_true", help="log signals but never place orders")
    args = parser.parse_args()

    while True:
        try:
            log = trading_loop.run_cycle(ingest=not args.no_ingest, place_orders=not args.no_orders)
            print(trading_loop.format_cycle(log), flush=True)
            for error in log["errors"]:
                print("  error:", error, flush=True)
        except Exception as exc:
            print(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z cycle crashed: {exc}", flush=True)
            if args.once:
                sys.exit(1)
        if args.once:
            return
        wait = trading_loop.seconds_until_next_run(datetime.now(timezone.utc))
        print(f"  next run in {wait / 60:.1f} min (Ctrl+C to stop)", flush=True)
        time.sleep(wait)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nloop stopped")
