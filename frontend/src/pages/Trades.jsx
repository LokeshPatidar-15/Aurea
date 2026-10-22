import { useState, useEffect } from "react";
import AddTradeForm from "../components/AddTradeForm";
import { API_URL } from "../config";

function Trades() {
  const [trades, setTrades] = useState([]);
  const [error, setError] = useState(null);

  const fetchTrades = async () => {
    try {
      const response = await fetch(`${API_URL}/trades`);
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      const data = await response.json();
      setTrades(Array.isArray(data) ? data : []);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    fetchTrades();
  }, []);

  return (
    <div>
      <h2 className="text-xl font-medium mb-4">Add Trade</h2>
      <AddTradeForm onTradeAdded={fetchTrades} />

      <h2 className="text-xl font-medium mt-8 mb-4">Trade Journal</h2>
      {error && <p className="text-rose-400 text-sm mb-3">Could not load trades: {error}</p>}
      <div className="bg-zinc-900/60 rounded-xl border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-zinc-400">
              <th className="p-3 font-medium">Symbol</th>
              <th className="p-3 font-medium">Entry</th>
              <th className="p-3 font-medium">Exit</th>
              <th className="p-3 font-medium">Qty</th>
              <th className="p-3 font-medium">Direction</th>
              <th className="p-3 font-medium">P&L</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id} className="border-b border-zinc-800 last:border-0">
                <td className="p-3">{t.symbol}</td>
                <td className="p-3">{t.entry_price}</td>
                <td className="p-3">{t.exit_price}</td>
                <td className="p-3">{t.quantity}</td>
                <td className="p-3 capitalize">{t.direction}</td>
                <td className={`p-3 font-mono ${t.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{t.pnl}</td>
              </tr>
            ))}
            {trades.length === 0 && (
              <tr>
                <td colSpan="6" className="p-6 text-center text-zinc-600">No trades yet. Add one above.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Trades;
