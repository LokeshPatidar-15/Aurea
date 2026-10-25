import itertools
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ARTIFACT_DIR = Path(__file__).parent.parent / "artifacts"

GRID = {
    "max_depth": [2, 3, 4],
    "min_child_weight": [10, 20, 50],
    "learning_rate": [0.03, 0.06],
}


def grid_combinations(grid: dict = GRID) -> list[dict]:
    keys = list(grid)
    return [dict(zip(keys, values)) for values in itertools.product(*grid.values())]


def best_params_path(symbol: str, timeframe: str) -> Path:
    return ARTIFACT_DIR / f"best_params_{symbol}_{timeframe}.json"


def save_best_params(symbol: str, timeframe: str, payload: dict) -> Path:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    path = best_params_path(symbol, timeframe)
    payload = {**payload, "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_best_params(symbol: str, timeframe: str) -> dict | None:
    path = best_params_path(symbol, timeframe)
    if not path.exists():
        return None
    return json.loads(path.read_text())["params"]
