import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Trades from "./pages/Trades";
import Strategy from "./pages/Strategy";
import Copilot from "./pages/Copilot";

const linkClass = ({ isActive }) =>
  `text-sm font-medium ${isActive ? "text-amber-500" : "text-zinc-400 hover:text-zinc-100"}`;

function App() {
  return (
    <BrowserRouter>
      <div className="bg-zinc-950 min-h-screen text-zinc-100">
        <nav className="flex gap-6 px-6 py-4 border-b border-zinc-900">
          <NavLink to="/" end className={linkClass}>Dashboard</NavLink>
          <NavLink to="/trades" className={linkClass}>Trades</NavLink>
          <NavLink to="/strategy" className={linkClass}>Strategy</NavLink>
          <NavLink to="/copilot" className={linkClass}>Copilot</NavLink>
        </nav>
        <div className="p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/trades" element={<Trades />} />
            <Route path="/strategy" element={<Strategy />} />
            <Route path="/copilot" element={<Copilot />} />
            <Route path="*" element={<p className="text-zinc-500">Page not found.</p>} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
