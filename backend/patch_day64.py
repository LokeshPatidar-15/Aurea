from pathlib import Path

ROOT = Path(__file__).parent


def edit(name, old, new, marker):
    path = ROOT / name
    text = path.read_text()
    if marker in text:
        print(f"{name}: already patched")
        return
    assert old in text, f"{name}: expected text not found, send me this file"
    path.write_text(text.replace(old, new, 1))
    print(f"{name}: patched")


edit(
    "config.py",
    "    request_timeout_seconds: float = 5\n",
    "    request_timeout_seconds: float = 5\n    ws_poll_seconds: float = 5\n    ws_max_clients: int = 100\n",
    "ws_poll_seconds",
)

edit(
    "main.py",
    "from fastapi import Depends, FastAPI, HTTPException\n",
    "import asyncio\nfrom contextlib import asynccontextmanager, suppress\n\nfrom fastapi import Depends, FastAPI, HTTPException\n",
    "asynccontextmanager",
)

edit(
    "main.py",
    "from routers import backtest as backtest_router\n\napp = FastAPI(\n",
    '''from routers import backtest as backtest_router
from routers import ws as ws_router
from services import price_service
from services.tick_poller import PollingTicker
from services.ws_hub import DEFAULT_SYMBOLS, hub


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.max_clients = settings.ws_max_clients
    hub.meta["poll_seconds"] = settings.ws_poll_seconds
    task = None
    if settings.ws_poll_seconds > 0:
        ticker = PollingTicker(hub, price_service.get_price, DEFAULT_SYMBOLS, max(1.0, settings.ws_poll_seconds))
        task = asyncio.create_task(ticker.run(), name="tick-poller")
    yield
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    lifespan=lifespan,
''',
    "lifespan=lifespan",
)

edit(
    "main.py",
    "app.include_router(loop_router.router)\n",
    "app.include_router(loop_router.router)\napp.include_router(ws_router.router)\n",
    "ws_router.router",
)

env_example = ROOT / ".env.example"
text = env_example.read_text()
if "WS_POLL_SECONDS" not in text:
    env_example.write_text(text.rstrip("\n") + "\nWS_POLL_SECONDS=5\nWS_MAX_CLIENTS=100\n")
    print(".env.example: patched")

gitignore = ROOT / ".gitignore"
text = gitignore.read_text()
added = []
for line in ("artifacts/rag_index/", "artifacts/strategy_trials.jsonl", ".env"):
    if line not in text.splitlines():
        added.append(line)
if added:
    gitignore.write_text(text.rstrip("\n") + "\n" + "\n".join(added) + "\n")
    print(".gitignore: added " + ", ".join(added))
