import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Trades from "./pages/Trades";
import Copilot from "./pages/Copilot";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <div style={{ background: "#0d0d0d", minHeight: "100vh", padding: "24px", color: "white" }}>
        <nav style={{ display: "flex", gap: "16px", marginBottom: "24px", borderBottom: "1px solid #333", paddingBottom: "12px" }}>
          <Link to="/" style={{ color: "white" }}>Dashboard</Link>
          <Link to="/trades" style={{ color: "white" }}>Trades</Link>
          <Link to="/copilot" style={{ color: "white" }}>Copilot</Link>
        </nav>

        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/copilot" element={<Copilot />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
