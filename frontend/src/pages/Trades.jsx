import { useState, useEffect } from "react";
import AddTradeForm from "../components/AddTradeForm";
import { API_URL } from "../config";

function Trades() {
  const [trades, setTrades] = useState([]);
  const [error, setError] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [draft, setDraft] = useState("");

  const fetchTrades = async () => {
    try {
      const response = await fetch(`${API_URL}/trades?limit=200`);
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      const data = await response.json();
      setTrades(Array.isArray(data) ? [...data].reverse() : []);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    fetchTrades();
  }, []);

  const deleteTrade = async (id) => {
    if (!window.confirm("Delete this trade permanently?")) return;
    try {
      const response = await fetch(`${API_URL}/trades/${id}`, { method: "DELETE" });
      if (!response.ok && response.status !== 404) throw new Error(`Server returned ${response.status}`);
      await fetchTrades();
    } catch (err) {
      setError(err.message);
    }
  };

  const startEditing = (trade) => {
    setEditingId(trade.id);
    setDraft(trade.notes);
  };

  const saveNotes = async (id) => {
    try {
      const response = await fetch(`${API_URL}/trades/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: draft }),
      });
      if (!response.ok) throw new Error(`Server returned ${response.status}`);
      setEditingId(null);
      await fetchTrades();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div>
      <h2 className="text-xl font-medium mb-4">Add Trade</h2>
      <AddTradeForm onTradeAdded={fetchTrades} />

      <h2 className="text-xl font-medium mt-8 mb-4">Trade Journal</h2>
      {error && <p className="text-rose-400 text-sm mb-3">Something went wrong: {error}</p>}
      <div className="bg-zinc-900/60 rounded-xl border border-zinc-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800 text-left text-zinc-400">
              <th className="p-3 font-medium">Symbol</th>
              <th className="p-3 font-medium">Entry</th>
              <th className="p-3 font-medium">Exit</th>
              <th className="p-3 font-medium">Qty</th>
              <th className="p-3 font-medium">Side</th>
              <th className="p-3 font-medium">P&L</th>
              <th className="p-3 font-medium">Notes</th>
              <th className="p-3 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id} className="border-b border-zinc-800 last:border-0 align-top">
                <td className="p-3">{t.symbol}</td>
                <td className="p-3">{t.entry_price}</td>
                <td className="p-3">{t.exit_price}</td>
                <td className="p-3">{t.quantity}</td>
                <td className="p-3 capitalize">{t.direction}</td>
                <td className={`p-3 font-mono ${t.pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>{t.pnl}</td>
                <td className="p-3 w-64">
                  {editingId === t.id ? (
                    <div className="flex gap-2">
                      <textarea
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        maxLength={500}
                        rows={2}
                        className="flex-1 bg-zinc-950 border border-zinc-800 rounded-lg px-2 py-1 text-xs text-zinc-200"
                      />
                      <div className="flex flex-col gap-1">
                        <button onClick={() => saveNotes(t.id)} className="text-xs text-emerald-400 hover:text-emerald-300">Save</button>
                        <button onClick={() => setEditingId(null)} className="text-xs text-zinc-500 hover:text-zinc-300">Cancel</button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => startEditing(t)} className="text-left text-xs text-zinc-400 hover:text-zinc-200">
                      {t.notes || "Add note..."}
                    </button>
                  )}
                </td>
                <td className="p-3">
                  <button onClick={() => deleteTrade(t.id)} className="text-xs text-rose-400 hover:text-rose-300">Delete</button>
                </td>
              </tr>
            ))}
            {trades.length === 0 && (
              <tr>
                <td colSpan="8" className="p-6 text-center text-zinc-600">No trades yet. Add one above.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Trades;
