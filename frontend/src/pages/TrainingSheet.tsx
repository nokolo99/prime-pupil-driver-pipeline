import { useEffect, useState } from "react";
import { api, asDate } from "../api";

type Row = { id: number; candidate_id: number; trainee: string; cohort: string; completed: boolean; marked_at: string | null; processed: boolean };

// Stand-in for the trainer's shared spreadsheet. The trainer works exactly as today (tick Completed);
// the system watches the sheet and moves the candidate on. Prod: their Google Sheet / Excel via API.
export default function TrainingSheet() {
  const [rows, setRows] = useState<Row[]>([]);
  const load = () => { api<Row[]>("/demo/training-sheet").then(setRows); };
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, []);
  async function toggle(r: Row) {
    await api(`/demo/training-sheet/${r.id}`, { method: "POST", body: JSON.stringify({ completed: !r.completed }) });
    load();
  }
  const open = rows.filter((r) => !r.completed);
  return (
    <div className="mx-auto max-w-3xl">
      <div className="mb-3 flex items-center gap-2"><span className="rounded bg-green-700 px-1.5 py-0.5 text-xs font-bold text-white">XLS</span>
        <h2 className="text-lg font-semibold">CDL Training Roster (shared)</h2></div>
      <p className="mb-3 text-xs text-stone-500">Stand-in for the trainer's shared spreadsheet. The trainer checks Zoom attendance and ticks "Completed" as they do today; Prime Pupil's system watches this sheet and moves the candidate to the skills test automatically.</p>
      <table className="w-full border-collapse border border-stone-300 bg-white text-sm">
        <thead className="bg-stone-100 text-left"><tr>
          <th className="w-10 border border-stone-300 px-2 py-1 text-center text-stone-400">#</th>
          <th className="border border-stone-300 px-2 py-1">Trainee</th><th className="border border-stone-300 px-2 py-1">Cohort</th>
          <th className="border border-stone-300 px-2 py-1 text-center">Completed</th><th className="border border-stone-300 px-2 py-1">System</th>
        </tr></thead>
        <tbody>
          {[...open, ...rows.filter((r) => r.completed)].map((r, i) => (
            <tr key={r.id}>
              <td className="border border-stone-300 px-2 py-1 text-center text-stone-400">{i + 1}</td>
              <td className="border border-stone-300 px-2 py-1">{r.trainee}</td>
              <td className="border border-stone-300 px-2 py-1">{r.cohort}</td>
              <td className="border border-stone-300 px-2 py-1 text-center"><input type="checkbox" checked={r.completed} onChange={() => toggle(r)} /></td>
              <td className="border border-stone-300 px-2 py-1 text-xs text-stone-500">{r.processed ? `✓ Picked up${r.marked_at ? ` ${asDate(r.marked_at).toLocaleTimeString()}` : ""}` : r.completed ? "Waiting for next check…" : ""}</td>
            </tr>
          ))}
          {rows.length === 0 && <tr><td colSpan={5} className="p-3 text-stone-500">No trainees yet.</td></tr>}
        </tbody>
      </table>
    </div>
  );
}
