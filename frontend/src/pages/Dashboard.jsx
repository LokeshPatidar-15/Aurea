import { useState, useEffect } from "react";
import PriceChart from "../components/PriceChart";
import { API_URL } from "../config";

const ASSETS = ["XAUUSD", "BTCUSDT", "EURUSD"];

function formatPrice(symbol, price) {
  const decimals = symbol === "EURUSD" ? 4 : 2;
  return Number(price).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function Dashboard() {
  const [prices, setPrices] = useState({});

  useEffect(() => {
    const fetchOne = async (symbol) => {
      try {
        const response = await fetch(`${API_URL}/prices/${symbol}`);
        const data = await response.json();
        if (!response.ok) {
          return [symbol, { error: data.detail ?? "Request failed" }];
        }
        return [symbol, data];
      } catch (err) {
        return [symbol, { error: "Cannot reach the server" }];
      }
    };

    const fetchAllPrices = async () => {
      const entries = await Promise.all(ASSETS.map(fetchOne));
      setPrices(Object.fromEntries(entries));
    };

    fetchAllPrices();
    const interval = setInterval(fetchAllPrices, 5000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <h1 className="text-2xl font-medium mb-6">Aurea Dashboard</h1>
      <div className="grid grid-cols-3 gap-4 mb-6">
        {ASSETS.map((symbol) => {
          const data = prices[symbol];
          const up = data?.change_percent_24h >= 0;
          return (
            <div key={symbol} className="bg-zinc-900/60 rounded-xl p-4 border border-zinc-800">
              <div className="flex items-baseline justify-between">
                <span className="text-sm text-zinc-400">{symbol}</span>
                {data && !data.error && (
                  <span className={`text-xs font-mono ${up ? "text-emerald-400" : "text-rose-400"}`}>
                    {up ? "+" : ""}{data.change_percent_24h.toFixed(2)}%
                  </span>
                )}
              </div>
              <div className="text-xl font-mono mt-1">
                {data?.error ? (
                  <span className="text-rose-400 text-sm">{data.error}</span>
                ) : (
                  data ? `$${formatPrice(symbol, data.price)}` : "..."
                )}
              </div>
              {data && !data.error && (
                <div className="text-xs text-zinc-500 mt-2">
                  24h {formatPrice(symbol, data.low_24h)} to {formatPrice(symbol, data.high_24h)} · {data.mock ? "mock data" : "live"}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <PriceChart symbol="BTCUSDT" />
        <PriceChart symbol="EURUSD" />
      </div>
    </div>
  );
}

export default Dashboard;
