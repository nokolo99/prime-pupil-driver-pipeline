import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ACTOR_LABEL, api, asDate, eventLabel, HIDDEN_EVENTS, label, STAGES, timeAgo, type Candidate, type Event, type Lookups, type Message, type Task } from "../api";
import { Linkify, StatusPill, TaskActions } from "../components";

type Permit = { image_path: string | null; extracted: Record<string, string | boolean | null>; mismatches: string[]; received_at: string | null;
                verified_at: string | null; self_reported_at: string | null; photo_requested_at: string | null };
type Detail = {
  candidate: Candidate & { preferred_channel?: string; drop_reason?: string | null };
  messages: Message[]; events: Event[]; tasks: Task[];
  screening: Record<string, unknown> | null;
  steps: { stage: string; flag_note: string | null; nudge_count: number }[];
  background_check: Record<string, string | null> | null;
  drug_test: Record<string, string | number | null> | null;
  later: { permit?: Permit; training?: { cohort_start: string; completed_at: string | null };
           skills_test?: { test_id: string; attempts: number; result: string | null; score: number | null };
           offer?: { offer_id: string; terms: Record<string, string>; signed_at: string | null; declined_at: string | null } };
};

const MAIN_STAGES = STAGES.filter((s) => s !== "application" && s !== "cdl_permit");
const SCREENING_LABELS: Record<string, string> = { is_21_plus: "21 or older", years_licensed: "Years licensed", dui_past_7_years: "DUI in lookback period", willing_drug_test: "Willing to take a drug test" };
const fmt = (v: unknown) => (v === null || v === undefined || v === "" ? "—" : v === true ? "Yes" : v === false ? "No" : String(v));
const when = (iso?: string | null) => (iso ? asDate(iso).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : null);

function Rows({ rows }: { rows: [string, unknown][] }) {
  return <div className="divide-y text-sm">{rows.map(([k, v]) => (
    <div key={k} className="flex justify-between gap-4 py-1.5"><span className="text-stone-500">{k}</span><span className="text-right font-medium">{fmt(v)}</span></div>
  ))}</div>;
}

function permitStatus(p?: Permit): { text: string; tone: string } {
  if (!p) return { text: "Starts with training", tone: "bg-stone-100 text-stone-500" };
  if (p.verified_at) return { text: "Verified ✓", tone: "bg-emerald-100 text-emerald-800" };
  if (p.image_path) return { text: "Photo received, verify", tone: "bg-rose-100 text-rose-800" };
  if (p.photo_requested_at) return { text: "Photo requested", tone: "bg-amber-100 text-amber-800" };
  if (p.self_reported_at) return { text: "Says they have it", tone: "bg-sky-100 text-sky-800" };
  return { text: "Not yet (reminders on)", tone: "bg-stone-100 text-stone-600" };
}

