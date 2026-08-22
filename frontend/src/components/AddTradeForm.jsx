import { useState } from "react";

function AddTradeForm({ onTradeAdded }) {
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [entryPrice, setEntryPrice] = useState("");
  const [exitPrice, setExitPrice] = useState("");
  const [quantity, setQuantity] = useState("");
  const [direction, setDirection] = useState("long");
  const [status, setStatus] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault(); // stops the browser's default full-page reload on form submit

    const newTrade = {
      symbol,
      entry_price: parseFloat(entryPrice),
      exit_price: parseFloat(exitPrice),
      quantity: parseFloat(quantity),
      direction,
    };

    try {
      const response = await fetch("http://127.0.0.1:8010/trades", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newTrade),
      });

      if (!response.ok) throw new Error("Failed to add trade");

      setStatus("Trade added!");
      setEntryPrice("");
      setExitPrice("");
      setQuantity("");

      if (onTradeAdded) onTradeAdded();
    } catch (err) {
      setStatus(`Error: ${err.message}`);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ color: "white", display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center", marginTop: "16px" }}>
      <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
        <option value="BTCUSDT">BTCUSDT</option>
        <option value="XAUUSD">XAUUSD</option>
        <option value="EURUSD">EURUSD</option>
      </select>

      <input
        type="number"
        placeholder="Entry Price"
        value={entryPrice}
        onChange={(e) => setEntryPrice(e.target.value)}
        required
      />

      <input
        type="number"
        placeholder="Exit Price"
        value={exitPrice}
        onChange={(e) => setExitPrice(e.target.value)}
        required
      />

      <input
        type="number"
        placeholder="Quantity"
        value={quantity}
        onChange={(e) => setQuantity(e.target.value)}
        required
      />

      <select value={direction} onChange={(e) => setDirection(e.target.value)}>
        <option value="long">Long</option>
        <option value="short">Short</option>
      </select>

      <button type="submit">Add Trade</button>

      {status && <span style={{ marginLeft: "8px" }}>{status}</span>}
    </form>
  );
}

export default AddTradeForm;
