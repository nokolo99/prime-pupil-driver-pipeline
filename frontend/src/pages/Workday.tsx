import { useEffect, useState } from "react";
import { api, demoHeaders } from "../api";

type App = { id: number; job_application_id: string; candidate_id: string; first_name: string; last_name: string; job_requisition_id: string; current_step: string; disposition: string | null };
type Out = { id: number; workday_id: string | null; action: string; payload: Record<string, unknown>; status: string; created_at: string };

// What Prime Pupil's IT team would care about: what's in Workday, and exactly what our connector sent.
export default function Workday() {
  const [apps, setApps] = useState<App[]>([]);
  const [out, setOut] = useState<Out[]>([]);
  const [mode, setMode] = useState("");
  useEffect(() => {
    const load = () => {
      fetch("/mock-workday/applications", { headers: demoHeaders() }).then((r) => r.json()).then(setApps).catch(() => {});
      api<Out[]>("/demo/workday-outbox").then(setOut);
    };
    load(); api<{ workday_intake?: string }>("/demo/voice-status").then((v) => setMode(v.workday_intake ?? ""));
    const t = setInterval(load, 3000); return () => clearInterval(t);
  }, []);
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold">Workday integration</h2>
        <p className="text-xs text-stone-500">Intake: <b>{mode === "poll" ? "polling Get_Candidates every few seconds" : "direct (shortcut)"}</b>. Writes go through an outbox: recorded with each change, delivered right after, retried if Workday is down. This page shows a fake Workday tenant.</p>
      </div>
      <section className="overflow-x-auto rounded-lg border bg-white">
        <h3 className="p-4 pb-2 font-semibold">Job applications in Workday</h3>
        <table className="w-full text-sm"><thead className="text-left text-stone-500"><tr><th className="px-4 py-2">Application</th><th>Candidate</th><th>Requisition</th><th>Workday step</th><th>Disposition</th></tr></thead>
          <tbody className="divide-y">
            {apps.length === 0 && <tr><td colSpan={5} className="px-4 py-3 text-stone-500">No applications yet. Submit one on the New applicant page.</td></tr>}
            {apps.map((a) => <tr key={a.id}><td className="px-4 py-2 font-mono text-xs">{a.job_application_id}</td><td>{a.first_name} {a.last_name} <span className="font-mono text-xs text-stone-400">{a.candidate_id}</span></td>
              <td className="font-mono text-xs">{a.job_requisition_id}</td><td className="font-medium">{a.current_step}</td><td className="text-rose-700">{a.disposition ?? ""}</td></tr>)}
          </tbody></table>
      </section>
      <section className="overflow-x-auto rounded-lg border bg-white">
        <h3 className="p-4 pb-2 font-semibold">What we sent to Workday</h3>
        <table className="w-full text-sm"><thead className="text-left text-stone-500"><tr><th className="px-4 py-2">Status</th><th>Application</th><th>Operation</th><th>Detail</th></tr></thead>
          <tbody className="divide-y">
            {out.length === 0 && <tr><td colSpan={4} className="px-4 py-3 text-stone-500">Nothing sent yet.</td></tr>}
            {out.map((o) => <tr key={o.id}>
              <td className={`px-4 py-2 text-xs font-medium ${o.status === "sent" ? "text-emerald-700" : o.status === "failed" ? "text-rose-700" : "text-stone-400"}`}>{o.status}</td>
              <td className="font-mono text-xs">{o.workday_id ?? "—"}</td><td className="font-mono text-xs font-semibold">{o.action}</td>
              <td className="text-stone-600">{String(o.payload.next_step ?? o.payload.disposition ?? (o.action === "Offer" ? "Start offer" : ""))}</td></tr>)}
          </tbody></table>
      </section>
    </div>
  );
}
