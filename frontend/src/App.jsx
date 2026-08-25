import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Trades from "./pages/Trades";
import Copilot from "./pages/Copilot";

function App() {
  return (
    <BrowserRouter>
      <div className="bg-black min-h-screen text-gray-100">
        <nav className="flex gap-6 px-6 py-4 border-b border-gray-800">
          <Link to="/" className="text-sm font-medium hover:text-white text-gray-300">Dashboard</Link>
          <Link to="/trades" className="text-sm font-medium hover:text-white text-gray-300">Trades</Link>
          <Link to="/copilot" className="text-sm font-medium hover:text-white text-gray-300">Copilot</Link>
        </nav>

        <div className="p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/trades" element={<Trades />} />
            <Route path="/copilot" element={<Copilot />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
