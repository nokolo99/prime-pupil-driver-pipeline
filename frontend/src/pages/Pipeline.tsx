import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, daysSince, label, STAGES, timeAgo, type Candidate, type Lookups } from "../api";
import { StatusPill } from "../components";

export default function Pipeline() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  const [stage, setStage] = useState<string | null>(null);
  const [depot, setDepot] = useState<string>("");
  const [sla, setSla] = useState<Record<string, number>>({});

  useEffect(() => {
    api<Candidate[]>("/candidates").then(setCandidates);
    api<Lookups>("/lookups").then(setLk);
    api<{ stage_sla_days: Record<string, number> }>("/config").then((c) => setSla(c.stage_sla_days));
  }, []);

  const stuck = (c: Candidate) => !["dropped", "rejected", "hired"].includes(c.status) && sla[c.stage] !== undefined && daysSince(c.stage_entered_at) > sla[c.stage];
  const depotName = (id: number | null) => lk.depots.find((d) => d.id === id)?.name ?? "—";
  const inDepot = candidates.filter((c) => !depot || String(c.depot_id) === depot);
  const shown = inDepot.filter((c) => !stage || c.stage === stage);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Pipeline</h2>
        <select className="rounded border bg-white px-2 py-1 text-sm" value={depot} onChange={(e) => setDepot(e.target.value)}>
          <option value="">All depots</option>
          {lk.depots.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </div>

      <div className="grid grid-cols-3 gap-2 sm:grid-cols-5 lg:grid-cols-9">
        {STAGES.map((s) => {
          const n = inDepot.filter((c) => c.stage === s).length;
          return (
            <button key={s} onClick={() => setStage(stage === s ? null : s)}
              className={`rounded-lg border p-2 text-left ${stage === s ? "border-emerald-700 bg-emerald-50" : "bg-white"}`}>
              <div className="text-xl font-semibold">{n}</div>
              <div className="text-xs text-stone-500">{label(s)}</div>
            </button>
          );
        })}
      </div>

      <div className="overflow-x-auto rounded-lg border bg-white">
        <table className="w-full text-sm">
          <thead className="text-left text-stone-500">
            <tr><th className="p-3">Name</th><th>Depot</th><th>Stage</th><th>Status</th><th>Days in stage</th><th>Last contact</th><th>Lang</th></tr>
          </thead>
          <tbody className="divide-y">
            {shown.length === 0 && <tr><td colSpan={7} className="p-4 text-stone-500">No candidates.</td></tr>}
            {shown.map((c) => (
              <tr key={c.id} className={stuck(c) ? "bg-rose-50" : "hover:bg-stone-50"}>
                <td className="p-3"><Link className="font-medium text-emerald-800 hover:underline" to={`/candidates/${c.id}`}>{c.first_name} {c.last_name}</Link></td>
                <td>{depotName(c.depot_id)}</td>
                <td>{label(c.stage)}</td>
                <td><StatusPill status={c.status} /></td>
                <td className={stuck(c) ? "font-semibold text-rose-700" : ""}>{daysSince(c.stage_entered_at)}{stuck(c) ? " ⚠" : ""}</td>
                <td className="text-stone-500">{c.last_contacted_at ? timeAgo(c.last_contacted_at) : "—"}</td>
                <td className="uppercase text-stone-500">{c.preferred_language}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
