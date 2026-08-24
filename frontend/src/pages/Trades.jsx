import { useState, useEffect } from "react";
import AddTradeForm from "../components/AddTradeForm";

function Trades() {
  const [trades, setTrades] = useState([]);

  const fetchTrades = async () => {
    const response = await fetch("http://127.0.0.1:8010/trades");
    const data = await response.json();
    setTrades(data);
  };

  useEffect(() => {
    fetchTrades();
  }, []);

  return (
    <div>
      <h2>Add Trade</h2>
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

export default Trades;
