import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn

ARTIFACT_DIR = Path(__file__).parent.parent / "artifacts"
SCHEMA_VERSION = 1


def artifact_path(symbol: str, timeframe: str) -> Path:
    return ARTIFACT_DIR / f"{symbol}_{timeframe}.joblib"


def library_versions() -> dict:
    versions = {
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit-learn": sklearn.__version__,
    }
    try:
        import xgboost

        versions["xgboost"] = xgboost.__version__
    except ImportError:
        pass
    return versions


def save_artifact(symbol: str, timeframe: str, payload: dict) -> Path:
    ARTIFACT_DIR.mkdir(exist_ok=True)
    path = artifact_path(symbol, timeframe)
    payload = {
        **payload,
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol,
        "timeframe": timeframe,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "versions": library_versions(),
    }
    temporary = path.with_suffix(".tmp")
    joblib.dump(payload, temporary)
    temporary.replace(path)
    return path


def read_artifact(symbol: str, timeframe: str) -> dict:
    path = artifact_path(symbol, timeframe)
    if not path.exists():
        raise FileNotFoundError(path)
    return joblib.load(path)
