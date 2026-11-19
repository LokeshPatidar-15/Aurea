from pathlib import Path

ROOT = Path(__file__).parent


def edit(name, pairs, marker):
    path = ROOT / name
    text = path.read_text()
    if marker in text:
        print(f"{name}: already patched")
        return
    for old, new in pairs:
        assert old in text, f"{name}: expected text not found: {old[:60]!r}. Send me this file"
        text = text.replace(old, new, 1)
    path.write_text(text)
    print(f"{name}: patched")


edit(
    "models/__init__.py",
    [("from models.paper import PaperFill, PaperPosition  # noqa: E402,F401\n", "from models.paper import PaperFill, PaperPosition  # noqa: E402,F401\nfrom models.signal_log import SignalLog  # noqa: E402,F401\n")],
    "signal_log",
)

edit(
    "services/candle_pipeline.py",
    [
        ("        min_gap_full_s: float = MIN_GAP_FULL_SECONDS,\n    ):\n        self.hub = hub\n", "        min_gap_full_s: float = MIN_GAP_FULL_SECONDS,\n        record=None,\n    ):\n        self.hub = hub\n        self._record = record\n"),
        (
            '        if mode == "full" and summary["cycle"] is not None and not summary["cycle"]["skipped"]:\n',
            '        if self._record is not None:\n'
            '            try:\n'
            '                summary["recorded"] = await self._to_thread(self._record, list(events.values()))\n'
            '            except Exception as exc:\n'
            '                summary["errors"].append(f"record: {type(exc).__name__}")\n'
            '        if mode == "full" and summary["cycle"] is not None and not summary["cycle"]["skipped"]:\n',
        ),
    ],
    "self._record",
)

edit(
    "main.py",
    [
        ("from routers import portfolio as portfolio_router\n", "from routers import portfolio as portfolio_router\nfrom routers import signals as signals_router\n"),
        ("from services import candle_pipeline, prediction_service, price_service, strategy_service, trading_loop\n", "from services import candle_pipeline, prediction_service, price_service, signal_service, strategy_service, trading_loop\n"),
        ("        symbols=DEFAULT_SYMBOLS,\n    )\n    pipe.scheduler_enabled", "        symbols=DEFAULT_SYMBOLS,\n        record=signal_service.record_events,\n    )\n    pipe.scheduler_enabled"),
        ("app.include_router(portfolio_router.router)\n", "app.include_router(portfolio_router.router)\napp.include_router(signals_router.router)\n"),
    ],
    "signals_router",
)
