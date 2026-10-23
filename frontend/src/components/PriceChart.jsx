import { useState, useEffect } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { API_URL } from "../config";

function PriceChart({ symbol }) {
  const [history, setHistory] = useState([]);

  useEffect(() => {
    let cancelled = false;

    const loadHistory = async () => {
      try {
        const response = await fetch(`${API_URL}/prices/${symbol}/history?interval=1m&limit=30`);
        if (!response.ok) return;
        const candles = await response.json();
        if (cancelled) return;
        setHistory(
          candles.map((c) => ({
            time: new Date(c.time).toLocaleTimeString(),
            price: c.close,
          }))
        );
      } catch (err) {
        console.error("History fetch error:", err);
      }
    };

    const fetchPrice = async () => {
      try {
        const response = await fetch(`${API_URL}/prices/${symbol}`);
        if (!response.ok) return;
        const data = await response.json();
        if (cancelled) return;
        const point = { time: new Date(data.timestamp).toLocaleTimeString(), price: data.price };
        setHistory((prev) => [...prev, point].slice(-60));
      } catch (err) {
        console.error("Chart fetch error:", err);
      }
    };

    loadHistory().then(fetchPrice);
    const interval = setInterval(fetchPrice, 5000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [symbol]);

  return (
    <div className="bg-zinc-900/60 rounded-xl border border-zinc-800 p-4">
      <div className="text-sm text-zinc-400 mb-2">{symbol} price</div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={history}>
          <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#888" }} minTickGap={30} />
          <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: "#888" }} />
          <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }} />
          <Line type="monotone" dataKey="price" stroke="#d97706" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default PriceChart;
