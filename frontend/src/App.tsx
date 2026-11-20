import { NavLink, Route, Routes } from "react-router-dom";
import Today from "./pages/Today";
import Pipeline from "./pages/Pipeline";
import CandidateDetail from "./pages/CandidateDetail";
import Demo from "./pages/Demo";
import Insights from "./pages/Insights";
import TrainingSheet from "./pages/TrainingSheet";
import Settings from "./pages/Settings";
import Apply from "./pages/Apply";
import Workday from "./pages/Workday";
import { ClockBanner } from "./components";

const link = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-1.5 rounded-md text-sm ${isActive ? "bg-emerald-800 text-white" : "text-stone-700 hover:bg-stone-200"}`;

export default function App() {
  return (
    <div className="min-h-screen">
      <ClockBanner />
      <header className="border-b bg-white">
        <div className="mx-auto max-w-6xl px-4 py-3 flex items-center gap-4">
          <NavLink to="/" className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-800 text-sm text-white">PP</span>
            <span className="leading-tight"><span className="block text-sm font-semibold">Prime Pupil</span><span className="block text-[11px] text-stone-500">Driver hiring</span></span>
          </NavLink>
          <nav className="flex gap-1">
            <NavLink to="/" end className={link}>Today</NavLink>
            <NavLink to="/pipeline" className={link}>Pipeline</NavLink>
            <NavLink to="/insights" className={link}>Insights</NavLink>
            <NavLink to="/settings" className={link}>Settings</NavLink>
          </nav>
          <nav className="ml-auto flex items-center gap-1 rounded-lg border border-dashed border-amber-300 bg-amber-50 px-1.5 py-1 text-xs">
            <span className="px-1 font-semibold uppercase tracking-wide text-amber-800">Demo</span>
            <NavLink to="/apply" className={({ isActive }) => `rounded px-2 py-0.5 ${isActive ? "bg-amber-200 text-amber-950" : "text-amber-900 hover:bg-amber-100"}`}>New applicant</NavLink>
            <NavLink to="/demo" className={({ isActive }) => `rounded px-2 py-0.5 ${isActive ? "bg-amber-200 text-amber-950" : "text-amber-900 hover:bg-amber-100"}`}>Console</NavLink>
            <NavLink to="/workday" className={({ isActive }) => `rounded px-2 py-0.5 ${isActive ? "bg-amber-200 text-amber-950" : "text-amber-900 hover:bg-amber-100"}`}>Workday</NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/pipeline" element={<Pipeline />} />
          <Route path="/candidates/:id" element={<CandidateDetail />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/insights" element={<Insights />} />
          <Route path="/training-roster" element={<TrainingSheet />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/apply" element={<Apply />} />
          <Route path="/workday" element={<Workday />} />
        </Routes>
      </main>
    </div>
  );
}
