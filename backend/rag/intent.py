import re

SYMBOL_ALIASES = {
    "BTCUSDT": ("btcusdt", "btc", "bitcoin"),
    "XAUUSD": ("xauusd", "xau", "gold"),
    "EURUSD": ("eurusd", "eur", "euro"),
}
ALL_SYMBOLS = tuple(SYMBOL_ALIASES)
WORD = re.compile(r"[a-z0-9&']+")

ACTION_START = re.compile(
    r"^(?:(?:please|pls|just|kindly)\s+)*(?:(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)|go\s+|i\s+want\s+to\s+|i'd\s+like\s+to\s+|i\s+would\s+like\s+to\s+|help\s+me\s+|let's\s+|lets\s+|i\s+wanna\s+)?"
    r"(?:buy(?!\s+signals?\b)|sell(?!\s+signals?\b)|go\s+short|go\s+long|sell\s+short|place|submit|execute|cancel|close|enter|open\s+(?:a|an|the|my))\b"
)
ACTION_ANY = re.compile(
    r"\b(?:place|submit|execute|cancel|create)\s+(?:a\s+|an\s+|the\s+|my\s+|that\s+|this\s+|new\s+)?(?:paper\s+)?(?:order|trade|position)s?\b"
    r"|\b(?:buy|sell)\s+(?:it|this|that|now|for\s+me)\b"
)
QUESTION_LED = re.compile(r"^(?:how|what|where|why|when|which|who|is|are|does|do|did|has|have)\b")
ADVICE = re.compile(
    r"\bshould\s+(?:i|we)\b.{0,30}\b(?:buy|sell|short|long|trade|invest|enter|hold|exit)\b"
    r"|\bwhat\s+should\s+(?:i|we)\s+(?:buy|sell|trade|do)\b"
    r"|\bis\s+it\s+(?:a\s+)?good\s+(?:time\s+)?to\s+(?:buy|sell|trade|enter)\b"
    r"|\bis\s+(?:\w+\s+)?(?:a\s+)?(?:good|bad)\s+(?:buy|sell|investment)\b"
)
FORECAST = re.compile(
    r"\bwill\b.{0,40}\b(?:go\s+up|go\s+down|rise|fall|increase|decrease|drop|pump|dump|crash|moon|hit|reach|break|be\s+higher|be\s+lower)\b"
    r"|\b(?:predict|forecast)\w*\b.{0,30}\b(?:price|tomorrow|next\s+(?:hour|day|week|month)|future)\b"
    r"|\bwhere\s+will\b"
    r"|\bwhat\s+will\b.{0,30}\b(?:price|btc|bitcoin|gold|eur|euro)\b"
    r"|\bgoing\s+to\s+(?:go\s+up|go\s+down|rise|fall|crash|pump|dump)\b"
)
CUE = re.compile(
    r"\b(?:now|current|currently|latest|today|tonight|right\s+now|at\s+the\s+moment|so\s+far|my|our|how\s+many|how\s+much|how's|status|are\s+there|is\s+there|do\s+i\s+have|do\s+we\s+have|am\s+i)\b"
    r"|\bhow\s+(?:is|are|did|has|have)\s+(?:the\s+|my\s+|our\s+)?(?:paper|trading|portfolio|account|strategy|strategies)\b"
)
LIVE_PHRASE = re.compile(r"\bpaper\s+(?:trading\s+)?(?:performance|results|pnl|p&l|account|portfolio)\b|\bopen\s+positions?\b|\bpending\s+orders?\b")
WHY_LIKE = re.compile(r"^(?:why|explain|define|how\s+does|how\s+do|when)\b")
HOW_IS = re.compile(r"\bhow\s+(?:is|are|did|has|have)\s+(?:the\s+|my\s+|our\s+)?(?:paper|trading|portfolio|account)\b")

