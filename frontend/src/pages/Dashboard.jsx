import { useState, useEffect } from "react";
import AddTradeForm from "../components/AddTradeForm";

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
      <h1>Aurea Dashboard</h1>
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "20px" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #444", textAlign: "left" }}>
            <th style={{ padding: "8px" }}>Symbol</th>
            <th style={{ padding: "8px" }}>Price</th>
            <th style={{ padding: "8px" }}>Source</th>
          </tr>
        </thead>
        <tbody>
          {ASSETS.map((symbol) => {
            const data = prices[symbol];
            return (
              <tr key={symbol} style={{ borderBottom: "1px solid #222" }}>
                <td style={{ padding: "8px" }}>{symbol}</td>
                <td style={{ padding: "8px" }}>
                  {data?.error ? <span style={{ color: "red" }}>Error</span> : `$${data?.price ?? "Loading..."}`}
                </td>
                <td style={{ padding: "8px", color: "#888" }}>{data?.mock ? "mock (temp)" : data ? "live" : "-"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default Dashboard;
