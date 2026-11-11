from dataclasses import dataclass

import numpy as np
import pandas as pd

from analysis import patterns
from analysis.indicators import ema

MAX_DEPTH = 8


class UnknownCondition(KeyError):
    pass


class RuleError(ValueError):
    pass


class Context:
    def __init__(self, cleaned: pd.DataFrame, feats: pd.DataFrame):
        self.cleaned = cleaned
        self.feats = feats.reindex(cleaned.index)
        self.index = cleaned.index
        self._cache: dict = {}

    def cached(self, key: str, fn):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    def pattern(self, name: str) -> pd.Series:
        return self.cached("patterns", lambda: patterns.detect_all(self.cleaned))[name]

    def ema(self, window: int) -> pd.Series:
        return self.cached(f"ema{window}", lambda: ema(self.cleaned["close"], window))

    def flag(self, column: str) -> pd.Series:
        return self.feats[column].fillna(False).astype(bool)

    def num(self, column: str) -> pd.Series:
        return self.feats[column].astype(float)


CONDITIONS = {
    "sweep_bull": ("Wick below the last swing low, close back above it (bullish liquidity sweep)", lambda c: c.flag("sweep_bull")),
    "sweep_bear": ("Wick above the last swing high, close back below it (bearish liquidity sweep)", lambda c: c.flag("sweep_bear")),
    "bullish_engulfing": ("Bullish candle whose body engulfs the previous bearish body", lambda c: c.pattern("bullish_engulfing")),
    "bearish_engulfing": ("Bearish candle whose body engulfs the previous bullish body", lambda c: c.pattern("bearish_engulfing")),
    "bullish_pin": ("Hammer: long lower wick, small body, tiny upper wick", lambda c: c.pattern("bullish_pin")),
    "bearish_pin": ("Shooting star: long upper wick, small body, tiny lower wick", lambda c: c.pattern("bearish_pin")),
    "inside_bar": ("High below and low above the previous candle's range", lambda c: c.pattern("inside_bar")),
    "trend_up": ("EMA50 is above EMA200", lambda c: (c.ema(50) > c.ema(200)).fillna(False)),
    "trend_down": ("EMA50 is below EMA200", lambda c: (c.ema(50) < c.ema(200)).fillna(False)),
    "volume_ok": ("Volume z-score is at least 0 (not below average)", lambda c: (c.num("vol_z") >= 0).fillna(False)),
    "volume_high": ("Volume z-score is at least 1", lambda c: (c.num("vol_z") >= 1).fillna(False)),
    "rsi_oversold": ("RSI(14) below 30", lambda c: (c.num("rsi_14") < 30).fillna(False)),
    "rsi_overbought": ("RSI(14) above 70", lambda c: (c.num("rsi_14") > 70).fillna(False)),
    "clean_bar": ("Candle is neither gap-filled nor an outlier", lambda c: ~(c.flag("is_filled") | c.flag("is_outlier"))),
}


def condition_names() -> list:
    return list(CONDITIONS)


class Expr:
    def __and__(self, other: "Expr") -> "Expr":
        return And(_flat(And, self) + _flat(And, other))

    def __or__(self, other: "Expr") -> "Expr":
        return Or(_flat(Or, self) + _flat(Or, other))

    def __invert__(self) -> "Expr":
        return Not(self)


def _flat(kind, expr) -> tuple:
    return expr.children if isinstance(expr, kind) else (expr,)


@dataclass(frozen=True)
class Cond(Expr):
    name: str


@dataclass(frozen=True)
class And(Expr):
    children: tuple

    def __post_init__(self):
        if not self.children:
            raise RuleError("AND needs at least one condition")


@dataclass(frozen=True)
class Or(Expr):
    children: tuple

    def __post_init__(self):
        if not self.children:
            raise RuleError("OR needs at least one condition")


@dataclass(frozen=True)
class Not(Expr):
    child: Expr


def evaluate(expr: Expr, ctx: Context) -> pd.Series:
    if isinstance(expr, Cond):
        if expr.name not in CONDITIONS:
            raise UnknownCondition(f"unknown condition {expr.name!r}. Valid: {', '.join(CONDITIONS)}")
        return ctx.cached("cond:" + expr.name, lambda: CONDITIONS[expr.name][1](ctx).reindex(ctx.index).fillna(False).astype(bool))
    if isinstance(expr, And):
        out = evaluate(expr.children[0], ctx)
        for child in expr.children[1:]:
            out = out & evaluate(child, ctx)
        return out
    if isinstance(expr, Or):
        out = evaluate(expr.children[0], ctx)
        for child in expr.children[1:]:
            out = out | evaluate(child, ctx)
        return out
    if isinstance(expr, Not):
        return ~evaluate(expr.child, ctx)
    raise RuleError(f"not a rule expression: {expr!r}")


