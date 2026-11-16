import fcntl
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "artifacts" / "strategy_trials.jsonl"


class TrialLog:
    def __init__(self, path=DEFAULT_PATH):
        self.path = Path(path)

    @staticmethod
    def _parse(text: str) -> list:
        entries = []
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and "key" in row and "symbol" in row:
                entries.append(row)
        return entries

    def record(self, key: str, symbol: str, name: str = "", long_text: str | None = None, short_text: str | None = None) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.seek(0)
                entries = self._parse(f.read())
                seen = {(e["key"], e["symbol"]) for e in entries}
                new = (key, symbol) not in seen
                if new:
                    row = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "key": key, "symbol": symbol, "name": str(name)[:60],
                           "long": long_text, "short": short_text}
                    f.seek(0, 2)
                    f.write(json.dumps(row) + "\n")
                    f.flush()
                    entries.append(row)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        return {"count": len(entries), "new": new}

    def entries(self) -> list:
        if not self.path.exists():
            return []
        return self._parse(self.path.read_text(encoding="utf-8"))

    def count(self) -> int:
        return len(self.entries())
