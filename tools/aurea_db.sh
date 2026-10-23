#!/usr/bin/env bash
set -uo pipefail

AUREA_HOME="$HOME/.aurea"
DATA_DIR="$AUREA_HOME/pgdata"
PGBIN="$(cat "$AUREA_HOME/pgbin")"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

case "${1:-}" in
  start)
    "$PGBIN/pg_ctl" -D "$DATA_DIR" -l "$AUREA_HOME/pg.log" start
    ;;
  stop)
    "$PGBIN/pg_ctl" -D "$DATA_DIR" stop
    ;;
  status)
    echo "Aurea database (port 5433):"
    "$PGBIN/pg_isready" -h localhost -p 5433
    echo "Other server (port 5432, not managed by Aurea):"
    "$PGBIN/pg_isready" -h localhost -p 5432
    ;;
  psql)
    shift
    URL="$(grep '^DATABASE_URL=' "$ROOT/backend/.env" | cut -d= -f2-)"
    exec "$PGBIN/psql" "$URL" "$@"
    ;;
  *)
    echo "usage: tools/aurea_db.sh {start|stop|status|psql [psql args]}"
    ;;
esac
