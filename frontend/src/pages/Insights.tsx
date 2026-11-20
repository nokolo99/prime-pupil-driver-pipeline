import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, label, type Lookups } from "../api";

type Value = {
  first_contact_median_s: number | null; first_contact_n: number;
  automated_30d: Record<string, number>; recruiters: number;
  stage_conversion: { stage: string; passed: number; lost: number; rate: number | null }[]; applications_30d: number;
};
type Data = {
  value: Value;
  trend: { week_start: string; week_end: string; applications: number; hires: number }[];
  baseline: { hires_per_month: number; days_to_hire: number; goal_hires_per_month: number };
  totals: { candidates: number; active: number; hired_30d: number; lost: number; median_days_to_hire: number | null };
  funnel: { stage: string; reached: number }[];
  days_per_stage: { stage: string; median_days: number | null; n: number }[];
  drop_reasons: [string, number][];
  drop_by_stage: Record<string, Record<string, number>>;
  by_depot: { depot_id: number; depot: string; city: string; applied: number; active: number; hired: number; hired_30d: number;
              needs_review: number; lost: number; stuck: number; conversion: number | null; median_days_to_hire: number | null }[];
  automation: { follow_ups: number; results_processed: number; advanced: number; advanced_no_recruiter: number };
};

// Metric definition: hover (or tap) the ⓘ.
function Info({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative ml-1 inline-block align-middle">
      <button type="button" aria-label="Definition" className="text-xs text-stone-400 hover:text-stone-700"
        onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)} onClick={() => setOpen(!open)}>ⓘ</button>
      {open && <span className="absolute left-1/2 top-5 z-20 w-64 -translate-x-1/2 rounded border bg-white p-2 text-xs font-normal text-stone-700 shadow">{text}</span>}
    </span>
  );
}

const DEF = {
  hires30: "Candidates who signed their offer in the last 30 days. Baseline (17/mo) and goal (35/mo) are from Prime Pupil.",
  tth: "Median days from application (arrival from Workday) to signed offer, for hired candidates.",
  active: "Candidates still in the process: not hired, dropped, or rejected.",
  noTouch: "Of candidates who moved past at least one stage, the share with no recruiter action on their record (approvals, rejections, manual updates). The rest of the work was follow-ups, reminders and results handled by the system.",
  firstContact: "Median time from a candidate arriving from Workday to the first message we send them.",
  hours: "Automated actions in the last 30 days × the minutes each would take a recruiter by hand (editable), converted to hours per week.",
  whatif: "Applications per month × each stage's pass rate (among candidates who finished or left that stage). Sliders reduce one stage's drop-off; others stay the same.",
  trend: "Applications = candidates who arrived from Workday that week. Hires = offers signed that week. Click a week for details.",
  funnel: "How many candidates ever reached each stage; % = share continuing from the previous stage. Includes candidates still in progress.",
  days: "Median days from entering a stage to completing it, among candidates who passed it.",
  why: "Reason recorded when a candidate was dropped or rejected (by a recruiter, or after 90 days without a response).",
  where: "The stage a candidate was at when they were dropped or rejected.",
  depot: "Conversion = hired ÷ (hired + lost). Stuck = active candidates in their stage longer than its time limit (configurable). Highlighted: the lowest-converting depots.",
};

function Tile({ value, label: l, sub, info }: { value: string | number; label: string; sub?: string; info?: string }) {
  return (
    <div className="rounded-lg border bg-white p-4">
      <div className="text-3xl font-semibold tabular-nums">{value}</div>
      <div className="text-sm text-stone-600">{l}{info && <Info text={info} />}</div>
      {sub && <div className="mt-1 text-xs text-stone-400">{sub}</div>}
    </div>
  );
}

// Single-series horizontal bars: one hue, value labeled at the end, hover tooltip.
type SortMode = "natural" | "desc" | "asc" | "name";
const SORT_LABELS: Record<SortMode, string> = { natural: "Stage order", desc: "Largest first", asc: "Smallest first", name: "A–Z" };

