import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, asDate, label, STAGES, type Candidate, type Event, type Message, type Task } from "../api";
import { Linkify, StatusPill, TaskActions } from "../components";

type Detail = {
  candidate: Candidate; messages: Message[]; events: Event[]; tasks: Task[];
  screening: Record<string, unknown> | null;
  steps: { stage: string; flag_note: string | null; nudge_count: number }[];
  background_check: Record<string, string | null> | null;
  drug_test: Record<string, string | number | null> | null;
  later: {
    permit?: { image_path: string | null; extracted: Record<string, string | boolean | null>; mismatches: string[]; received_at: string | null; verified_at: string | null };
    training?: { cohort_start: string; completed_at: string | null; session_link: string };
    skills_test?: { test_id: string; attempts: number; result: string | null; score: number | null };
    offer?: { offer_id: string; terms: Record<string, string>; signed_at: string | null; declined_at: string | null };
  };
};
const Row = ({ k, v }: { k: string; v: unknown }) => (
  <div className="flex justify-between gap-4 border-b px-3 py-1.5 last:border-0"><span className="text-stone-500">{k}</span><span className="text-right font-medium">{v === null || v === undefined || v === "" ? "—" : String(v)}</span></div>
);

const SCREENING_LABELS: Record<string, string> = {
  is_21_plus: "21 or older", has_valid_license: "Valid license", years_licensed: "Years licensed",
  recent_violations: "Recent DUI / suspension / serious violation", availability_ok: "Split shift OK",
  has_cdl_or_permit: "Has CDL or permit",
};
const fmt = (v: unknown) => (v === null || v === undefined ? "—" : v === true ? "Yes" : v === false ? "No" : String(v));

