import numpy as np
import pandas as pd

from analysis.cleaning import clean_candles
from analysis.common import OUTPUT_DIR
from analysis.features import compute_features

SYMBOLS = ["BTCUSDT", "XAUUSD", "EURUSD"]
COLORS = {"BTCUSDT": "#2a78d6", "XAUUSD": "#eb6834", "EURUSD": "#1baf7a"}
SURFACE, TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e3e2de"


def load_all(timeframe: str = "1h", symbols: list[str] = SYMBOLS) -> dict[str, pd.DataFrame]:
    from analysis.db_loader import load_from_db

    out = {}
    for symbol in symbols:
        cleaned, _ = clean_candles(load_from_db(symbol, timeframe), timeframe)
        out[symbol] = cleaned
    return out


def rebased_prices(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    closes = pd.DataFrame({s: d["close"] for s, d in dfs.items()}).dropna()
    return closes / closes.iloc[0] * 100


def levels_vs_returns_corr(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    closes = pd.DataFrame({s: d["close"] for s, d in dfs.items()}).dropna()
    rets = np.log(closes).diff().dropna()
    rows = []
    cols = list(closes.columns)
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            rows.append({"pair": f"{a[:3]}-{b[:3]}", "levels": closes[a].corr(closes[b]), "returns": rets[a].corr(rets[b])})
    return pd.DataFrame(rows).set_index("pair")


def volatility_by_hour(dfs: dict[str, pd.DataFrame]) -> pd.DataFrame:
    out = {}
    for s, d in dfs.items():
        r = np.log(d["close"]).diff().abs().dropna()
        by_hour = r.groupby(r.index.hour).mean()
        out[s] = by_hour / by_hour.mean()
    return pd.DataFrame(out)


def autocorr_table(df: pd.DataFrame, max_lag: int = 48) -> pd.DataFrame:
    r = np.log(df["close"]).diff().dropna()
    lags = range(1, max_lag + 1)
    return pd.DataFrame(
        {"returns": [r.autocorr(lag) for lag in lags], "abs_returns": [r.abs().autocorr(lag) for lag in lags]},
        index=list(lags),
    )


def sweep_forward_returns(df: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
    feats = compute_features(df)
    log_close = np.log(df["close"])
    fwd = (log_close.shift(-horizon) - log_close) * 10_000
    valid = fwd.notna() & feats["dist_poc_atr"].notna()
    groups = {
        "all candles": valid,
        "after bull sweep": valid & feats["sweep_bull"],
        "after bear sweep": valid & feats["sweep_bear"],
    }
    rows = []
    for name, mask in groups.items():
        x = fwd[mask]
        n = len(x)
        eff_n = max(n / horizon, 1)
        t = x.mean() / (x.std(ddof=1) / np.sqrt(eff_n)) if n > 2 and x.std(ddof=1) > 0 else np.nan
        rows.append({"group": name, "n": n, "mean_bps": x.mean(), "hit_rate_up": (x > 0).mean(), "t_adj": t})
    return pd.DataFrame(rows).set_index("group")


def _style(ax, title, xlabel, ylabel):
    import matplotlib.pyplot as plt

    ax.figure.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=12, color=TEXT)
    ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    ax.set_ylabel(ylabel, color=MUTED, fontsize=9)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ["top", "right", "left"]:
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    plt.tight_layout()


def _save(fig, name):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / name
    fig.savefig(path, dpi=140, facecolor=fig.get_facecolor())
    return path


def plot_rebased(dfs):
    import matplotlib.pyplot as plt

    data = rebased_prices(dfs)
    fig, ax = plt.subplots(figsize=(9, 4))
    for s in data.columns:
        ax.plot(data.index, data[s], color=COLORS[s], linewidth=1.3, label=s)
    ax.legend(frameon=False, fontsize=9, labelcolor=MUTED)
    _style(ax, "Price paths rebased to 100", "", "price index")
    return fig


def plot_corr(dfs):
    import matplotlib.pyplot as plt

    table = levels_vs_returns_corr(dfs)
    x = np.arange(len(table))
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(x - 0.18, table["levels"], width=0.34, color="#2a78d6", label="price levels")
    ax.bar(x + 0.18, table["returns"], width=0.34, color="#eb6834", label="returns")
    ax.set_xticks(x, table.index)
    ax.axhline(0, color=GRID, linewidth=0.8)
    ax.legend(frameon=False, fontsize=9, labelcolor=MUTED)
    _style(ax, "Correlation: price levels vs returns", "", "correlation")
    return fig


def plot_hour(dfs):
    import matplotlib.pyplot as plt

    table = volatility_by_hour(dfs)
    fig, ax = plt.subplots(figsize=(9, 4))
    for s in table.columns:
        ax.plot(table.index, table[s], color=COLORS[s], linewidth=1.5, label=s)
    ax.axhline(1, color=GRID, linewidth=0.8)
    ax.set_xticks(range(0, 24, 3))
    ax.legend(frameon=False, fontsize=9, labelcolor=MUTED)
    _style(ax, "Volatility depends on the hour (1.0 = average)", "hour (UTC)", "relative mean |return|")
    return fig


def plot_acf(df, symbol="BTCUSDT"):
    import matplotlib.pyplot as plt

    table = autocorr_table(df)
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(table.index, table["abs_returns"], color="#2a78d6", linewidth=1.5, label="|returns| (size of moves)")
    ax.plot(table.index, table["returns"], color="#eb6834", linewidth=1.5, label="returns (direction)")
    ax.axhline(0, color=GRID, linewidth=0.8)
    ax.legend(frameon=False, fontsize=9, labelcolor=MUTED)
    _style(ax, f"{symbol}: autocorrelation of move size vs direction", "lag (candles)", "autocorrelation")
    return fig


def save_all_charts(dfs):
    paths = [
        _save(plot_rebased(dfs), "eda_1_rebased.png"),
        _save(plot_corr(dfs), "eda_2_corr.png"),
        _save(plot_hour(dfs), "eda_3_hour.png"),
        _save(plot_acf(dfs["BTCUSDT"]), "eda_4_acf.png"),
    ]
    return paths
