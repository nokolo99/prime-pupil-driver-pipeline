import { useEffect, useState } from "react";
import { api, label, STATUS_STYLE, type Task } from "./api";

export function StatusPill({ status }: { status: string }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status] ?? "bg-stone-100"}`}>{label(status)}</span>;
}

export function ClockBanner() {
  const [days, setDays] = useState(0);
  useEffect(() => {
    const load = () => { api<{ offset_days: number }>("/demo/clock").then((c) => setDays(c.offset_days)); };
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);
  if (!days) return null;
  return <div className="bg-amber-100 py-1 text-center text-xs text-amber-900">Demo clock: simulated time is +{days} day{days === 1 ? "" : "s"}</div>;
}

const REJECT_REASONS = ["failed_knockout", "failed_background_check", "failed_drug_test", "other"];
const DROP_REASONS = ["no_response", "took_another_job", "withdrew", "other"];

// Buttons a recruiter can use on a task. Mirrors ALLOWED in backend routes/actions.py.
export function TaskActions({ task, onDone }: { task: Task; onDone: () => void }) {
  const [picking, setPicking] = useState<null | "reject" | "mark_dropped">(null);
  const [busy, setBusy] = useState(false);

  async function act(action: string, reason?: string) {
    setBusy(true);
    try { await api(`/tasks/${task.id}/action`, { method: "POST", body: JSON.stringify({ action, reason }) }); onDone(); }
    finally { setBusy(false); setPicking(null); }
  }
  const btn = "rounded border px-2 py-1 text-xs hover:bg-stone-100 disabled:opacity-50";

  if (picking) {
    const reasons = picking === "reject" ? REJECT_REASONS : DROP_REASONS;
    return (
      <div className="flex flex-wrap items-center gap-1" onClick={(e) => e.preventDefault()}>
        <span className="text-xs text-stone-500">Reason:</span>
        {reasons.map((r) => <button key={r} disabled={busy} className={btn} onClick={() => act(picking, r)}>{label(r)}</button>)}
        <button className={`${btn} border-transparent text-stone-400`} onClick={() => setPicking(null)}>Cancel</button>
      </div>
    );
  }
  return (
    <div className="flex gap-1" onClick={(e) => e.preventDefault()}>
      {["review_knockout", "review_background_flag", "review_drug_result"].includes(task.type) && <>
        <button disabled={busy} className={`${btn} border-emerald-600 text-emerald-800`} onClick={() => act("approve")}>Approve</button>
        <button disabled={busy} className={`${btn} border-rose-400 text-rose-700`} onClick={() => setPicking("reject")}>Reject</button>
      </>}
      {task.type === "candidate_unresponsive" && <>
        <button disabled={busy} className={btn} onClick={() => act("extend")}>Keep following up</button>
        <button disabled={busy} className={btn} onClick={() => setPicking("mark_dropped")}>Mark dropped</button>
      </>}
      {["candidate_withdrawing", "offer_declined"].includes(task.type) &&
        <button disabled={busy} className={btn} onClick={() => setPicking("mark_dropped")}>Mark dropped</button>}
      {task.type === "review_permit" && <>
        {task.photo && <a href={`/api/sim/media/${task.photo}`} target="_blank" rel="noreferrer" className={`${btn} inline-block`}>View photo ↗</a>}
        <button disabled={busy} className={`${btn} border-emerald-600 text-emerald-800`} onClick={() => act("verify_permit")}>Verify permit</button>
        <button disabled={busy} className={btn} onClick={() => act("request_new_photo")}>Request new photo</button>
      </>}
      {task.type === "review_skills_test" && <>
        <button disabled={busy} className={`${btn} border-emerald-600 text-emerald-800`} onClick={() => act("allow_retest")}>Allow retest</button>
        <button disabled={busy} className={`${btn} border-rose-400 text-rose-700`} onClick={() => setPicking("reject")}>Reject</button>
      </>}
      {!["review_knockout", "review_background_flag", "review_drug_result", "candidate_unresponsive", "candidate_withdrawing",
         "offer_declined", "review_permit", "review_skills_test"].includes(task.type) &&
        <button disabled={busy} className={btn} onClick={() => act("dismiss")}>Dismiss</button>}
    </div>
  );
}

// Turn URLs in message text into tappable links (vendor form / booking links).
export function Linkify({ text }: { text: string }) {
  const parts = text.split(/(https?:\/\/\S+)/g);
  return <>{parts.map((p, i) => /^https?:\/\//.test(p)
    ? <a key={i} href={p} target="_blank" rel="noreferrer" className="break-all underline">{p}</a>
    : <span key={i} className="whitespace-pre-line">{p}</span>)}</>;
}