export default function CandidateDetail() {
  const { id } = useParams();
  const [d, setD] = useState<Detail | null>(null);

  useEffect(() => {
    const load = () => api<Detail>(`/candidates/${id}`).then(setD);
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [id]);

  if (!d) return <p className="text-stone-500">Loading…</p>;
  const c = d.candidate;
  const idx = STAGES.indexOf(c.stage);
  const flags = (d.screening?.knockout_flags as string[] | undefined) ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">{c.first_name} {c.last_name}</h2>
        <StatusPill status={c.status} />
        <span className="text-sm text-stone-500">{c.phone} · {c.preferred_language.toUpperCase()}{c.workday_id ? ` · Workday ${c.workday_id}` : ""}</span>
      </div>

      <ol className="flex flex-wrap gap-1">
        {STAGES.map((s, i) => (
          <li key={s} className={`rounded px-2 py-1 text-xs ${i < idx ? "bg-emerald-700 text-white" : i === idx ? "bg-emerald-200 font-semibold text-emerald-900" : "bg-stone-200 text-stone-500"}`}>{label(s)}</li>
        ))}
      </ol>

      {d.tasks.filter((t) => t.status === "open").length > 0 && (
        <div className="space-y-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm">
          {d.tasks.filter((t) => t.status === "open").map((t) => (
            <div key={t.id} className="flex flex-wrap items-center justify-between gap-2"><span>⚑ {t.reason}</span><TaskActions task={t} onDone={() => api<Detail>(`/candidates/${id}`).then(setD)} /></div>
          ))}
        </div>
      )}
      {c.drop_reason && <div className="text-sm text-stone-600">{label(c.status)}: {label(c.drop_reason)}</div>}

      <div className="grid gap-5 lg:grid-cols-2">
        <section>
          <h3 className="mb-2 font-semibold">Conversation</h3>
          <div className="max-h-[32rem] space-y-2 overflow-y-auto rounded-lg border bg-white p-3">
            {d.messages.map((m) => (
              <div key={m.id} className={`max-w-[85%] ${m.direction === "in" ? "" : "ml-auto text-right"}`}>
                <div className={`inline-block rounded-2xl px-3 py-2 text-left text-sm ${m.direction === "in" ? "bg-stone-200" : "bg-emerald-700 text-white"}`}><Linkify text={m.body} /></div>
                {m.translation_en && <div className="mt-0.5 text-xs italic text-stone-500">EN: {m.translation_en}</div>}
                <div className="text-[10px] text-stone-400">{m.channel === "voice" ? "📞 Call · " : ""}{m.direction === "in" ? "Candidate" : label(m.sender)} · {asDate(m.created_at).toLocaleTimeString()}</div>
              </div>
            ))}
          </div>
        </section>

        <div className="space-y-5">
          <section>
            <h3 className="mb-2 font-semibold">Screening answers</h3>
            <div className="rounded-lg border bg-white text-sm">
              {Object.entries(SCREENING_LABELS).map(([k, l]) => (
                <div key={k} className="flex justify-between border-b px-3 py-1.5 last:border-0">
                  <span className="text-stone-500">{l}</span><span className="font-medium">{fmt(d.screening?.[k])}</span>
                </div>
              ))}
              {flags.length > 0 && <div className="bg-rose-50 px-3 py-1.5 text-rose-800">Flags: {flags.join("; ")}</div>}
            </div>
          </section>

          {d.steps.filter((st) => st.flag_note).map((st) => (
            <div key={st.stage} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">FYI · {label(st.stage)}: {st.flag_note}</div>
          ))}

          {d.background_check && <section>
            <h3 className="mb-2 font-semibold">Background check</h3>
            <div className="rounded-lg border bg-white text-sm">
              {([["Vendor order", d.background_check.vendor_order_id], ["Form submitted", d.background_check.form_completed_at ? asDate(d.background_check.form_completed_at).toLocaleString() : "Not yet"],
                ["Status", label(d.background_check.report_status ?? "")], ["Findings", d.background_check.flags]] as [string, string | null][]).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 border-b px-3 py-1.5 last:border-0"><span className="text-stone-500">{k}</span><span className="text-right font-medium">{v ?? "—"}</span></div>
              ))}
            </div>
          </section>}

          {d.drug_test && <section>
            <h3 className="mb-2 font-semibold">Drug test</h3>
            <div className="rounded-lg border bg-white text-sm">
              {([["Vendor case", d.drug_test.vendor_case_id], ["Clinic", d.drug_test.clinic_name],
                ["Appointment", d.drug_test.appointment_at ? asDate(String(d.drug_test.appointment_at)).toLocaleString() : "Not booked"],
                ["Missed appointments", d.drug_test.no_show_count], ["Sample collected", d.drug_test.collected_at ? asDate(String(d.drug_test.collected_at)).toLocaleString() : "Not yet"],
                ["Result", d.drug_test.result ? label(String(d.drug_test.result)) : "—"]] as [string, string | number | null][]).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 border-b px-3 py-1.5 last:border-0"><span className="text-stone-500">{k}</span><span className="text-right font-medium">{v ?? "—"}</span></div>
              ))}
            </div>
          </section>}

          {d.later.permit && <section>
            <h3 className="mb-2 font-semibold">CDL permit</h3>
            <div className="rounded-lg border bg-white text-sm">
              {d.later.permit.image_path && <a href={`/api/sim/media/${d.later.permit.image_path}`} target="_blank" rel="noreferrer"><img src={`/api/sim/media/${d.later.permit.image_path}`} className="max-h-40 w-full object-contain p-2" /></a>}
              {d.later.permit.mismatches.length > 0
                ? <div className="bg-rose-50 px-3 py-1.5 text-rose-800">⚠ {d.later.permit.mismatches.join("; ")}</div>
                : d.later.permit.received_at && <div className="bg-emerald-50 px-3 py-1.5 text-emerald-800">✓ Details match the candidate</div>}
              <Row k="Name on permit" v={d.later.permit.extracted.name} /><Row k="Permit #" v={d.later.permit.extracted.permit_number} />
              <Row k="Class" v={d.later.permit.extracted.license_class} /><Row k="Expires" v={d.later.permit.extracted.expiration_date} />
              <Row k="Verified" v={d.later.permit.verified_at ? asDate(d.later.permit.verified_at).toLocaleString() : d.later.permit.received_at ? "Awaiting recruiter" : "No photo yet"} />
            </div>
          </section>}

          {d.later.training && <section>
            <h3 className="mb-2 font-semibold">Training</h3>
            <div className="rounded-lg border bg-white text-sm">
              <Row k="Cohort starts" v={asDate(d.later.training.cohort_start).toLocaleString()} />
              <Row k="Completed" v={d.later.training.completed_at ? asDate(d.later.training.completed_at).toLocaleString() : "Not yet"} />
              {c.stage === "training" && <div className="p-2"><button className="rounded border border-emerald-600 px-2 py-1 text-xs text-emerald-800 hover:bg-emerald-50"
                onClick={() => api(`/tasks/training/${c.id}/complete`, { method: "POST" }).then(() => api<Detail>(`/candidates/${id}`).then(setD))}>Mark training complete</button></div>}
            </div>
          </section>}

          {d.later.skills_test && <section>
            <h3 className="mb-2 font-semibold">Skills test</h3>
            <div className="rounded-lg border bg-white text-sm">
              <Row k="Test" v={d.later.skills_test.test_id} /><Row k="Attempt" v={d.later.skills_test.attempts} />
              <Row k="Result" v={d.later.skills_test.result ? `${label(d.later.skills_test.result)} (${d.later.skills_test.score})` : "—"} />
            </div>
          </section>}

          {d.later.offer && <section>
            <h3 className="mb-2 font-semibold">Offer</h3>
            <div className="rounded-lg border bg-white text-sm">
              {Object.entries(d.later.offer.terms).map(([k, v]) => <Row key={k} k={label(k)} v={v} />)}
              <Row k="Status" v={d.later.offer.signed_at ? `Signed ${asDate(d.later.offer.signed_at).toLocaleString()}` : d.later.offer.declined_at ? "Declined" : "Sent, awaiting signature"} />
            </div>
          </section>}

          <section>
            <h3 className="mb-2 font-semibold">Timeline</h3>
            <ol className="space-y-1 rounded-lg border bg-white p-3 text-sm">
              {d.events.map((e) => (
                <li key={e.id} className="flex gap-2">
                  <span className="w-20 shrink-0 text-xs text-stone-400">{asDate(e.created_at).toLocaleTimeString()}</span>
                  <span className={`w-16 shrink-0 text-xs uppercase ${e.actor === "recruiter" ? "text-sky-700" : "text-stone-500"}`}>{e.actor}</span>
                  <span>{label(e.type)}{e.type === "nudge_sent" ? ` #${e.details.attempt} (day ${e.details.day}, ${e.details.kind})` : ""}{e.type === "workday_synced" ? `: ${e.details.decision ?? e.details.stage}` : ""}{e.type === "bg_result_received" ? `: ${e.details.status}` : ""}{e.type === "drug_test_result" ? `: ${e.details.result}` : ""}{e.type === "stage_changed" ? `: ${label(String(e.details.to))}` : ""}{e.type === "screening_answer" ? `: ${Object.entries(e.details.answers as object).map(([k, v]) => `${k}=${v}`).join(", ")}` : ""}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}
