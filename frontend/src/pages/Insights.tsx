import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, label, type Lookups } from "../api";

type Data = {
  trend: { week_start: string; applications: number; hires: number }[];
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
function Bars({ rows, max, unit = "", note, onPick }: { rows: { key: string; value: number; tip: string }[]; max: number; unit?: string; note?: (k: string) => string; onPick?: (k: string) => void }) {
  return (
    <div className="space-y-1.5">
      {rows.map((r) => (
        <div key={r.key} className={`group flex items-center gap-2 text-sm ${onPick ? "cursor-pointer" : ""}`} title={r.tip + (onPick ? " · click to see candidates" : "")} onClick={() => onPick?.(r.key)}>
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

// Two series, same unit (people per week) on one axis. Blue = applications, orange = hires (validated CVD-safe pair).
function Trend({ data }: { data: Data["trend"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 640, H = 200, P = { l: 32, r: 70, t: 12, b: 24 };
  const max = Math.max(...data.map((d) => Math.max(d.applications, d.hires)), 1);
  const x = (i: number) => P.l + (i / Math.max(data.length - 1, 1)) * (W - P.l - P.r);
  const y = (v: number) => P.t + (1 - v / max) * (H - P.t - P.b);
  const path = (k: "applications" | "hires") => data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d[k])}`).join(" ");
  const last = data.length - 1;
  const fmt = (iso: string) => new Date(iso + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" onMouseLeave={() => setHover(null)}>
        {[0, 0.5, 1].map((f) => <g key={f}><line x1={P.l} x2={W - P.r} y1={y(max * f)} y2={y(max * f)} stroke="#e7e5e4" /><text x={P.l - 6} y={y(max * f) + 4} fontSize="10" textAnchor="end" fill="#78716c">{Math.round(max * f)}</text></g>)}
        {data.map((d, i) => i % 3 === 0 && <text key={i} x={x(i)} y={H - 6} fontSize="10" textAnchor="middle" fill="#78716c">{fmt(d.week_start)}</text>)}
        <path d={path("applications")} fill="none" stroke="#2a78d6" strokeWidth="2" />
        <path d={path("hires")} fill="none" stroke="#eb6834" strokeWidth="2" />
        <text x={x(last) + 6} y={y(data[last]?.applications ?? 0) + 4} fontSize="11" fill="#44403c">Applications</text>
        <text x={x(last) + 6} y={y(data[last]?.hires ?? 0) + 4} fontSize="11" fill="#44403c">Hires</text>
        {hover !== null && <line x1={x(hover)} x2={x(hover)} y1={P.t} y2={H - P.b} stroke="#a8a29e" strokeDasharray="3 3" />}
        {hover !== null && (["applications", "hires"] as const).map((k) => <circle key={k} cx={x(hover)} cy={y(data[hover][k])} r="4" fill={k === "applications" ? "#2a78d6" : "#eb6834"} stroke="#fff" strokeWidth="2" />)}
        {data.map((_, i) => <rect key={i} x={x(i) - (W - P.l - P.r) / data.length / 2} y={P.t} width={(W - P.l - P.r) / data.length} height={H - P.t - P.b} fill="transparent" onMouseEnter={() => setHover(i)} />)}
      </svg>
      {hover !== null && <div className="pointer-events-none absolute top-0 rounded border bg-white px-2 py-1 text-xs shadow" style={{ left: `${(x(hover) / W) * 100}%`, transform: "translateX(-50%)" }}>
        Week of {fmt(data[hover].week_start)}<br /><span className="text-[#2a78d6]">●</span> {data[hover].applications} applications · <span className="text-[#eb6834]">●</span> {data[hover].hires} hires
      </div>}
      <div className="mt-1 flex gap-4 text-xs text-stone-600"><span><span className="text-[#2a78d6]">━</span> Applications</span><span><span className="text-[#eb6834]">━</span> Hires</span></div>
    </div>
  );
}

const FILTERS = [
  { key: "days", label: "Applied", options: [["", "All time"], ["7", "Last 7 days"], ["30", "Last 30 days"], ["90", "Last 90 days"]] },
  { key: "language", label: "Language", options: [["", "All languages"], ["en", "English"], ["es", "Spanish"], ["other", "Other"]] },
  { key: "channel", label: "Channel", options: [["", "All channels"], ["calls", "Received AI calls"], ["texts", "Texts only"]] },
  { key: "status", label: "Status", options: [["", "All statuses"], ["active", "Active"], ["hired", "Hired"], ["lost", "Lost"]] },
] as const;

export default function Insights() {
  const [d, setD] = useState<Data | null>(null);
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  const [f, setF] = useState<Record<string, string>>({});
  const nav = useNavigate();
  const qs = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
  useEffect(() => { api<Lookups>("/lookups").then(setLk); }, []);
  useEffect(() => {
    const load = () => { api<Data>(`/insights${qs ? `?${qs}` : ""}`).then(setD); };
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, [qs]);
  // Click-through: open the Pipeline with the same filters plus what was clicked.
  const drill = (extra: Record<string, string>) => nav(`/pipeline?${new URLSearchParams({ ...Object.fromEntries(Object.entries(f).filter(([, v]) => v)), ...extra })}`);
  const sel = "rounded border bg-white px-2 py-1 text-sm";
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
        {qs && <button className="text-sm text-stone-500 hover:underline" onClick={() => setF({})}>Clear filters</button>}
      </div>
      <div className="flex flex-wrap gap-2">
        {FILTERS.map((fl) => (
          <select key={fl.key} aria-label={fl.label} className={sel} value={f[fl.key] ?? ""} onChange={(e) => setF({ ...f, [fl.key]: e.target.value })}>
            {fl.options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        ))}
        <select aria-label="Depot" className={sel} value={f.depot_id ?? ""} onChange={(e) => setF({ ...f, depot_id: e.target.value })}>
          <option value="">All 12 depots</option>
          {lk.depots.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.city})</option>)}
        </select>
        <select aria-label="Recruiter" className={sel} value={f.recruiter_id ?? ""} onChange={(e) => setF({ ...f, recruiter_id: e.target.value })}>
          <option value="">All recruiters</option>
          {lk.recruiters.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
      </div>
      {f.channel && <p className="text-xs text-amber-800">Note: candidates who stay in the process longer get more calls, so this comparison shows correlation, not that calls cause hires.</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile value={d.totals.hired_30d} label="Hires, last 30 days" sub={`Baseline ${d.baseline.hires_per_month}/mo · Goal ${d.baseline.goal_hires_per_month}/mo`} />
        <Tile value={d.totals.median_days_to_hire ? `${d.totals.median_days_to_hire}d` : "—"} label="Median time to hire" sub={`Baseline ~${d.baseline.days_to_hire} days`} />
        <Tile value={d.totals.active} label="Active candidates" sub={`${d.totals.candidates} total`} />
        <Tile value={a.advanced ? `${Math.round((a.advanced_no_recruiter / a.advanced) * 100)}%` : "—"} label="Moved forward with no recruiter touch" sub={`${a.follow_ups.toLocaleString()} follow-ups · ${a.results_processed} results processed automatically`} />
      </div>

      <section className="rounded-lg border bg-white p-4">
        <h3 className="mb-1 font-semibold">Weekly trend</h3>
        <p className="mb-2 text-xs text-stone-500">Applications received and hires made per week, last 13 weeks</p>
        <Trend data={d.trend} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="rounded-lg border bg-white p-4">
          <h3 className="mb-1 font-semibold">Funnel</h3>
          <p className="mb-3 text-xs text-stone-500">Candidates who reached each stage · % continuing from the previous stage</p>
          <Bars rows={d.funnel.map((f) => ({ key: f.stage, value: f.reached, tip: `${f.reached} reached ${label(f.stage)}` }))} max={fmax}
            note={(k) => conv(d.funnel.findIndex((x) => x.stage === k))} onPick={(k) => drill(k === "hired" ? { status: "hired" } : { stage: k })} />
        </section>
        <section className="rounded-lg border bg-white p-4">
          <h3 className="mb-1 font-semibold">Median days per stage</h3>
          <p className="mb-3 text-xs text-stone-500">From entering a stage to completing it</p>
          <Bars rows={d.days_per_stage.map((x) => ({ key: x.stage, value: x.median_days ?? 0, tip: `${label(x.stage)}: median ${x.median_days ?? "—"} days (n=${x.n})` }))} max={dmax} unit="d" />
        </section>
        <section className="rounded-lg border bg-white p-4">
          <h3 className="mb-1 font-semibold">Why candidates stopped</h3>
          <p className="mb-3 text-xs text-stone-500">Drop-off and rejection reasons, all stages</p>
          <Bars rows={d.drop_reasons.map(([r, n]) => ({ key: r, value: n, tip: Object.entries(d.drop_by_stage).filter(([, v]) => v[r]).map(([st, v]) => `${label(st)}: ${v[r]}`).join(" · ") }))} max={rmax}
            onPick={(r) => drill({ status: "lost", reason: r })} />
        </section>
        <section className="rounded-lg border bg-white p-4">
          <h3 className="mb-1 font-semibold">Where they stopped</h3>
          <p className="mb-3 text-xs text-stone-500">Candidates lost at each stage</p>
          <Bars rows={d.funnel.filter((f) => f.stage !== "hired").map((f) => {
            const n = Object.values(d.drop_by_stage[f.stage] ?? {}).reduce((x, y) => x + y, 0);
            return { key: f.stage, value: n, tip: Object.entries(d.drop_by_stage[f.stage] ?? {}).map(([r, v]) => `${label(r)}: ${v}`).join(" · ") || "None" };
          })} max={Math.max(...Object.values(d.drop_by_stage).map((v) => Object.values(v).reduce((x, y) => x + y, 0)), 1)}
            onPick={(k) => drill({ status: "lost", stage: k })} />
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
