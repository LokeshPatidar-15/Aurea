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
      <h2 className="text-xl font-medium mb-4">Add Trade</h2>
      <AddTradeForm onTradeAdded={fetchTrades} />

      <h2 className="text-xl font-medium mt-8 mb-4">Trade Journal</h2>
      <div className="bg-gray-900 rounded-lg border border-gray-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800 text-left text-gray-400">
              <th className="p-3 font-medium">Symbol</th>
              <th className="p-3 font-medium">Entry</th>
              <th className="p-3 font-medium">Exit</th>
              <th className="p-3 font-medium">Qty</th>
              <th className="p-3 font-medium">Direction</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t, i) => (
              <tr key={i} className="border-b border-gray-800 last:border-0">
                <td className="p-3">{t.symbol}</td>
                <td className="p-3">{t.entry_price}</td>
                <td className="p-3">{t.exit_price}</td>
                <td className="p-3">{t.quantity}</td>
                <td className="p-3 capitalize">{t.direction}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Trades;
