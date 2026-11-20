import { NavLink, Route, Routes } from "react-router-dom";
import Today from "./pages/Today";
import Pipeline from "./pages/Pipeline";
import CandidateDetail from "./pages/CandidateDetail";
import Demo from "./pages/Demo";
import Insights from "./pages/Insights";
import { ClockBanner } from "./components";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded-md text-sm ${isActive ? "bg-emerald-800 text-white" : "text-stone-700 hover:bg-stone-200"}`;

export default function App() {
  return (
    <div className="min-h-screen">
      <ClockBanner />
      <header className="border-b bg-white">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center gap-4">
          <span className="font-semibold">Prime Pupil · Driver Pipeline</span>
          <nav className="flex gap-1">
            <NavLink to="/" end className={link}>Today</NavLink>
            <NavLink to="/pipeline" className={link}>Pipeline</NavLink>
            <NavLink to="/insights" className={link}>Insights</NavLink>
          </nav>
          <NavLink to="/demo" className="ml-auto text-xs text-stone-500 hover:underline">Demo controls</NavLink>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/candidates/:id" element={<CandidateDetail />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/insights" element={<Insights />} />
        </Routes>
      </main>
    </div>
  );
}
