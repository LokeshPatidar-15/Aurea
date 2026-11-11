from analysis.rules import MAX_DEPTH, RuleError, RuleStrategy, STOP_MODES, UnknownCondition, describe, from_dict, names_used

MAX_NODES = 40
MAX_CHILDREN = 12
MAX_NAME = 60
ALLOWED_KEYS = {"name", "long", "short", "stop_mode", "stop_buffer_atr"}


def measure(data, depth: int = 0, counter: list | None = None) -> int:
    counter = counter if counter is not None else [0]
    if depth > MAX_DEPTH:
        raise RuleError(f"rule is nested deeper than {MAX_DEPTH} levels")
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise RuleError(f"rule is too large (more than {MAX_NODES} parts)")
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                if len(value) > MAX_CHILDREN:
                    raise RuleError(f"a list can hold at most {MAX_CHILDREN} conditions")
                for item in value:
                    measure(item, depth + 1, counter)
            else:
                measure(value, depth + 1, counter)
    return counter[0]


def _short(text, limit: int = 200) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit] + "..."


def _message(exc: Exception) -> str:
    return _short(exc.args[0] if isinstance(exc, KeyError) and exc.args else exc)


def validate_payload(data) -> dict:
    errors, exprs, nodes = [], {}, 0
    if not isinstance(data, dict):
        return {"valid": False, "errors": ["a strategy is a JSON object"], "strategy": None, "long_text": None, "short_text": None, "conditions_used": [], "nodes": 0}
    extra = sorted(str(k) for k in data if k not in ALLOWED_KEYS)
    if extra:
        errors.append(f"unknown field(s): {', '.join(_short(e, 40) for e in extra)}. Allowed: {', '.join(sorted(ALLOWED_KEYS))}")
    name = data.get("name", "custom")
    if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME or not name.isprintable():
        errors.append(f"name must be 1-{MAX_NAME} printable characters")
        name = "custom"
    stop_mode = data.get("stop_mode", "candle")
    if not isinstance(stop_mode, str) or stop_mode not in STOP_MODES:
        errors.append(f"stop_mode must be one of {list(STOP_MODES)}")
        stop_mode = "candle"
    buffer = data.get("stop_buffer_atr", 0.25)
    if isinstance(buffer, bool) or not isinstance(buffer, (int, float)) or not (0 <= buffer <= 3):
        errors.append("stop_buffer_atr must be a number between 0 and 3")
        buffer = 0.25
    for side in ("long", "short"):
        raw = data.get(side)
        if raw is None:
            continue
        try:
            nodes += measure(raw)
            exprs[side] = from_dict(raw)
        except (RuleError, UnknownCondition) as exc:
            errors.append(f"{side}: {_message(exc)}")
    if not errors and not exprs:
        errors.append("a strategy needs a long rule, a short rule or both")
    if errors:
        return {"valid": False, "errors": errors, "strategy": None, "long_text": None, "short_text": None, "conditions_used": [], "nodes": nodes}
    strategy = RuleStrategy(name=name.strip(), long=exprs.get("long"), short=exprs.get("short"), stop_mode=stop_mode, stop_buffer_atr=float(buffer))
    used = set()
    for e in exprs.values():
        used |= names_used(e)
    return {"valid": True, "errors": [], "strategy": strategy.to_dict(), "long_text": describe(strategy.long) if strategy.long else None,
            "short_text": describe(strategy.short) if strategy.short else None, "conditions_used": sorted(used), "nodes": nodes}


def build_strategy(data) -> RuleStrategy:
    result = validate_payload(data)
    if not result["valid"]:
        raise RuleError("; ".join(result["errors"]))
    return RuleStrategy.from_dict(result["strategy"])
