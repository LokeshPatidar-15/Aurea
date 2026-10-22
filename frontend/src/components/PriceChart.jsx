import { useState, useEffect } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { API_URL } from "../config";

function PriceChart({ symbol }) {
  const [history, setHistory] = useState([]);

  useEffect(() => {
    const fetchPrice = async () => {
      try {
        const response = await fetch(`${API_URL}/price/${symbol}`);
        const data = await response.json();
        if (data.price) {
          const point = { time: new Date().toLocaleTimeString(), price: data.price };
          setHistory((prev) => [...prev, point].slice(-20));
        }
      } catch (err) {
        console.error("Chart fetch error:", err);
      }
    };

    fetchPrice();
    const interval = setInterval(fetchPrice, 5000);
    return () => clearInterval(interval);
  }, [symbol]);

  return (
    <div className="bg-zinc-900/60 rounded-xl border border-zinc-800 p-4">
      <div className="text-sm text-zinc-400 mb-2">{symbol} live price</div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={history}>
          <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#888" }} />
          <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: "#888" }} />
          <Tooltip contentStyle={{ background: "#18181b", border: "1px solid #3f3f46" }} />
          <Line type="monotone" dataKey="price" stroke="#d97706" strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default PriceChart;
