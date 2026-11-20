import { useEffect, useState } from "react";
import { api, label, type Lookups } from "../api";

type Data = {
  baseline: { hires_per_month: number; days_to_hire: number; goal_hires_per_month: number };
  totals: { candidates: number; active: number; hired_30d: number; lost: number; median_days_to_hire: number | null };
  funnel: { stage: string; reached: number }[];
  days_per_stage: { stage: string; median_days: number | null; n: number }[];
  drop_reasons: [string, number][];
  drop_by_stage: Record<string, Record<string, number>>;
  by_depot: { depot: string; city: string; active: number; hired_30d: number; needs_review: number; lost: number }[];
  automation: { follow_ups: number; results_processed: number; advanced: number; advanced_no_recruiter: number };
};

function Tile({ value, label: l, sub }: { value: string | number; label: string; sub?: string }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="text-3xl font-semibold tabular-nums">{value}</div>
      <div className="text-sm text-stone-600">{l}</div>
      {sub && <div className="mt-1 text-xs text-stone-400">{sub}</div>}
    </div>
  );
}

// Single-series horizontal bars: one hue, value labeled at the end, hover tooltip.
function Bars({ rows, max, unit = "", note }: { rows: { key: string; value: number; tip: string }[]; max: number; unit?: string; note?: (k: string) => string }) {
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.key} className="group flex items-center gap-2 text-sm" title={r.tip}>
          <span className="w-28 shrink-0 text-stone-600">{label(r.key)}</span>
          <div className="relative h-5 flex-1">
            <div className="h-full rounded-r bg-emerald-700 transition-colors group-hover:bg-emerald-800" style={{ width: `${max ? Math.max((r.value / max) * 100, 0.5) : 0}%` }} />
          </div>
          <span className="w-16 shrink-0 text-right tabular-nums text-stone-700">{r.value}{unit}</span>
          {note && <span className="w-14 shrink-0 text-right text-xs text-stone-400">{note(r.key)}</span>}
        </div>
      ))}
    </div>
  );
}

export default function Insights() {
  const [d, setD] = useState<Data | null>(null);
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  const [depot, setDepot] = useState("");
  useEffect(() => { api<Lookups>("/lookups").then(setLk); }, []);
  useEffect(() => {
    const load = () => { api<Data>(`/insights${depot ? `?depot_id=${depot}` : ""}`).then(setD); };
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [depot]);
  if (!d) return <p className="text-stone-500">Loading…</p>;

  const fmax = Math.max(...d.funnel.map((f) => f.reached), 1);
  const conv = (i: number) => (i === 0 || !d.funnel[i - 1].reached ? "" : `${Math.round((d.funnel[i].reached / d.funnel[i - 1].reached) * 100)}%`);
  const dmax = Math.max(...d.days_per_stage.map((x) => x.median_days ?? 0), 1);
  const rmax = Math.max(...d.drop_reasons.map(([, n]) => n), 1);
  const a = d.automation;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Insights</h2>
          <p className="text-xs text-stone-500">Illustrative demo data (not a projection). Baseline and goal from Prime Pupil.</p>
        </div>
        <select className="rounded border bg-white px-2 py-1 text-sm" value={depot} onChange={(e) => setDepot(e.target.value)}>
          <option value="">All 12 depots</option>
          {lk.depots.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.city})</option>)}
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile value={d.totals.hired_30d} label="Hires, last 30 days" sub={`Baseline ${d.baseline.hires_per_month}/mo · Goal ${d.baseline.goal_hires_per_month}/mo`} />
        <Tile value={d.totals.median_days_to_hire ? `${d.totals.median_days_to_hire}d` : "—"} label="Median time to hire" sub={`Baseline ~${d.baseline.days_to_hire} days`} />
        <Tile value={d.totals.active} label="Active candidates" sub={`${d.totals.candidates} total`} />
        <Tile value={a.advanced ? `${Math.round((a.advanced_no_recruiter / a.advanced) * 100)}%` : "—"} label="Moved forward with no recruiter touch" sub={`${a.follow_ups.toLocaleString()} follow-ups · ${a.results_processed} results processed automatically`} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-lg border bg-white p-4">
          <h3 className="mb-1 font-semibold">Funnel</h3>
          <p className="mb-3 text-xs text-stone-500">Candidates who reached each stage · % continuing from the previous stage</p>
          <Bars rows={d.funnel.map((f) => ({ key: f.stage, value: f.reached, tip: `${f.reached} reached ${label(f.stage)}` }))} max={fmax}
            note={(k) => conv(d.funnel.findIndex((f) => f.stage === k))} />
        </section>
        <section className="rounded-lg border bg-white p-4">
          <h3 className="mb-1 font-semibold">Median days per stage</h3>
          <p className="mb-3 text-xs text-stone-500">From entering a stage to completing it</p>
          <Bars rows={d.days_per_stage.map((x) => ({ key: x.stage, value: x.median_days ?? 0, tip: `${label(x.stage)}: median ${x.median_days ?? "—"} days (n=${x.n})` }))} max={dmax} unit="d" />
        </section>
        <section className="rounded-lg border bg-white p-4">
          <h3 className="mb-1 font-semibold">Why candidates stopped</h3>
          <p className="mb-3 text-xs text-stone-500">Drop-off and rejection reasons, all stages</p>
          <Bars rows={d.drop_reasons.map(([r, n]) => ({ key: r, value: n, tip: Object.entries(d.drop_by_stage).filter(([, v]) => v[r]).map(([st, v]) => `${label(st)}: ${v[r]}`).join(" · ") }))} max={rmax} />
        </section>
        <section className="rounded-lg border bg-white p-4">
          <h3 className="mb-1 font-semibold">Where they stopped</h3>
          <p className="mb-3 text-xs text-stone-500">Candidates lost at each stage</p>
          <Bars rows={d.funnel.filter((f) => f.stage !== "hired").map((f) => {
            const n = Object.values(d.drop_by_stage[f.stage] ?? {}).reduce((x, y) => x + y, 0);
            return { key: f.stage, value: n, tip: Object.entries(d.drop_by_stage[f.stage] ?? {}).map(([r, v]) => `${label(r)}: ${v}`).join(" · ") || "None" };
          })} max={Math.max(...Object.values(d.drop_by_stage).map((v) => Object.values(v).reduce((x, y) => x + y, 0)), 1)} />
        </section>
      </div>

      <section className="overflow-x-auto rounded-lg border bg-white">
        <h3 className="p-4 pb-2 font-semibold">By depot</h3>
        <table className="w-full text-sm">
          <thead className="text-left text-stone-500"><tr><th className="px-4 py-2">Depot</th><th>Active</th><th>Hires (30d)</th><th>Needs review</th><th>Lost</th></tr></thead>
          <tbody className="divide-y">
            {d.by_depot.map((r) => (
              <tr key={r.depot}><td className="px-4 py-2">{r.depot} <span className="text-stone-400">({r.city})</span></td>
                <td className="tabular-nums">{r.active}</td><td className="tabular-nums">{r.hired_30d}</td>
                <td className="tabular-nums">{r.needs_review || "—"}</td><td className="tabular-nums text-stone-500">{r.lost}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
