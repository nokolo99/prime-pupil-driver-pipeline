import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, asDate, label, STAGES, type Candidate, type Event, type Message, type Task } from "../api";
import { StatusPill, TaskActions } from "../components";

type Detail = {
  candidate: Candidate; messages: Message[]; events: Event[]; tasks: Task[];
  screening: Record<string, unknown> | null;
};

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
                <div className={`inline-block rounded-2xl px-3 py-2 text-left text-sm ${m.direction === "in" ? "bg-stone-200" : "bg-emerald-700 text-white"}`}>{m.body}</div>
                {m.translation_en && <div className="mt-0.5 text-xs italic text-stone-500">EN: {m.translation_en}</div>}
                <div className="text-[10px] text-stone-400">{m.direction === "in" ? "Candidate" : label(m.sender)} · {asDate(m.created_at).toLocaleTimeString()}</div>
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

          <section>
            <h3 className="mb-2 font-semibold">Timeline</h3>
            <ol className="space-y-1 rounded-lg border bg-white p-3 text-sm">
              {d.events.map((e) => (
                <li key={e.id} className="flex gap-2">
                  <span className="w-20 shrink-0 text-xs text-stone-400">{asDate(e.created_at).toLocaleTimeString()}</span>
                  <span className={`w-16 shrink-0 text-xs uppercase ${e.actor === "recruiter" ? "text-sky-700" : "text-stone-500"}`}>{e.actor}</span>
                  <span>{label(e.type)}{e.type === "nudge_sent" ? ` #${e.details.attempt} (day ${e.details.day}, ${e.details.kind})` : ""}{e.type === "workday_synced" ? `: ${e.details.decision}` : ""}{e.type === "stage_changed" ? `: ${label(String(e.details.to))}` : ""}{e.type === "screening_answer" ? `: ${Object.entries(e.details.answers as object).map(([k, v]) => `${k}=${v}`).join(", ")}` : ""}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>
    </div>
  );
}