PRICE_KW = re.compile(r"\bprice\b|\bquote\b|\btrading\s+at\b|\bhow\s+much\s+is\b")
OTHER_CURRENCY = re.compile(r"\b(?:rupees?|inr|gram|grams|yen|jpy|gbp|pounds?|kg|kilos?)\b")
MODEL_KW = re.compile(
    r"\bpredict\w*\b|\bprobabilit\w*\b"
    r"|\b(?:model|xgboost|lstm|logistic|ml)\b.{0,25}\b(?:say|says|saying|signal|signals|output|think|show|shows|view|recommend\w*)\b"
    r"|\b(?:model|xgboost|lstm|logistic|ml)\s+(?:signal|prediction)s?\b"
)
PATTERN_KW = re.compile(r"\b(?:patterns?|candlesticks?|engulfing|pin\s+bar|hammer|shooting\s+star|inside\s+bar)\b")
SIGNAL_KW = re.compile(r"\b(?:signals?|setups?|sweeps?|strategy)\b")
RULE_WORDS = re.compile(r"\b(?:sweeps?|strategy|setups?|rules?|rule-based)\b")
TRADABLE_KW = re.compile(r"\b(?:tradable|tradeable|tradability|worth\s+trading|cost[- ]to[- ]atr)\b|\bcan\s+(?:i|we)\s+trade\b")
SUMMARY_KW = re.compile(
    r"\b(?:equity|balance|unrealized|realized|open\s+positions?|pending\s+orders?|open\s+trades?|drawdown|pnl|p&l|earn\w*)\b"
    r"|\bpaper\s+(?:account|portfolio|positions?|orders?|trading)\b"
)
PERF_KW = re.compile(r"\b(?:performance|win\s+rate|expectancy|profit\s+factor|losing\s+streak|fees)\b")
TRIALS_KW = re.compile(r"\bhow\s+many\s+(?:strategies|strategy|tests|trials)\b|\b(?:strategies|trials)\s+(?:tried|tested|run)\b|\bmultiple[- ]testing\b|\bbonferroni\b")

REFUSALS = {
    "action": (
        "I am read-only. I cannot place, change or cancel paper orders, and I do not tell anyone what to buy or sell. "
        "I can show the current signals, the paper account, performance and tradability, and explain how Aurea works."
    ),
    "forecast": (
        "I do not forecast prices, and no Aurea model has shown an edge after costs. "
        "I can show what the model and the rule strategy say right now: try asking \"what is the signal for BTC now?\"."
    ),
}


def find_symbols(text: str) -> list:
    words = set(WORD.findall(text))
    return [symbol for symbol, aliases in SYMBOL_ALIASES.items() if words & set(aliases)]


def detect(question: str) -> dict:
    q = " ".join((question or "").lower().split())
    symbols = find_symbols(q)
    base = {"kind": "kb", "reason": None, "tools": [], "symbols": symbols}
    led = bool(QUESTION_LED.match(q))
    if ACTION_START.match(q) or (not led and ACTION_ANY.search(q)) or ADVICE.search(q):
        return {**base, "kind": "refuse", "reason": "action"}
    if FORECAST.search(q):
        return {**base, "kind": "refuse", "reason": "forecast"}

    cue = bool(CUE.search(q) or LIVE_PHRASE.search(q))
    why_like = bool(WHY_LIKE.match(q))
    symbolic_gate = (cue or bool(symbols)) and not (why_like and not cue)
    targets = symbols or list(ALL_SYMBOLS)
    tools = []

    if symbolic_gate:
        if PRICE_KW.search(q) and symbols and not OTHER_CURRENCY.search(q):
            tools += [{"tool": "price", "symbol": s} for s in targets]
        if MODEL_KW.search(q):
            tools += [{"tool": "prediction", "symbol": s} for s in targets]
        elif PATTERN_KW.search(q):
            tools += [{"tool": "patterns", "symbol": s} for s in targets]
        elif SIGNAL_KW.search(q):
            tools += [{"tool": "signal", "symbol": s} for s in targets]
            if not RULE_WORDS.search(q):
                tools += [{"tool": "prediction", "symbol": s} for s in targets]
        if TRADABLE_KW.search(q):
            tools.append({"tool": "tradability", "symbol": None})
    if cue:
        wants_summary = bool(SUMMARY_KW.search(q)) or bool(HOW_IS.search(q))
        wants_perf = bool(PERF_KW.search(q)) or bool(HOW_IS.search(q))
        if wants_summary:
            tools.append({"tool": "summary", "symbol": None})
        if wants_perf:
            tools.append({"tool": "performance", "symbol": None})
        if TRIALS_KW.search(q):
            tools.append({"tool": "trials", "symbol": None})
    seen, unique = set(), []
    for t in tools:
        key = (t["tool"], t["symbol"])
        if key not in seen:
            seen.add(key)
            unique.append(t)
    if unique:
        base.update(kind="live", tools=unique)
    return base
