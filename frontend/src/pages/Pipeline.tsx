import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, daysSince, label, STAGES, timeAgo, type Candidate, type Lookups } from "../api";
import { StatusPill } from "../components";

export default function Pipeline() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  const [params, setParams] = useSearchParams();
  const stage = params.get("stage");
  const depot = params.get("depot_id") ?? "";
  const setStage = (v: string | null) => { const p = new URLSearchParams(params); if (v) p.set("stage", v); else p.delete("stage"); setParams(p); };
  const setDepot = (v: string) => { const p = new URLSearchParams(params); if (v) p.set("depot_id", v); else p.delete("depot_id"); setParams(p); };
  const extra = new URLSearchParams(params); extra.delete("stage"); extra.delete("depot_id");
  const extraQs = extra.toString();
  const [sla, setSla] = useState<Record<string, number>>({});
  const [flags, setFlags] = useState<{ candidate_id: number; note: string }[]>([]);

  useEffect(() => {
    api<Candidate[]>(`/candidates${extraQs ? `?${extraQs}` : ""}`).then(setCandidates);
  }, [extraQs]);
  useEffect(() => {
    api<Lookups>("/lookups").then(setLk);
    api<typeof flags>("/flags").then(setFlags);
    api<{ stage_sla_days: Record<string, number> }>("/config").then((c) => setSla(c.stage_sla_days));
  }, []);

  const stuck = (c: Candidate) => !["dropped", "rejected", "hired"].includes(c.status) && sla[c.stage] !== undefined && daysSince(c.stage_entered_at) > sla[c.stage];
  const depotName = (id: number | null) => lk.depots.find((d) => d.id === id)?.name ?? "—";
  const inDepot = candidates.filter((c) => !depot || String(c.depot_id) === depot);
  const shown = inDepot.filter((c) => !stage || c.stage === stage);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Pipeline</h2>
          {extraQs && <p className="text-xs text-stone-500">Filtered from Insights: {[...extra.entries()].map(([k, v]) => `${label(k)} = ${label(v)}`).join(" · ")} · <button className="underline" onClick={() => setParams(new URLSearchParams(depot ? { depot_id: depot } : {}))}>clear</button></p>}
        </div>
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
                <td><StatusPill status={c.status} />{flags.find((f) => f.candidate_id === c.id) && <span title={flags.find((f) => f.candidate_id === c.id)!.note} className="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-900">FYI</span>}</td>
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