function SortPicker({ value, onChange, naturalLabel = "Stage order" }: { value: SortMode; onChange: (m: SortMode) => void; naturalLabel?: string }) {
  return (
    <select aria-label="Sort" className="rounded border bg-white px-1.5 py-0.5 text-xs text-stone-600" value={value} onChange={(e) => onChange(e.target.value as SortMode)}>
      {(Object.keys(SORT_LABELS) as SortMode[]).map((m) => <option key={m} value={m}>{m === "natural" ? naturalLabel : SORT_LABELS[m]}</option>)}
    </select>
  );
}

function sortRows<T extends { key: string; value: number }>(rows: T[], mode: SortMode): T[] {
  const r = [...rows];
  if (mode === "desc") r.sort((a, b) => b.value - a.value);
  if (mode === "asc") r.sort((a, b) => a.value - b.value);
  if (mode === "name") r.sort((a, b) => label(a.key).localeCompare(label(b.key)));
  return r;
}

// A chart card with a title, subtitle and its own sort control.
function Card({ title, sub, sort, setSort, naturalLabel, info, children }: { title: string; sub: string; sort?: SortMode; setSort?: (m: SortMode) => void; naturalLabel?: string; info?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border bg-white p-4">
      <div className="mb-1 flex items-start justify-between gap-2"><h3 className="font-semibold">{title}{info && <Info text={info} />}</h3>{sort && setSort && <SortPicker value={sort} onChange={setSort} naturalLabel={naturalLabel} />}</div>
      <p className="mb-3 text-xs text-stone-500">{sub}</p>
      {children}
    </section>
  );
}