export default function CandidateDetail() {
  const { id } = useParams();
  const [d, setD] = useState<Detail | null>(null);
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  const [tab, setTab] = useState<string>("");
  const load = () => api<Detail>(`/candidates/${id}`).then(setD);
  useEffect(() => { api<Lookups>("/lookups").then(setLk); }, []);
  useEffect(() => { load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!d) return <p className="text-stone-500">Loading…</p>;

  const c = d.candidate;
  const idx = MAIN_STAGES.indexOf(c.stage === "cdl_permit" ? "training" : c.stage);
  const lost = c.status === "dropped" || c.status === "rejected";
  const openTasks = d.tasks.filter((t) => t.status === "open");
  const p = d.later.permit;
  const ps = permitStatus(p);
  const depot = lk.depots.find((x) => x.id === c.depot_id);
  const recruiter = lk.recruiters.find((x) => x.id === c.recruiter_id);
  const timeline = d.events.filter((e) => !HIDDEN_EVENTS.has(e.type)).slice().reverse();
  const flags = (d.screening?.knockout_flags as string[] | undefined) ?? [];

  const tabs: [string, string, React.ReactNode][] = [];
  if (d.screening) tabs.push(["screening", "Screening", <>
    <Rows rows={Object.entries(SCREENING_LABELS).map(([k, l]) => [l, d.screening?.[k]])} />
    {flags.length > 0 && <p className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">Flags: {flags.join("; ")}</p>}
  </>]);
  if (d.background_check) tabs.push(["bg", "Background check", <Rows rows={[["Vendor order", d.background_check.vendor_order_id],
    ["Form submitted", when(d.background_check.form_completed_at) ?? "Not yet"], ["Status", label(d.background_check.report_status ?? "")], ["Findings", d.background_check.flags]]} />]);
  if (d.drug_test) tabs.push(["drug", "Drug test", <Rows rows={[["Vendor case", d.drug_test.vendor_case_id], ["Clinic", d.drug_test.clinic_name],
    ["Appointment", when(d.drug_test.appointment_at as string) ?? "Not booked"], ["Missed appointments", d.drug_test.no_show_count],
    ["Sample collected", when(d.drug_test.collected_at as string) ?? "Not yet"], ["Result", d.drug_test.result ? label(String(d.drug_test.result)) : null]]} />]);
  if (p) tabs.push(["permit", "CDL permit", <>
    {p.image_path && <a href={`/api/sim/media/${p.image_path}`} target="_blank" rel="noreferrer"><img src={`/api/sim/media/${p.image_path}`} className="mb-2 max-h-44 w-full rounded-lg border object-contain" /></a>}
    {p.image_path && (p.mismatches.length ? <p className="mb-2 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">⚠ {p.mismatches.join("; ")}</p>
      : <p className="mb-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800">✓ Details on the photo match the candidate</p>)}
    <Rows rows={[["Says they have it", when(p.self_reported_at) ?? "Not yet"], ["Photo requested (before offer)", when(p.photo_requested_at)],
      ["Name on permit", p.extracted?.name], ["Permit #", p.extracted?.permit_number], ["Class", p.extracted?.license_class], ["Expires", p.extracted?.expiration_date],
      ["Verified by recruiter", when(p.verified_at) ?? (p.image_path ? "Awaiting recruiter" : "—")]]} />
  </>]);
  if (d.later.training) tabs.push(["training", "Training", <>
    <Rows rows={[["Cohort starts", when(d.later.training.cohort_start)], ["Completed", when(d.later.training.completed_at) ?? "Not yet"]]} />
    {c.stage === "training" && <p className="mt-2 text-xs text-stone-500">Completion is picked up automatically from the trainer's <a className="underline" href="/training-roster">training roster</a>.</p>}
  </>]);
  if (d.later.skills_test) tabs.push(["skills", "Skills test", <Rows rows={[["Test", d.later.skills_test.test_id], ["Attempt", d.later.skills_test.attempts],
    ["Result", d.later.skills_test.result ? `${label(d.later.skills_test.result)} (${d.later.skills_test.score})` : null]]} />]);
  if (d.later.offer) tabs.push(["offer", "Offer", <Rows rows={[...Object.entries(d.later.offer.terms).map(([k, v]) => [label(k), v] as [string, unknown]),
    ["Status", d.later.offer.signed_at ? `Signed ${when(d.later.offer.signed_at)}` : d.later.offer.declined_at ? "Declined" : "Sent, awaiting signature"]]} />]);
  const active = tabs.find(([k]) => k === tab) ?? tabs[tabs.length - 1];

  return (
    <div className="space-y-4">
      <Link to="/pipeline" className="text-sm text-stone-500 hover:underline">← Pipeline</Link>

      {/* Header */}
      <section className="rounded-xl border bg-white p-5">
        <div className="flex flex-wrap items-start gap-4">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-100 text-lg font-semibold text-emerald-900">{c.first_name[0]}{c.last_name?.[0] ?? ""}</div>
          <div className="mr-auto">
            <div className="flex flex-wrap items-center gap-2"><h2 className="text-2xl font-semibold">{c.first_name} {c.last_name}</h2><StatusPill status={c.status} /></div>
            <div className="mt-1 text-sm text-stone-500">
              {c.phone} · {c.preferred_language === "es" ? "Spanish" : c.preferred_language === "en" ? "English" : c.preferred_language} · {c.preferred_channel === "whatsapp" ? "WhatsApp" : "SMS"}
              {depot && <> · {depot.name} depot</>}{recruiter && <> · Recruiter: {recruiter.name}</>}{c.workday_id && <> · Workday {c.workday_id}</>}
            </div>
            {lost && c.drop_reason && <div className="mt-1 text-sm text-stone-600">{label(c.status)}: {label(c.drop_reason)}</div>}
          </div>
          <div className="text-right text-xs text-stone-500">Applied {timeAgo(c.created_at)}<br />In {label(c.stage)} for {timeAgo(c.stage_entered_at).replace(" ago", "")}</div>
        </div>

        {/* Progress, with the CDL permit as a side track during training */}
        <div className="mt-5 flex flex-wrap items-center gap-1">
          {MAIN_STAGES.map((s, i) => (
            <div key={s} className="flex items-center gap-1">
              <span className={`rounded-full px-3 py-1 text-xs ${lost && i === idx ? "bg-stone-300 text-stone-700 line-through" : i < idx || c.stage === "hired" ? "bg-emerald-700 text-white" : i === idx ? "bg-emerald-100 font-semibold text-emerald-900 ring-1 ring-emerald-700" : "bg-stone-100 text-stone-400"}`}>{label(s)}</span>
              {s === "training" && <span title="The CDL permit runs alongside training and is verified before the offer" className={`rounded-full px-2 py-1 text-[11px] ${ps.tone}`}>Permit: {ps.text}</span>}
              {i < MAIN_STAGES.length - 1 && <span className="text-stone-300">›</span>}
            </div>
          ))}
        </div>
      </section>

      {/* Needs a person */}
      {openTasks.length > 0 && (
        <section className="space-y-2 rounded-xl border border-rose-200 bg-rose-50 p-4">
          <h3 className="text-sm font-semibold text-rose-900">Needs you</h3>
          {openTasks.map((t) => (
            <div key={t.id} className="flex flex-wrap items-center justify-between gap-2 text-sm"><span className="text-rose-900">{t.reason}</span><TaskActions task={t} onDone={load} /></div>
          ))}
        </section>
      )}
      {d.steps.filter((st) => st.flag_note).map((st) => (
        <div key={st.stage} className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900">FYI · {label(st.stage)}: {st.flag_note}</div>
      ))}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Conversation */}
        <section className="rounded-xl border bg-white p-4">
          <h3 className="mb-3 font-semibold">Conversation <span className="text-xs font-normal text-stone-500">· texts, WhatsApp and calls in one thread</span></h3>
          <div className="max-h-[36rem] space-y-2 overflow-y-auto pr-1">
            {d.messages.length === 0 && <p className="text-sm text-stone-500">No messages yet.</p>}
            {d.messages.map((m) => (
              <div key={m.id} className={`max-w-[85%] ${m.direction === "in" ? "" : "ml-auto text-right"}`}>
                <div className={`inline-block rounded-2xl px-3 py-2 text-left text-sm ${m.direction === "in" ? "bg-stone-100" : "bg-emerald-700 text-white"}`}><Linkify text={m.body} /></div>
                {m.translation_en && <div className="mt-0.5 text-xs italic text-stone-500">EN: {m.translation_en}</div>}
                <div className="text-[10px] text-stone-400">{m.channel === "voice" ? "📞 Call" : m.channel === "whatsapp" ? "WhatsApp" : m.channel === "sms" ? "SMS" : "Web"} · {m.direction === "in" ? "Candidate" : label(m.sender)} · {asDate(m.created_at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</div>
              </div>
            ))}
          </div>
        </section>

        <div className="space-y-4">
          {/* Step details */}
          {tabs.length > 0 && active && (
            <section className="rounded-xl border bg-white p-4">
              <div className="mb-3 flex flex-wrap gap-1 border-b pb-2">
                {tabs.map(([k, l]) => (
                  <button key={k} onClick={() => setTab(k)} className={`rounded-lg px-2.5 py-1 text-sm ${active[0] === k ? "bg-emerald-50 font-medium text-emerald-900" : "text-stone-500 hover:bg-stone-50"}`}>{l}</button>
                ))}
              </div>
              {active[2]}
            </section>
          )}

          {/* Timeline */}
          <section className="rounded-xl border bg-white p-4">
            <h3 className="mb-2 font-semibold">Timeline <span className="text-xs font-normal text-stone-500">· newest first</span></h3>
            <ol className="max-h-[24rem] space-y-1.5 overflow-y-auto text-sm">
              {timeline.map((e) => (
                <li key={e.id} className="flex gap-2">
                  <span className="w-24 shrink-0 text-xs text-stone-400">{when(e.created_at)}</span>
                  <span className={`w-16 shrink-0 text-xs ${e.actor === "recruiter" ? "font-medium text-sky-700" : e.actor === "candidate" ? "text-emerald-700" : "text-stone-400"}`}>{ACTOR_LABEL[e.actor] ?? e.actor}</span>
                  <span className="text-stone-700">{eventLabel(e)}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}
