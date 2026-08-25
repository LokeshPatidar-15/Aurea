import { useState, useEffect } from "react";
import PriceChart from "../components/PriceChart";

const ASSETS = ["XAUUSD", "BTCUSDT", "EURUSD"];

function Dashboard() {
  const [prices, setPrices] = useState({});

  useEffect(() => {
    const fetchAllPrices = async () => {
      const results = {};
      for (const symbol of ASSETS) {
        try {
          const response = await fetch(`http://127.0.0.1:8010/price/${symbol}`);
          const data = await response.json();
          results[symbol] = data;
        } catch (err) {
          results[symbol] = { error: err.message };
        }
      }
      setPrices(results);
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
            <div key={symbol} className="bg-gray-900 rounded-lg p-4 border border-gray-800">
              <div className="text-sm text-gray-400">{symbol}</div>
              <div className="text-xl font-medium mt-1">
                {data?.error ? <span className="text-red-400 text-sm">Error</span> : `$${data?.price ?? "..."}`}
              </div>
              <div className="text-xs text-gray-500 mt-2">{data?.mock ? "mock (temp)" : data ? "live" : "-"}</div>
            </div>
          );
        })}
      </div>

      <PriceChart symbol="BTCUSDT" />
    </div>
  );
}

export default Dashboard;
