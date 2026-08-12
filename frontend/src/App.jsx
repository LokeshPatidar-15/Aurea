import PriceCard from "./components/PriceCard";
import "./App.css";

function App() {
  return (
    <div style={{ background: "#0d0d0d", minHeight: "100vh", padding: "24px" }}>
      <h1 style={{ color: "white" }}>Aurea Dashboard</h1>
      <div style={{ display: "flex", gap: "16px" }}>
        <PriceCard symbol="BTCUSDT" />
        <PriceCard symbol="ETHUSDT" />
      </div>
    </div>
  );
}

export default App;
