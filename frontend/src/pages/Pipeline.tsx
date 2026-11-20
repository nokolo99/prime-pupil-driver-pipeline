import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, daysSince, label, STAGES, timeAgo, type Candidate, type Lookups } from "../api";
import { StatusPill } from "../components";

// The CDL permit runs in parallel with training, so it isn't a column of its own here.
const PIPELINE_STAGES = STAGES.filter((s) => s !== "application" && s !== "cdl_permit");
const PAGE = 50;
const sel = "rounded-lg border bg-white px-2 py-1.5 text-sm";
const STATUS_TITLE: Record<string, string> = { needs_review: "Needs review", waiting_on_candidate: "Waiting on candidate", waiting_on_vendor: "Waiting on vendor",
  stuck: "Stuck candidates", hired: "Hired", lost: "Lost candidates", "": "All candidates" };
type SortKey = "name" | "depot" | "stage" | "status" | "days" | "contact";

export default function Pipeline() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  const [params, setParams] = useSearchParams();
  const stage = params.get("stage");
  const depot = params.get("depot_id") ?? "";
  const setParam = (k: string, v: string | null) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); setParams(p); setPage(0); };
  const extra = new URLSearchParams(params); extra.delete("stage"); extra.delete("depot_id");
  const extraQs = extra.toString();
  const [sla, setSla] = useState<Record<string, number>>({});
  const [flags, setFlags] = useState<{ candidate_id: number; note: string }[]>([]);
  const [q, setQ] = useState("");
  // Filters (client-side). Status defaults to Active so the tiles mean "who's in progress at each stage".
  const [status, setStatus] = useState(params.get("status") ? "" : "active");
  const [recruiter, setRecruiter] = useState("");
  const [lang, setLang] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "days", dir: -1 });
  const [page, setPage] = useState(0);

  useEffect(() => { api<Candidate[]>(`/candidates${extraQs ? `?${extraQs}` : ""}`).then(setCandidates); }, [extraQs]);
  useEffect(() => {
    api<Lookups>("/lookups").then(setLk);
    api<typeof flags>("/flags").then(setFlags);
    api<{ stage_sla_days: Record<string, number> }>("/config").then((c) => setSla(c.stage_sla_days));
  }, []);

  const stuck = (c: Candidate) => !["dropped", "rejected", "hired"].includes(c.status) && sla[c.stage] !== undefined && daysSince(c.stage_entered_at) > sla[c.stage];
  const depotName = (id: number | null) => lk.depots.find((d) => d.id === id)?.name ?? "—";
  const LOST = ["dropped", "rejected"];
  const statusOk = (c: Candidate) => {
    switch (status) {
      case "active": return !LOST.includes(c.status) && c.stage !== "hired";
      case "stuck": return stuck(c);
      case "hired": return c.stage === "hired";
      case "lost": return LOST.includes(c.status);
      case "": return true;
      default: return c.status === status;
    }
  };
  const inDepot = candidates.filter((c) => (!depot || String(c.depot_id) === depot) && (!recruiter || String(c.recruiter_id) === recruiter)
    && (!lang || (lang === "other" ? !["en", "es"].includes(c.preferred_language) : c.preferred_language === lang)) && statusOk(c));
  const ql = q.trim().toLowerCase(), digits = q.replace(/\D/g, "");
  const shown = inDepot
    .filter((c) => !stage || c.stage === stage || (stage === "training" && c.stage === "cdl_permit"))
    .filter((c) => !ql || `${c.first_name} ${c.last_name}`.toLowerCase().includes(ql) || (digits.length >= 3 && c.phone.includes(digits)));
  const val = (c: Candidate): string | number => ({
    name: `${c.first_name} ${c.last_name}`.toLowerCase(), depot: depotName(c.depot_id), stage: PIPELINE_STAGES.indexOf(c.stage),
    status: c.status, days: daysSince(c.stage_entered_at), contact: c.last_contacted_at ?? "",
  })[sort.key];
  const sorted = [...shown].sort((a, b) => { const x = val(a), y = val(b); return (x < y ? -1 : x > y ? 1 : 0) * sort.dir; });
  const pages = Math.max(1, Math.ceil(sorted.length / PAGE));
  const rows = sorted.slice(page * PAGE, page * PAGE + PAGE);
  const th = (key: SortKey, text: string, first = false) => (
    <th className={`cursor-pointer select-none py-2 font-medium hover:text-stone-800 ${first ? "px-4" : "pr-3"}`}
      onClick={() => { setSort({ key, dir: sort.key === key ? (-sort.dir as 1 | -1) : key === "name" || key === "depot" ? 1 : -1 }); setPage(0); }}>
      {text}{sort.key === key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
    </th>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">Pipeline</h2>
          {extraQs ? <p className="text-xs text-stone-500">Filtered from Insights: {[...extra.entries()].map(([k, v]) => `${label(k)} = ${label(v)}`).join(" · ")} · <button className="underline" onClick={() => setParams(new URLSearchParams(depot ? { depot_id: depot } : {}))}>clear</button></p>
            : <p className="text-sm text-stone-500">Every candidate and where they are. Rows in red are stuck past their stage's time limit.</p>}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input className="w-60 rounded-lg border bg-white px-3 py-1.5 text-sm" placeholder="Search name or phone…" value={q} onChange={(e) => { setQ(e.target.value); setPage(0); }} />
        <select aria-label="Status" className={sel} value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}>
          <option value="active">Active (in progress)</option><option value="needs_review">Needs review</option>
          <option value="waiting_on_candidate">Waiting on candidate</option><option value="waiting_on_vendor">Waiting on vendor</option>
          <option value="stuck">Stuck (past time limit)</option><option value="hired">Hired</option><option value="lost">Lost (dropped or rejected)</option>
          <option value="">All statuses</option>
        </select>
        <select aria-label="Stage" className={sel} value={stage ?? ""} onChange={(e) => setParam("stage", e.target.value || null)}>
          <option value="">All stages</option>
          {PIPELINE_STAGES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
        <select aria-label="Depot" className={sel} value={depot} onChange={(e) => setParam("depot_id", e.target.value || null)}>
          <option value="">All depots</option>
          {lk.depots.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
        <select aria-label="Recruiter" className={sel} value={recruiter} onChange={(e) => { setRecruiter(e.target.value); setPage(0); }}>
          <option value="">All recruiters</option>
          {lk.recruiters.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
        <select aria-label="Language" className={sel} value={lang} onChange={(e) => { setLang(e.target.value); setPage(0); }}>
          <option value="">All languages</option><option value="en">English</option><option value="es">Spanish</option><option value="other">Other</option>
        </select>
        {(q || status !== "active" || stage || depot || recruiter || lang) &&
          <button className="text-sm text-stone-500 underline" onClick={() => { setQ(""); setStatus("active"); setRecruiter(""); setLang(""); setParams(new URLSearchParams()); setPage(0); }}>Reset filters</button>}
      </div>

      <p className="text-xs font-medium uppercase tracking-wide text-stone-500">{status === "active" ? "Active candidates by current stage" : `${STATUS_TITLE[status] ?? "Candidates"} by current stage`} · click a stage to filter</p>

      <div className={`-mt-2 grid grid-cols-3 gap-2 ${status === "active" ? "sm:grid-cols-6" : "sm:grid-cols-7"}`}>
        {PIPELINE_STAGES.filter((s) => !(status === "active" && s === "hired")).map((s) => {
          const at = inDepot.filter((c) => c.stage === s || (s === "training" && c.stage === "cdl_permit"));
          const nStuck = at.filter(stuck).length;
          return (
            <button key={s} onClick={() => setParam("stage", stage === s ? null : s)}
              className={`rounded-xl border p-2.5 text-left transition-colors ${stage === s ? "border-emerald-700 bg-emerald-50" : "bg-white hover:bg-stone-50"}`}>
              <div className="text-xl font-semibold tabular-nums">{at.length}</div>
              <div className="text-xs text-stone-500">{label(s)}</div>
              <div className={`mt-0.5 text-[11px] ${nStuck ? "text-rose-700" : "text-transparent"}`}>{nStuck} stuck</div>
            </button>
          );
        })}
      </div>

      <div className="overflow-x-auto rounded-xl border bg-white">
        <table className="w-full text-sm">
          <thead className="border-b text-left text-stone-500"><tr>
            {th("name", "Name", true)}{th("depot", "Depot")}{th("stage", "Stage")}{th("status", "Status")}{th("days", "Days in stage")}{th("contact", "Last contact")}<th className="pr-3">Lang</th>
          </tr></thead>
          <tbody className="divide-y">
            {rows.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-stone-500">No candidates match.</td></tr>}
            {rows.map((c) => {
              const flag = flags.find((f) => f.candidate_id === c.id);
              return (
                <tr key={c.id} className={stuck(c) ? "bg-rose-50/70" : "hover:bg-stone-50"}>
                  <td className="px-4 py-2"><Link className="font-medium text-emerald-900 hover:underline" to={`/candidates/${c.id}`}>{c.first_name} {c.last_name}</Link></td>
                  <td className="pr-3 text-stone-600">{depotName(c.depot_id)}</td>
                  <td className="pr-3">{label(c.stage === "cdl_permit" ? "training" : c.stage)}</td>
                  <td className="pr-3"><StatusPill status={c.status} />{flag && <span title={flag.note} className="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-900">FYI</span>}</td>
                  <td className={`pr-3 tabular-nums ${stuck(c) ? "font-semibold text-rose-700" : ""}`}>{daysSince(c.stage_entered_at)}{stuck(c) ? " ⚠" : ""}</td>
                  <td className="pr-3 text-stone-500">{c.last_contacted_at ? timeAgo(c.last_contacted_at) : "—"}</td>
                  <td className="pr-3 uppercase text-stone-500">{c.preferred_language}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-stone-500">
          <span>{sorted.length.toLocaleString()} candidate{sorted.length === 1 ? "" : "s"}{sorted.length > PAGE ? ` · showing ${page * PAGE + 1}–${Math.min((page + 1) * PAGE, sorted.length)}` : ""}</span>
          {pages > 1 && <span className="flex items-center gap-2">
            <button disabled={page === 0} className="rounded border px-2 py-0.5 disabled:opacity-40" onClick={() => setPage(page - 1)}>← Prev</button>
            <span>Page {page + 1} of {pages}</span>
            <button disabled={page >= pages - 1} className="rounded border px-2 py-0.5 disabled:opacity-40" onClick={() => setPage(page + 1)}>Next →</button>
          </span>}
        </div>
      </div>
    </div>
  );
}
