import { useState, useEffect } from "react";

function PriceCard({ symbol }) {
  const [price, setPrice] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchPrice = async () => {
      try {
        const response = await fetch(`http://127.0.0.1:8010/price/${symbol}`);
        const data = await response.json();
        if (data.error) {
          setError(data.error);
        } else {
          setPrice(data.price);
          setError(null);
        }
      } catch (err) {
        setError(err.message);
      }
    };

    fetchPrice();
    const interval = setInterval(fetchPrice, 5000);

    return () => clearInterval(interval);
  }, [symbol]);

  return (
    <div style={{ border: "1px solid #444", padding: "16px", borderRadius: "8px", color: "white", background: "#1a1a1a" }}>
      <h3>{symbol}</h3>
      {error ? <p style={{ color: "red" }}>Error: {error}</p> : <p>${price ?? "Loading..."}</p>}
    </div>
  );
}

export default PriceCard;
