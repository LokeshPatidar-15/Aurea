import { useState, useEffect } from "react";
import PriceChart from "../components/PriceChart";
import { API_URL } from "../config";

const ASSETS = ["XAUUSD", "BTCUSDT", "EURUSD"];

function Dashboard() {
  const [prices, setPrices] = useState({});

  useEffect(() => {
    const fetchOne = async (symbol) => {
      try {
        const response = await fetch(`${API_URL}/price/${symbol}`);
        return [symbol, await response.json()];
      } catch (err) {
        return [symbol, { error: err.message }];
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
          return (
            <div key={symbol} className="bg-zinc-900/60 rounded-xl p-4 border border-zinc-800">
              <div className="text-sm text-zinc-400">{symbol}</div>
              <div className="text-xl font-mono mt-1">
                {data?.error ? <span className="text-rose-400 text-sm">Unavailable</span> : `$${data?.price ?? "..."}`}
              </div>
              <div className="text-xs text-zinc-500 mt-2">{data?.mock ? "mock data" : data ? "live" : "-"}</div>
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
