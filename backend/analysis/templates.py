import copy

TEMPLATES = {
    "sweep_reversal": {
        "title": "Liquidity sweep reversal (Day 54 rules)",
        "idea": "Price wicks beyond the last swing low or high and closes back inside, in the direction of the EMA50/EMA200 trend, on normal volume.",
        "evidence": "Backtested on Day 54: no net edge after 20 bps cost on BTCUSDT, XAUUSD or EURUSD.",
        "strategy": {
            "name": "sweep_reversal",
            "long": {"all": ["sweep_bull", "volume_ok", "trend_up", "clean_bar"]},
            "short": {"all": ["sweep_bear", "volume_ok", "trend_down", "clean_bar"]},
            "stop_mode": "candle", "stop_buffer_atr": 0.25,
        },
    },
    "engulfing_with_trend": {
        "title": "Engulfing candle with the trend",
        "idea": "A bullish engulfing candle in an uptrend, or a bearish one in a downtrend, with at least average volume.",
        "evidence": "Single engulfing patterns showed no tradable edge in the Day 60 report. Not yet backtested as a full strategy.",
        "strategy": {
            "name": "engulfing_with_trend",
            "long": {"all": ["bullish_engulfing", "trend_up", "volume_ok", "clean_bar"]},
            "short": {"all": ["bearish_engulfing", "trend_down", "volume_ok", "clean_bar"]},
            "stop_mode": "two_candle", "stop_buffer_atr": 0.25,
        },
    },
    "pin_bar_with_trend": {
        "title": "Pin bar with the trend",
        "idea": "A hammer in an uptrend or a shooting star in a downtrend: the market rejected a price level and the trend agrees.",
        "evidence": "Single pin bars showed no tradable edge in the Day 60 report. Not yet backtested as a full strategy.",
        "strategy": {
            "name": "pin_bar_with_trend",
            "long": {"all": ["bullish_pin", "trend_up", "clean_bar"]},
            "short": {"all": ["bearish_pin", "trend_down", "clean_bar"]},
            "stop_mode": "candle", "stop_buffer_atr": 0.25,
        },
    },
    "sweep_then_engulfing": {
        "title": "Sweep confirmed by an engulfing candle",
        "idea": "The liquidity sweep and the engulfing candle happen on the same candle: a stricter, rarer version of the sweep reversal.",
        "evidence": "Looked at in the Day 60 report as a combination; no combination passed the multiple-testing threshold.",
        "strategy": {
            "name": "sweep_then_engulfing",
            "long": {"all": ["sweep_bull", "bullish_engulfing", "clean_bar"]},
            "short": {"all": ["sweep_bear", "bearish_engulfing", "clean_bar"]},
            "stop_mode": "candle", "stop_buffer_atr": 0.25,
        },
    },
    "rsi_extreme_rejection": {
        "title": "RSI extreme with a rejection candle",
        "idea": "RSI is oversold and the candle shows rejection (engulfing or pin), or the mirror at overbought. Shows how OR works.",
        "evidence": "Not tested yet. Day 62 will backtest it with a random-entry comparison.",
        "strategy": {
            "name": "rsi_extreme_rejection",
            "long": {"all": ["rsi_oversold", {"any": ["bullish_engulfing", "bullish_pin"]}, "clean_bar"]},
            "short": {"all": ["rsi_overbought", {"any": ["bearish_engulfing", "bearish_pin"]}, "clean_bar"]},
            "stop_mode": "two_candle", "stop_buffer_atr": 0.25,
        },
    },
}


def template_ids() -> list:
    return list(TEMPLATES)


def get_template(template_id: str) -> dict:
    if template_id not in TEMPLATES:
        raise KeyError(f"unknown template {template_id!r}. Valid: {', '.join(TEMPLATES)}")
    return copy.deepcopy(TEMPLATES[template_id])
