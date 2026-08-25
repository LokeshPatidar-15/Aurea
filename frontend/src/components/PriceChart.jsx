import { useState, useEffect } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

function PriceChart({ symbol }) {
  const [history, setHistory] = useState([]);

  useEffect(() => {
    const fetchPrice = async () => {
      try {
        const response = await fetch(`http://127.0.0.1:8010/price/${symbol}`);
        const data = await response.json();
        if (data.price) {
          const point = {
            time: new Date().toLocaleTimeString(),
            price: data.price,
          };
          setHistory((prev) => {
            const updated = [...prev, point];
            // keep only the last 20 points so the chart doesn't grow forever
            return updated.slice(-20);
          });
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
    <div className="bg-gray-900 rounded-lg border border-gray-800 p-4">
      <div className="text-sm text-gray-400 mb-2">{symbol} — live price</div>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={history}>
          <XAxis dataKey="time" tick={{ fontSize: 10, fill: "#888" }} />
          <YAxis domain={["auto", "auto"]} tick={{ fontSize: 10, fill: "#888" }} />
          <Tooltip contentStyle={{ background: "#1a1a1a", border: "1px solid #333" }} />
          <Line type="monotone" dataKey="price" stroke="#7F77DD" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default PriceChart;
