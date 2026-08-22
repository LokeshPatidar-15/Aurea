import { useState, useEffect } from "react";
import AddTradeForm from "./components/AddTradeForm";
import "./App.css";

const ASSETS = ["XAUUSD", "BTCUSDT", "EURUSD"];

function App() {
  const [prices, setPrices] = useState({});
  const [trades, setTrades] = useState([]);

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

  const fetchTrades = async () => {
    const response = await fetch("http://127.0.0.1:8010/trades");
    const data = await response.json();
    setTrades(data);
  };

  useEffect(() => {
    fetchTrades();
  }, []);

  return (
    <div style={{ background: "#0d0d0d", minHeight: "100vh", padding: "24px", color: "white" }}>
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

      <h2 style={{ marginTop: "32px" }}>Add Trade</h2>
      <AddTradeForm onTradeAdded={fetchTrades} />

      <h2 style={{ marginTop: "32px" }}>Trade Journal</h2>
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: "12px" }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #444", textAlign: "left" }}>
            <th style={{ padding: "8px" }}>Symbol</th>
            <th style={{ padding: "8px" }}>Entry</th>
            <th style={{ padding: "8px" }}>Exit</th>
            <th style={{ padding: "8px" }}>Qty</th>
            <th style={{ padding: "8px" }}>Direction</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr key={i} style={{ borderBottom: "1px solid #222" }}>
              <td style={{ padding: "8px" }}>{t.symbol}</td>
              <td style={{ padding: "8px" }}>{t.entry_price}</td>
              <td style={{ padding: "8px" }}>{t.exit_price}</td>
              <td style={{ padding: "8px" }}>{t.quantity}</td>
              <td style={{ padding: "8px" }}>{t.direction}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
