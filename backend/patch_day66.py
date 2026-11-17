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


HUB_METHODS = '''    def _event_problem(self, event, needs_symbol: bool) -> str | None:
        if not isinstance(event, dict):
            return "not_a_dict"
        if needs_symbol:
            symbol = event.get("symbol")
            if not isinstance(symbol, str) or symbol not in self.symbols:
                return "unknown_symbol"
            if not isinstance(event.get("fresh"), bool):
                return "bad_fresh"
            for key in ("rule", "model"):
                if event.get(key) is not None and not isinstance(event[key], dict):
                    return "bad_" + key
        for key in ("candle_time", "computed_at"):
            value = event.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                return "bad_time"
        return None

    def _event_text(self, event: dict, kind: str, prefix: str) -> str | None:
        self._event_seq += 1
        out = {**event, "type": kind, "seq": self._event_seq, "server_time": self._wall_ms()}
        try:
            text = _dumps(out)
        except (TypeError, ValueError):
            self.rejected[prefix + "_not_serialisable"] += 1
            return None
        if len(text) > MAX_EVENT_CHARS:
            self.rejected[prefix + "_too_large"] += 1
            return None
        return text

    def publish_signal(self, event: dict) -> bool:
        problem = self._event_problem(event, True)
        if problem:
            self.rejected["signal_" + problem] += 1
            return False
        text = self._event_text(event, "signal", "signal")
        if text is None:
            return False
        out = json.loads(text)
        self.latest_signals[out["symbol"]] = (out, text)
        self.stats["signals_published"] += 1
        for client in list(self.clients.values()):
            if not client.closed and out["symbol"] in client.symbols:
                self._send_text(client, text)
        return True

    def publish_paper_tick(self, event: dict) -> bool:
        problem = self._event_problem(event, False)
        if problem:
            self.rejected["paper_tick_" + problem] += 1
            return False
        text = self._event_text(event, "paper_tick", "paper_tick")
        if text is None:
            return False
        self.stats["paper_ticks_published"] += 1
        for client in list(self.clients.values()):
            if not client.closed:
                self._send_text(client, text)
        return True

'''

edit(
    "services/ws_hub.py",
    [
        (
            "FLUSH_WAIT_SECONDS = 2.0\n",
            "FLUSH_WAIT_SECONDS = 2.0\nMAX_EVENT_CHARS = 8000\n",
        ),
        (
            "        self.proxies: dict = {}\n",
            "        self.proxies: dict = {}\n        self.latest_signals: dict[str, tuple[dict, str]] = {}\n        self._event_seq = 0\n",
        ),
        (
            '                "proxies": dict(self.proxies),\n',
            '                "proxies": dict(self.proxies),\n                "events": ["tick", "signal", "paper_tick"],\n',
        ),
        (
            "    def _send_control(self, client: Client, message: dict) -> None:\n",
            "    def _send_text(self, client: Client, text: str) -> None:\n"
            "        if client.closed:\n"
            "            return\n"
            "        if len(client.control) >= self.max_control_backlog:\n"
            "            self.stats[\"clients_closed_backlog\"] += 1\n"
            "            self.close_client(client, 1008, \"backlog\")\n"
            "            return\n"
            "        client.control.append(text)\n"
            "        client.wake.set()\n\n"
            "    def _send_control(self, client: Client, message: dict) -> None:\n",
        ),
        (
            "                    client.pending[symbol] = entry[1]\n                    client.wake.set()\n",
            "                    client.pending[symbol] = entry[1]\n                    client.wake.set()\n"
            "                signal_entry = self.latest_signals.get(symbol)\n"
            "                if signal_entry:\n"
            "                    self._send_text(client, signal_entry[1])\n",
        ),
        (
            "    async def pump(self, client: Client, send) -> None:\n",
            HUB_METHODS + "    async def pump(self, client: Client, send) -> None:\n",
        ),
        (
            '            "ticks_rejected": dict(self.rejected),\n',
            '            "ticks_rejected": dict(self.rejected),\n'
            '            "signals": {\n'
            '                s: {"candle_time": e["candle_time"], "computed_at": e["computed_at"], "fresh": e["fresh"], "rule": (e.get("rule") or {}).get("status"), "model": (e.get("model") or {}).get("signal")}\n'
            "                for s, (e, _) in self.latest_signals.items()\n"
            "            },\n",
        ),
    ],
    "publish_paper_tick",
)

edit(
    "services/trading_loop.py",
    [
        (
            "def run_cycle(ingest: bool = True, place_orders: bool = True, symbols=None) -> dict:\n",
            "def run_cycle(ingest: bool = True, place_orders: bool = True, symbols=None) -> dict:\n"
            "    from services.cycle_lock import run_exclusive\n\n"
            "    return run_exclusive(lambda: _run_cycle_unlocked(ingest, place_orders, symbols))\n\n\n"
            "def _run_cycle_unlocked(ingest: bool = True, place_orders: bool = True, symbols=None) -> dict:\n",
        ),
    ],
    "run_exclusive",
)

edit(
    "config.py",
    [
        (
            '    binance_ws_url: str = "wss://stream.binance.com:9443/stream"\n',
            '    binance_ws_url: str = "wss://stream.binance.com:9443/stream"\n    pipeline_enabled: bool = True\n    pipeline_place_orders: bool = False\n',
        ),
    ],
    "pipeline_enabled",
)

edit(
    "main.py",
    [
        (
            "from routers import ws as ws_router\n",
            "from routers import pipeline as pipeline_router\nfrom routers import ws as ws_router\n",
        ),
        (
            "from services import price_service\n",
            "from services import candle_pipeline, prediction_service, price_service, strategy_service, trading_loop\n",
        ),
        (
            "    yield\n    for task in tasks:\n        task.cancel()\n",
            '''    pipe = candle_pipeline.CandlePipeline(
        hub,
        cycle=lambda: trading_loop.run_cycle(ingest=True, place_orders=settings.pipeline_place_orders),
        rule_signal=strategy_service.latest_signal,
        model_signal=lambda symbol: prediction_service.predict(symbol, "1h", "xgboost"),
        symbols=DEFAULT_SYMBOLS,
    )
    pipe.scheduler_enabled = settings.pipeline_enabled
    pipe.place_orders = settings.pipeline_place_orders
    candle_pipeline.set_pipeline(pipe)
    hub.meta["pipeline"] = pipe.status
    if settings.pipeline_enabled:
        tasks.append(asyncio.create_task(pipe.run(), name="candle-pipeline"))
    yield
    for task in tasks:
        task.cancel()
    candle_pipeline.set_pipeline(None)
''',
        ),
        (
            "app.include_router(ws_router.router)\n",
            "app.include_router(ws_router.router)\napp.include_router(pipeline_router.router)\n",
        ),
    ],
    "CandlePipeline",
)

env_example = ROOT / ".env.example"
text = env_example.read_text()
if "PIPELINE_ENABLED" not in text:
    env_example.write_text(text.rstrip("\n") + "\nPIPELINE_ENABLED=true\nPIPELINE_PLACE_ORDERS=false\n")
    print(".env.example: patched")

day64_checks = ROOT / "analysis" / "day64_checks.py"
if day64_checks.exists():
    text = day64_checks.read_text()
    old = 'r"paper_|sqlalchemy|session|\\.execute\\("'
    new = 'r"paper_(?!tick)|sqlalchemy|session|\\.execute\\("'
    if new in text:
        print("day64_checks.py: already patched")
    elif old in text:
        day64_checks.write_text(text.replace(old, new))
        print("day64_checks.py: patched")
    else:
        print("day64_checks.py: pattern not found (skipped)")
