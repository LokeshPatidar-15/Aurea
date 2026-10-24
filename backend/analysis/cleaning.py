from dataclasses import dataclass, field

import numpy as np
import pandas as pd

TIMEFRAME_FREQ = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}
PRICE_COLS = ["open", "high", "low", "close"]


@dataclass
class CleaningReport:
    rows_in: int = 0
    duplicates_removed: int = 0
    invalid_rows_removed: int = 0
    gaps_found: int = 0
    candles_filled: int = 0
    gaps_left_open: int = 0
    outliers_flagged: int = 0
    rows_out: int = 0
    notes: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if k != "notes"}


def remove_duplicates(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    dup_mask = df.index.duplicated(keep="last")
    return df[~dup_mask], int(dup_mask.sum())


def remove_invalid_ohlc(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    body_high = df[["open", "close"]].max(axis=1)
    body_low = df[["open", "close"]].min(axis=1)
    bad = (
        df[PRICE_COLS].isna().any(axis=1)
        | (df[PRICE_COLS] <= 0).any(axis=1)
        | (df["high"] < body_high)
        | (df["low"] > body_low)
        | (df["volume"] < 0)
    )
    return df[~bad], int(bad.sum())


def fill_gaps(df: pd.DataFrame, timeframe: str, max_fill: int = 3) -> tuple[pd.DataFrame, dict]:
    freq = TIMEFRAME_FREQ[timeframe]
    full_index = pd.date_range(df.index[0], df.index[-1], freq=freq, tz="UTC")
    out = df.reindex(full_index)
    out.index.name = df.index.name
    missing = out["close"].isna()

    run_id = (missing != missing.shift()).cumsum()
    run_len = missing.groupby(run_id).transform("sum")
    fillable = missing & (run_len <= max_fill)

    prev_close = out["close"].ffill()
    for col in ["open", "high", "low", "close"]:
        out.loc[fillable, col] = prev_close[fillable]
    out.loc[fillable, "volume"] = 0.0

    out["is_filled"] = fillable
    gap_runs = run_len[missing].groupby(run_id[missing]).first()
    stats = {
        "gaps_found": int(len(gap_runs)),
        "candles_filled": int(fillable.sum()),
        "gaps_left_open": int((gap_runs > max_fill).sum()),
    }
    out = out[~(missing & ~fillable)]
    return out, stats


def flag_outliers(df: pd.DataFrame, window: int = 100, threshold: float = 10.0) -> pd.Series:
    ret = np.log(df["close"]).diff()
    med = ret.rolling(window, min_periods=window // 2).median()
    mad = (ret - med).abs().rolling(window, min_periods=window // 2).median()
    score = (ret - med).abs() / (1.4826 * mad.replace(0, np.nan))
    return (score > threshold).fillna(False)


def clean_candles(df: pd.DataFrame, timeframe: str, max_fill: int = 3) -> tuple[pd.DataFrame, CleaningReport]:
    report = CleaningReport(rows_in=len(df))
    df = df.sort_index()
    df, report.duplicates_removed = remove_duplicates(df)
    df, report.invalid_rows_removed = remove_invalid_ohlc(df)
    df, gap_stats = fill_gaps(df, timeframe, max_fill)
    report.gaps_found = gap_stats["gaps_found"]
    report.candles_filled = gap_stats["candles_filled"]
    report.gaps_left_open = gap_stats["gaps_left_open"]
    df["is_outlier"] = flag_outliers(df) & ~df["is_filled"]
    report.outliers_flagged = int(df["is_outlier"].sum())
    report.rows_out = len(df)
    return df, report
