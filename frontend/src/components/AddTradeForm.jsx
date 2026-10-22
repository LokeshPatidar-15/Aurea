import { useState } from "react";
import { API_URL } from "../config";

const inputClass =
  "bg-zinc-950 border border-zinc-800 rounded-lg px-2.5 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-600";

function formatApiError(data) {
  if (Array.isArray(data?.detail)) {
    return data.detail.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join(", ");
  }
  return data?.detail ?? "Request failed";
}

function AddTradeForm({ onTradeAdded }) {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [entryPrice, setEntryPrice] = useState("");
  const [exitPrice, setExitPrice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [direction, setDirection] = useState("long");
  const [status, setStatus] = useState(null);
  const [isError, setIsError] = useState(false);

  const showStatus = (message, error) => {
    setStatus(message);
    setIsError(error);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    const entry = parseFloat(entryPrice);
    const exit = parseFloat(exitPrice);
    const qty = parseFloat(quantity);

    if (Number.isNaN(entry) || Number.isNaN(exit) || Number.isNaN(qty)) {
      showStatus("Enter valid numbers for price and quantity", true);
      return;
    }
    if (qty <= 0) {
      showStatus("Quantity must be positive", true);
      return;
    }

    try {
      const response = await fetch(`${API_URL}/trades`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          symbol,
          entry_price: entry,
          exit_price: exit,
          quantity: qty,
          direction,
        }),
      });
      const data = await response.json();

      if (!response.ok) {
        showStatus(formatApiError(data), true);
        return;
      }

      showStatus(`Trade added. P&L: ${data.pnl}`, false);
      setEntryPrice("");
      setExitPrice("");
      setQuantity("");
      if (onTradeAdded) onTradeAdded();
    } catch (err) {
      showStatus("Cannot reach the server. Is the backend running?", true);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-wrap items-center gap-2 bg-zinc-900/60 border border-zinc-800 rounded-xl p-4"
    >
      <select value={symbol} onChange={(e) => setSymbol(e.target.value)} className={inputClass}>
        <option value="BTCUSDT">BTCUSDT</option>
        <option value="XAUUSD">XAUUSD</option>
        <option value="EURUSD">EURUSD</option>
      </select>
      <input type="number" step="any" placeholder="Entry price" value={entryPrice} onChange={(e) => setEntryPrice(e.target.value)} required className={inputClass} />
      <input type="number" step="any" placeholder="Exit price" value={exitPrice} onChange={(e) => setExitPrice(e.target.value)} required className={inputClass} />
      <input type="number" step="any" placeholder="Quantity" value={quantity} onChange={(e) => setQuantity(e.target.value)} required className={inputClass} />
      <select value={direction} onChange={(e) => setDirection(e.target.value)} className={inputClass}>
        <option value="long">Long</option>
        <option value="short">Short</option>
      </select>
      <button type="submit" className="bg-amber-700/90 hover:bg-amber-700 text-zinc-950 text-sm font-medium rounded-lg px-4 py-1.5 transition-colors">
        Add trade
      </button>
      {status && (
        <span className={`text-sm ${isError ? "text-rose-400" : "text-emerald-400"}`}>{status}</span>
      )}
    </form>
  );
}

export default AddTradeForm;
