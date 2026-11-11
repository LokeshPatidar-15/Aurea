import numpy as np
import pandas as pd

PATTERN_NAMES = ("bullish_engulfing", "bearish_engulfing", "bullish_pin", "bearish_pin", "inside_bar")


def _parts(df: pd.DataFrame) -> dict:
    o, h, l, c = (df[k].astype(float) for k in ("open", "high", "low", "close"))
    return {
        "o": o, "h": h, "l": l, "c": c,
        "body": (c - o).abs(), "range": h - l,
        "upper": h - np.maximum(o, c), "lower": np.minimum(o, c) - l,
    }


def bullish_engulfing(df: pd.DataFrame, min_body_frac: float = 0.4) -> pd.Series:
    p = _parts(df)
    prev_o, prev_c, prev_body = p["o"].shift(1), p["c"].shift(1), p["body"].shift(1)
    strong = (p["range"] > 0) & (p["body"] >= min_body_frac * p["range"])
    covers = (p["o"] <= prev_c) & (p["c"] >= prev_o) & (p["body"] > prev_body)
    return (strong & (prev_c < prev_o) & (p["c"] > p["o"]) & covers).fillna(False).astype(bool)


def bearish_engulfing(df: pd.DataFrame, min_body_frac: float = 0.4) -> pd.Series:
    p = _parts(df)
    prev_o, prev_c, prev_body = p["o"].shift(1), p["c"].shift(1), p["body"].shift(1)
    strong = (p["range"] > 0) & (p["body"] >= min_body_frac * p["range"])
    covers = (p["o"] >= prev_c) & (p["c"] <= prev_o) & (p["body"] > prev_body)
    return (strong & (prev_c > prev_o) & (p["c"] < p["o"]) & covers).fillna(False).astype(bool)


def bullish_pin(df: pd.DataFrame, wick_frac: float = 0.6, max_other_wick_frac: float = 0.2) -> pd.Series:
    p = _parts(df)
    ok = (p["range"] > 0) & (p["lower"] >= 2 * p["body"]) & (p["lower"] >= wick_frac * p["range"]) & (p["upper"] <= max_other_wick_frac * p["range"])
    return ok.fillna(False).astype(bool)


def bearish_pin(df: pd.DataFrame, wick_frac: float = 0.6, max_other_wick_frac: float = 0.2) -> pd.Series:
    p = _parts(df)
    ok = (p["range"] > 0) & (p["upper"] >= 2 * p["body"]) & (p["upper"] >= wick_frac * p["range"]) & (p["lower"] <= max_other_wick_frac * p["range"])
    return ok.fillna(False).astype(bool)


def inside_bar(df: pd.DataFrame) -> pd.Series:
    h, l = df["high"].astype(float), df["low"].astype(float)
    return ((h < h.shift(1)) & (l > l.shift(1))).fillna(False).astype(bool)


def detect_all(df: pd.DataFrame) -> pd.DataFrame:
    missing = {"open", "high", "low", "close"} - set(df.columns)
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    return pd.DataFrame({
        "bullish_engulfing": bullish_engulfing(df), "bearish_engulfing": bearish_engulfing(df),
        "bullish_pin": bullish_pin(df), "bearish_pin": bearish_pin(df), "inside_bar": inside_bar(df),
    }, index=df.index)