def describe(expr: Expr) -> str:
    if isinstance(expr, Cond):
        return expr.name
    if isinstance(expr, And):
        return "(" + " AND ".join(describe(c) for c in expr.children) + ")"
    if isinstance(expr, Or):
        return "(" + " OR ".join(describe(c) for c in expr.children) + ")"
    if isinstance(expr, Not):
        return "NOT " + describe(expr.child)
    raise RuleError(f"not a rule expression: {expr!r}")


def names_used(expr: Expr) -> set:
    if isinstance(expr, Cond):
        return {expr.name}
    if isinstance(expr, Not):
        return names_used(expr.child)
    return set().union(*(names_used(c) for c in expr.children))


def to_dict(expr: Expr):
    if isinstance(expr, Cond):
        return expr.name
    if isinstance(expr, And):
        return {"all": [to_dict(c) for c in expr.children]}
    if isinstance(expr, Or):
        return {"any": [to_dict(c) for c in expr.children]}
    if isinstance(expr, Not):
        return {"not": to_dict(expr.child)}
    raise RuleError(f"not a rule expression: {expr!r}")


def from_dict(data, _depth: int = 0) -> Expr:
    if _depth > MAX_DEPTH:
        raise RuleError(f"rule is nested deeper than {MAX_DEPTH} levels")
    if isinstance(data, str):
        if data not in CONDITIONS:
            raise UnknownCondition(f"unknown condition {data!r}. Valid: {', '.join(CONDITIONS)}")
        return Cond(data)
    if not isinstance(data, dict) or len(data) != 1:
        raise RuleError("a rule is a condition name or an object with exactly one key: all, any or not")
    (key, value), = data.items()
    if key in ("all", "any"):
        if not isinstance(value, list) or not value:
            raise RuleError(f"'{key}' needs a non-empty list")
        children = tuple(from_dict(v, _depth + 1) for v in value)
        return And(children) if key == "all" else Or(children)
    if key == "not":
        return Not(from_dict(value, _depth + 1))
    raise RuleError(f"unknown key {key!r}: use all, any or not")


STOP_MODES = ("candle", "two_candle")


@dataclass(frozen=True)
class RuleStrategy:
    name: str
    long: Expr | None = None
    short: Expr | None = None
    stop_mode: str = "candle"
    stop_buffer_atr: float = 0.25

    def __post_init__(self):
        if self.long is None and self.short is None:
            raise RuleError("a strategy needs a long rule, a short rule or both")
        if self.stop_mode not in STOP_MODES:
            raise RuleError(f"stop_mode must be one of {STOP_MODES}")
        if not (0 <= self.stop_buffer_atr <= 3):
            raise RuleError("stop_buffer_atr must be between 0 and 3")

    def to_dict(self) -> dict:
        return {"name": self.name, "long": to_dict(self.long) if self.long else None, "short": to_dict(self.short) if self.short else None,
                "stop_mode": self.stop_mode, "stop_buffer_atr": self.stop_buffer_atr}

    @classmethod
    def from_dict(cls, data: dict) -> "RuleStrategy":
        if not isinstance(data, dict):
            raise RuleError("a strategy is an object")
        return cls(name=str(data.get("name", "custom")), long=from_dict(data["long"]) if data.get("long") is not None else None,
                   short=from_dict(data["short"]) if data.get("short") is not None else None,
                   stop_mode=data.get("stop_mode", "candle"), stop_buffer_atr=float(data.get("stop_buffer_atr", 0.25)))


def generate_rule_signals(cleaned: pd.DataFrame, feats: pd.DataFrame, strategy: RuleStrategy) -> pd.DataFrame:
    ctx = Context(cleaned, feats)
    zero = pd.Series(False, index=cleaned.index)
    long_setup = evaluate(strategy.long, ctx) if strategy.long is not None else zero
    short_setup = evaluate(strategy.short, ctx) if strategy.short is not None else zero
    both = long_setup & short_setup
    long_setup, short_setup = long_setup & ~both, short_setup & ~both
    close = cleaned["close"]
    atr = ctx.num("atr_14_pct") * close
    low, high = cleaned["low"], cleaned["high"]
    if strategy.stop_mode == "two_candle":
        low, high = np.minimum(low, low.shift(1)), np.maximum(high, high.shift(1))
    out = pd.DataFrame(index=cleaned.index)
    out["side"] = np.where(long_setup, 1, np.where(short_setup, -1, 0))
    out["stop"] = np.where(long_setup, low - strategy.stop_buffer_atr * atr, np.where(short_setup, high + strategy.stop_buffer_atr * atr, np.nan))
    out["atr"] = atr
    out.loc[~atr.notna(), "side"] = 0
    out.loc[out["stop"].isna(), "side"] = 0
    return out
