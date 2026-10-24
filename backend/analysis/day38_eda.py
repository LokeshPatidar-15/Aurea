import pandas as pd

from analysis import eda

pd.set_option("display.width", 120)

dfs = eda.load_all("1h")
for symbol, df in dfs.items():
    print(f"{symbol}: {len(df)} cleaned candles, {df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d}")

print("\n=== 1. Correlation: price levels vs returns ===")
print(eda.levels_vs_returns_corr(dfs).round(3).to_string())

print("\n=== 2. Busiest and quietest UTC hours (1.0 = average volatility) ===")
by_hour = eda.volatility_by_hour(dfs)
for symbol in by_hour.columns:
    s = by_hour[symbol].sort_values()
    print(f"{symbol}: quietest {s.index[0]:02d}:00 ({s.iloc[0]:.2f}) | busiest {s.index[-1]:02d}:00 ({s.iloc[-1]:.2f})")

print("\n=== 3. Autocorrelation at lag 1 (BTCUSDT) ===")
acf = eda.autocorr_table(dfs["BTCUSDT"])
print(f"returns lag-1: {acf.loc[1, 'returns']:+.3f} | |returns| lag-1: {acf.loc[1, 'abs_returns']:+.3f}")

print("\n=== 4. Forward 4-candle return after liquidity sweeps (basis points) ===")
for symbol, df in dfs.items():
    print(f"\n{symbol}")
    print(eda.sweep_forward_returns(df, horizon=4).round(2).to_string())

print("\nCharts saved:")
for path in eda.save_all_charts(dfs):
    print(" ", path)