function Bars({ rows, max, unit = "", note, onPick, sort = "natural" }: { rows: { key: string; value: number; tip: string }[]; max: number; unit?: string; note?: (k: string) => string; onPick?: (k: string) => void; sort?: SortMode }) {
  return (
    <div className="space-y-1.5">
      {sortRows(rows, sort).map((r) => (
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
function Trend({ data, onWeek }: { data: Data["trend"]; onWeek: (w: Data["trend"][number], action: "filter" | "applicants" | "hires") => void }) {
  const [hover, setHover] = useState<number | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
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
        {data.map((_, i) => <rect key={i} x={x(i) - (W - P.l - P.r) / data.length / 2} y={P.t} width={(W - P.l - P.r) / data.length} height={H - P.t - P.b} fill="transparent" className="cursor-pointer" onMouseEnter={() => setHover(i)} onClick={() => setPicked(i)} />)}
      </svg>
      {hover !== null && picked === null && <div className="pointer-events-none absolute top-0 rounded border bg-white px-2 py-1 text-xs shadow" style={{ left: `${(x(hover) / W) * 100}%`, transform: "translateX(-50%)" }}>
        Week of {fmt(data[hover].week_start)}<br /><span className="text-[#2a78d6]">●</span> {data[hover].applications} applications · <span className="text-[#eb6834]">●</span> {data[hover].hires} hires
        <br /><span className="text-stone-400">Click for details</span>
      </div>}
      {picked !== null && <div className="absolute top-0 z-10 w-60 rounded border bg-white p-2 text-xs shadow-lg" style={{ left: `${Math.min(Math.max((x(picked) / W) * 100, 15), 85)}%`, transform: "translateX(-50%)" }}>
        <div className="mb-1 flex justify-between"><b>Week of {fmt(data[picked].week_start)}</b><button className="text-stone-400" onClick={() => setPicked(null)}>✕</button></div>
        <div className="mb-2 text-stone-600">{data[picked].applications} applications · {data[picked].hires} hires</div>
        {([["filter", "Filter dashboard to this week's applicants"], ["applicants", "See this week's applicants →"], ["hires", "See this week's hires →"]] as const).map(([a, l]) => (
          <button key={a} className="block w-full rounded px-1 py-1 text-left hover:bg-stone-100" onClick={() => { onWeek(data[picked], a); setPicked(null); }}>{l}</button>
        ))}
      </div>}
      <div className="mt-1 flex gap-4 text-xs text-stone-600"><span><span className="text-[#2a78d6]">━</span> Applications</span><span><span className="text-[#eb6834]">━</span> Hires</span></div>
    </div>
  );
}

const MINUTES_DEFAULT: Record<string, { label: string; min: number }> = {
  text_follow_ups: { label: "Text follow-up", min: 3 },
  call_follow_ups: { label: "Follow-up call", min: 6 },
  results_processed: { label: "Checking inbox for a result + updating records", min: 5 },
  appointment_reminders: { label: "Appointment / training reminder", min: 2 },
  screenings_completed: { label: "Phone screen", min: 15 },
  stage_updates_synced: { label: "Updating Workday / spreadsheet after a step", min: 3 },
};

function fmtDuration(sec: number | null) {
  if (sec === null) return "—";
  if (sec < 60) return "< 1 min";
  if (sec < 3600) return `${Math.round(sec / 60)} min`;
  if (sec < 86400) return `${(sec / 3600).toFixed(1)} h`;
  return `${(sec / 86400).toFixed(1)} days`;
}

function HoursSaved({ v }: { v: Value }) {
  const [mins, setMins] = useState<Record<string, number>>(() => {
    try { return { ...Object.fromEntries(Object.entries(MINUTES_DEFAULT).map(([k, x]) => [k, x.min])), ...JSON.parse(localStorage.getItem("pp_minutes") ?? "{}") }; }
    catch { return Object.fromEntries(Object.entries(MINUTES_DEFAULT).map(([k, x]) => [k, x.min])); }
  });
  const set = (k: string, n: number) => { const next = { ...mins, [k]: n }; setMins(next); try { localStorage.setItem("pp_minutes", JSON.stringify(next)); } catch { /* ignore */ } };
  const total30 = Object.keys(MINUTES_DEFAULT).reduce((sum, k) => sum + (v.automated_30d[k] ?? 0) * (mins[k] ?? 0), 0) / 60;
  const perWeek = total30 / (30 / 7);
  return (
    <div>
      <div className="flex items-baseline gap-3"><span className="text-3xl font-semibold tabular-nums">{Math.round(perWeek)} h</span><span className="text-sm text-stone-600">recruiter time saved per week</span></div>
      <p className="text-xs text-stone-500">≈ {(perWeek / v.recruiters).toFixed(1)} h per recruiter per week ({v.recruiters} recruiters) · based on the last 30 days</p>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-xs text-stone-500">How this is calculated (edit the minutes)</summary>
        <table className="mt-2 w-full text-xs">
          <thead className="text-left text-stone-500"><tr><th className="py-1">Automated action</th><th>Count (30d)</th><th>Minutes each</th><th className="text-right">Hours</th></tr></thead>
          <tbody>
            {Object.entries(MINUTES_DEFAULT).map(([k, x]) => (
              <tr key={k} className="border-t"><td className="py-1">{x.label}</td><td className="tabular-nums">{(v.automated_30d[k] ?? 0).toLocaleString()}</td>
                <td><input type="number" min={0} className="w-14 rounded border px-1" value={mins[k]} onChange={(e) => set(k, Number(e.target.value))} /></td>
                <td className="text-right tabular-nums">{(((v.automated_30d[k] ?? 0) * (mins[k] ?? 0)) / 60).toFixed(0)}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="mt-1 text-xs text-stone-400">Minutes are assumptions about how long each task takes a recruiter by hand today. Adjust to your team's reality.</p>
      </details>
    </div>
  );
}

function WhatIf({ v, goal, baseline }: { v: Value; goal: number; baseline: number }) {
  const [cut, setCut] = useState<Record<string, number>>({});
  const stages = v.stage_conversion.filter((c) => c.rate !== null);
  const project = (adj: boolean) => stages.reduce((p, c) => p * (1 - (1 - (c.rate ?? 1)) * (adj ? 1 - (cut[c.stage] ?? 0) / 100 : 1)), v.applications_30d);
  const now = project(false), proj = project(true);
  const pct = (x: number) => Math.min((x / Math.max(goal * 1.3, proj, now)) * 100, 100);
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-baseline gap-x-6 gap-y-1">
        <div><span className="text-3xl font-semibold tabular-nums">{Math.round(proj)}</span> <span className="text-sm text-stone-600">projected hires / month</span></div>
        <div className="text-xs text-stone-500">Current funnel: {Math.round(now)}/mo · Baseline {baseline} · Goal {goal}</div>
      </div>
      <div className="relative mb-4 h-3 rounded-full bg-stone-100">
        <div className="h-3 rounded-full bg-emerald-700" style={{ width: `${pct(proj)}%` }} />
        <div className="absolute -top-1 h-5 w-0.5 bg-stone-800" style={{ left: `${pct(goal)}%` }} title={`Goal: ${goal}/mo`} />
        <span className="absolute -top-5 text-[10px] text-stone-600" style={{ left: `${pct(goal)}%`, transform: "translateX(-50%)" }}>Goal {goal}</span>
      </div>
      <div className="space-y-2">
        {stages.map((c) => (
          <label key={c.stage} className="flex items-center gap-3 text-sm">
            <span className="w-28 shrink-0 text-stone-600">{label(c.stage)}</span>
            <input type="range" min={0} max={75} step={5} value={cut[c.stage] ?? 0} onChange={(e) => setCut({ ...cut, [c.stage]: Number(e.target.value) })} className="flex-1 accent-emerald-700" />
            <span className="w-56 shrink-0 whitespace-nowrap text-right text-xs text-stone-600">−{cut[c.stage] ?? 0}% drop-off <span className="text-stone-400">· today {Math.round((1 - (c.rate ?? 1)) * 100)}% lost</span></span>
          </label>
        ))}
      </div>
      <p className="mt-2 text-xs text-stone-400">Model: {v.applications_30d} applications/month × each stage's pass rate. Each slider reduces that stage's drop-off; other stages unchanged. An estimate, not a promise.</p>
    </div>
  );
}

type DepotRow = Data["by_depot"][number];
const DEPOT_COLS: { key: keyof DepotRow; label: string; fmt?: (v: number | null) => string }[] = [
  { key: "depot", label: "Depot" }, { key: "applied", label: "Applied" }, { key: "active", label: "Active" },
  { key: "stuck", label: "Stuck" }, { key: "needs_review", label: "Needs review" }, { key: "hired_30d", label: "Hires (30d)" },
  { key: "conversion", label: "Conversion", fmt: (v) => (v === null ? "—" : `${v}%`) },
  { key: "median_days_to_hire", label: "Median days to hire", fmt: (v) => (v === null ? "—" : `${v}d`) }, { key: "lost", label: "Lost" },
];

function DepotTable({ rows, onPick }: { rows: DepotRow[]; onPick: (depotId: number) => void }) {
  const [sort, setSort] = useState<{ key: keyof DepotRow; dir: 1 | -1 }>({ key: "active", dir: -1 });
  const sorted = [...rows].sort((a, b) => {
    const x = a[sort.key], y = b[sort.key];
    if (typeof x === "string" && typeof y === "string") return x.localeCompare(y) * sort.dir;
    return ((Number(x ?? -1)) - (Number(y ?? -1))) * sort.dir;
  });
  const convs = rows.map((r) => r.conversion).filter((v): v is number => v !== null).sort((a, b) => a - b);
  const cutoff = convs[Math.min(2, convs.length - 1)];  // bottom 3 depots by conversion
  return (
    <section className="overflow-x-auto rounded-lg border bg-white">
      <h3 className="p-4 pb-2 font-semibold">By depot<Info text={DEF.depot} /> <span className="text-xs font-normal text-stone-500">· click a column to sort, a row to see its candidates</span></h3>
      <table className="w-full text-sm">
        <thead className="text-left text-stone-500"><tr>
          {DEPOT_COLS.map((c, i) => (
            <th key={c.key} className={`cursor-pointer select-none py-2 hover:text-stone-800 ${i === 0 ? "px-4" : "pr-3"}`}
              onClick={() => setSort({ key: c.key, dir: sort.key === c.key ? (-sort.dir as 1 | -1) : (c.key === "depot" ? 1 : -1) })}>
              {c.label}{sort.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
            </th>
          ))}
        </tr></thead>
        <tbody className="divide-y">
          {sorted.map((r) => {
            const low = r.conversion !== null && cutoff !== undefined && r.conversion <= cutoff;
            return (
              <tr key={r.depot} className={`cursor-pointer ${low ? "bg-amber-50 hover:bg-amber-100" : "hover:bg-stone-50"}`} onClick={() => onPick(r.depot_id)}
                title={low ? "Among the lowest-converting depots" : ""}>
                {DEPOT_COLS.map((c, i) => (
                  <td key={c.key} className={`py-2 tabular-nums ${i === 0 ? "px-4" : "pr-3"} ${c.key === "lost" ? "text-stone-500" : ""} ${c.key === "conversion" && low ? "font-semibold text-amber-800" : ""}`}>
                    {i === 0 ? <>{r.depot} <span className="text-stone-400">({r.city})</span></> : c.fmt ? c.fmt(r[c.key] as number | null) : (r[c.key] as number) || (c.key === "stuck" || c.key === "needs_review" ? "—" : 0)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
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
  const [sorts, setSorts] = useState<Record<string, SortMode>>({ funnel: "natural", days: "natural", why: "desc", where: "natural" });
  const sortFor = (k: string) => ({ sort: sorts[k], setSort: (m: SortMode) => setSorts({ ...sorts, [k]: m }) });
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
      {f.applied_from && <div className="text-sm"><span className="rounded-full bg-sky-100 px-3 py-1 text-sky-900">Applied week of {new Date(f.applied_from + "T12:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" })}
        <button className="ml-2" aria-label="Remove week filter" onClick={() => { const { applied_from: _a, applied_to: _b, ...rest } = f; setF(rest); }}>✕</button></span></div>}
      {f.channel && <p className="text-xs text-amber-800">Note: candidates who stay in the process longer get more calls, so this comparison shows correlation, not that calls cause hires.</p>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile info={DEF.hires30} value={d.totals.hired_30d} label="Hires, last 30 days" sub={`Baseline ${d.baseline.hires_per_month}/mo · Goal ${d.baseline.goal_hires_per_month}/mo`} />
        <Tile info={DEF.tth} value={d.totals.median_days_to_hire ? `${d.totals.median_days_to_hire}d` : "—"} label="Median time to hire" sub={`Baseline ~${d.baseline.days_to_hire} days`} />
        <Tile info={DEF.active} value={d.totals.active} label="Active candidates" sub={`${d.totals.candidates} total`} />
        <Tile info={DEF.noTouch} value={a.advanced ? `${Math.round((a.advanced_no_recruiter / a.advanced) * 100)}%` : "—"} label="Moved forward with no recruiter touch" sub={`${a.follow_ups.toLocaleString()} follow-ups · ${a.results_processed} results processed automatically`} />
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <section className="rounded-lg border bg-white p-4">
          <h3 className="mb-1 font-semibold">Speed to first contact<Info text={DEF.firstContact} /></h3>
          <div className="text-3xl font-semibold tabular-nums whitespace-nowrap">{fmtDuration(d.value.first_contact_median_s)}</div>
          <div className="text-sm text-stone-600">median, application → first message</div>
          <p className="mt-1 text-xs text-stone-500">Today: a recruiter reaches out "within a few days, sometimes a week." Measured across {d.value.first_contact_n.toLocaleString()} candidates.</p>
        </section>
        <section className="rounded-lg border bg-white p-4 lg:col-span-2">
          <h3 className="mb-1 font-semibold">Recruiter time saved<Info text={DEF.hours} /></h3>
          <HoursSaved v={d.value} />
        </section>
      </div>

      <section className="rounded-lg border bg-white p-4">
        <h3 className="mb-1 font-semibold">What it takes to hit {d.baseline.goal_hires_per_month} hires a month<Info text={DEF.whatif} /></h3>
        <p className="mb-4 text-xs text-stone-500">Drag a stage to see what reducing its drop-off does to monthly hires</p>
        <WhatIf v={d.value} goal={d.baseline.goal_hires_per_month} baseline={d.baseline.hires_per_month} />
      </section>

      <section className="rounded-lg border bg-white p-4">
        <h3 className="mb-1 font-semibold">Weekly trend<Info text={DEF.trend} /></h3>
        <p className="mb-2 text-xs text-stone-500">Applications received and hires made per week, last 13 weeks</p>
        <Trend data={d.trend} onWeek={(w, a) => {
          if (a === "filter") setF({ ...f, applied_from: w.week_start, applied_to: w.week_end, days: "" });
          else if (a === "applicants") drill({ applied_from: w.week_start, applied_to: w.week_end });
          else nav(`/pipeline?${new URLSearchParams({ hired_from: w.week_start, hired_to: w.week_end })}`);
        }} />
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card info={DEF.funnel} title="Funnel" sub="Candidates who reached each stage · % continuing from the previous stage" {...sortFor("funnel")}>
          <Bars sort={sorts.funnel} rows={d.funnel.map((f) => ({ key: f.stage, value: f.reached, tip: `${f.reached} reached ${label(f.stage)}` }))} max={fmax}
            note={(k) => conv(d.funnel.findIndex((x) => x.stage === k))} onPick={(k) => drill(k === "hired" ? { status: "hired" } : { stage: k })} />
        </Card>
        <Card info={DEF.days} title="Median days per stage" sub="From entering a stage to completing it" {...sortFor("days")}>
          <Bars sort={sorts.days} rows={d.days_per_stage.map((x) => ({ key: x.stage, value: x.median_days ?? 0, tip: `${label(x.stage)}: median ${x.median_days ?? "—"} days (n=${x.n})` }))} max={dmax} unit="d"
            onPick={(k) => drill({ stage: k })} />
        </Card>
        <Card info={DEF.why} title="Why candidates stopped" sub="Drop-off and rejection reasons, all stages" naturalLabel="Default" {...sortFor("why")}>
          <Bars sort={sorts.why} rows={d.drop_reasons.map(([r, n]) => ({ key: r, value: n, tip: Object.entries(d.drop_by_stage).filter(([, v]) => v[r]).map(([st, v]) => `${label(st)}: ${v[r]}`).join(" · ") }))} max={rmax}
            onPick={(r) => drill({ status: "lost", reason: r })} />
        </Card>
        <Card info={DEF.where} title="Where they stopped" sub="Candidates lost at each stage" {...sortFor("where")}>
          <Bars sort={sorts.where} rows={d.funnel.filter((f) => f.stage !== "hired").map((f) => {
            const n = Object.values(d.drop_by_stage[f.stage] ?? {}).reduce((x, y) => x + y, 0);
            return { key: f.stage, value: n, tip: Object.entries(d.drop_by_stage[f.stage] ?? {}).map(([r, v]) => `${label(r)}: ${v}`).join(" · ") || "None" };
          })} max={Math.max(...Object.values(d.drop_by_stage).map((v) => Object.values(v).reduce((x, y) => x + y, 0)), 1)}
            onPick={(k) => drill({ status: "lost", stage: k })} />
        </Card>
      </div>

      <DepotTable rows={d.by_depot} onPick={(id) => drill({ depot_id: String(id) })} />
    </div>
  );
}
