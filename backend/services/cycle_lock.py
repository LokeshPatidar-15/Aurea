import logging
from contextlib import contextmanager
from datetime import datetime, timezone

log = logging.getLogger("aurea.cycle")

CYCLE_LOCK_KEY = 6_600_641


class SqlAlchemyAdvisoryLock:
    def __init__(self):
        from database import engine

        self._conn = engine.connect()

    def try_lock(self, key: int) -> bool:
        from sqlalchemy import text

        return bool(self._conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}).scalar())

    def unlock(self, key: int) -> None:
        from sqlalchemy import text

        self._conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})

    def discard(self) -> None:
        self._conn.invalidate()

    def close(self) -> None:
        try:
            self._conn.rollback()
        finally:
            self._conn.close()


@contextmanager
def cycle_lock(factory=None, key: int = CYCLE_LOCK_KEY):
    lock = (factory or SqlAlchemyAdvisoryLock)()
    held = False
    try:
        held = bool(lock.try_lock(key))
        yield held
    finally:
        try:
            if held:
                lock.unlock(key)
        except Exception as exc:
            log.warning("cycle lock release failed (%s), discarding the connection", type(exc).__name__)
            discard = getattr(lock, "discard", None)
            if discard:
                discard()
        finally:
            lock.close()


def skipped_log(reason: str = "another cycle is already running, this one was skipped") -> dict:
    now = datetime.now(timezone.utc)
    return {"started_at": now, "finished_at": now, "ingest": None, "tick": None, "symbols": {}, "errors": [reason], "skipped": True}


def run_exclusive(fn, factory=None, key: int = CYCLE_LOCK_KEY) -> dict:
    with cycle_lock(factory, key) as acquired:
        if not acquired:
            return skipped_log()
        return fn()
