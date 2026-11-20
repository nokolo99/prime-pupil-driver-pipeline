// Demo password (remembered in this browser). Sent with every request; only demo endpoints check it.
export const demoKey = () => { try { return localStorage.getItem("pp_demo_key") ?? ""; } catch { return ""; } };
export const setDemoKey = (k: string) => { try { if (k) localStorage.setItem("pp_demo_key", k); else localStorage.removeItem("pp_demo_key"); } catch { /* ignore */ } };
export const demoHeaders = (): Record<string, string> => (demoKey() ? { "X-Demo-Key": demoKey() } : {});

// Thin wrapper around the backend JSON API.
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, { ...init, headers: { "Content-Type": "application/json", ...demoHeaders(), ...(init?.headers ?? {}) } });
  if (!res.ok) {
    const text = await res.text();
    let msg = text;
    try { const j = JSON.parse(text); msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return res.json();
}

export type Candidate = {
  id: number; first_name: string; last_name: string; phone: string;
  preferred_language: string; preferred_channel?: string; live_messages?: boolean; depot_id: number | null; recruiter_id: number | null;
  stage: string; status: string; stage_entered_at: string; last_contacted_at: string | null;
  last_reply_at: string | null; workday_id: string | null; created_at: string; drop_reason: string | null;
};
export type Task = { id: number; candidate_id: number; type: string; reason: string; priority: number; status: string; created_at: string; photo?: string | null; mismatches?: string[] };
export type Event = { id: number; candidate_id: number; type: string; actor: string; details: Record<string, unknown>; created_at: string };
export type Message = {
  id: number; direction: "in" | "out"; sender: string; body: string; channel: string;
  language: string | null; translation_en: string | null; created_at: string;
};
export type Depot = { id: number; name: string; city: string };
export type Recruiter = { id: number; name: string; depot_id: number };
export type Lookups = { depots: Depot[]; recruiters: Recruiter[] };

export const STAGES = ["application", "screening", "background_check", "drug_test", "cdl_permit", "training", "skills_test", "offer", "hired"];

export const label = (s: string) => s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()).replace(/\bCdl\b/i, "CDL");

// SQLite returns naive UTC timestamps; treat them as UTC.
export const asDate = (iso: string) => new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z");
export const daysSince = (iso: string) => Math.floor((Date.now() - asDate(iso).getTime()) / 86_400_000);
export const timeAgo = (iso: string) => {
  const m = Math.round((Date.now() - asDate(iso).getTime()) / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  if (m < 1440) return `${Math.round(m / 60)}h ago`;
  return `${Math.round(m / 1440)}d ago`;
};

export const STATUS_STYLE: Record<string, string> = {
  in_progress: "bg-sky-100 text-sky-800",
  waiting_on_candidate: "bg-amber-100 text-amber-800",
  waiting_on_vendor: "bg-violet-100 text-violet-800",
  needs_review: "bg-rose-100 text-rose-800",
  dropped: "bg-stone-200 text-stone-600",
  rejected: "bg-stone-200 text-stone-600",
  hired: "bg-emerald-100 text-emerald-800",
};

// ---------- Friendly event labels (timeline, Today log) ----------
// Plumbing events recruiters don't need to see.
export const HIDDEN_EVENTS = new Set(["sms_undelivered", "sms_failed", "message_sent", "caller_interrupted", "workday_note", "ai_call_placeholder"]);

const yesNo = (v: unknown) => (v === true ? "yes" : v === false ? "no" : String(v));
const ANSWER_LABELS: Record<string, string> = { is_21_plus: "21+", years_licensed: "years licensed", dui_past_7_years: "DUI recently", willing_drug_test: "will take drug test" };

export function eventLabel(e: Event): string {
  const d = e.details ?? {};
  switch (e.type) {
    case "applied": return "Applied (arrived from Workday)";
    case "screening_answer": return "Answer recorded: " + Object.entries((d.answers as Record<string, unknown>) ?? {}).map(([k, v]) => `${ANSWER_LABELS[k] ?? k} ${yesNo(v)}`).join(", ");
    case "screening_completed": return d.result === "pass" ? "Passed screening" : `Screening flagged: ${((d.flags as string[]) ?? []).join("; ")}`;
    case "answer_flagged_unclear": return "Unclear answer flagged for recruiter";
    case "stage_changed": return `Moved to ${label(String(d.to))}`;
    case "task_created": return `Flagged for recruiter: ${d.reason}`;
    case "task_dismissed": return "Recruiter dismissed a task";
    case "nudge_sent": return d.kind === "call" ? `AI follow-up call (day ${d.day})` : `Reminder text sent (day ${d.day})`;
    case "ai_call_placed": return "AI call placed";
    case "ai_call_failed": return "AI call couldn't be placed";
    case "call_answered": return "Answered the AI call";
    case "call_inbound": return "Called in";
    case "call_ended": return `Call ended${d.duration_s ? ` (${d.duration_s}s)` : ""}`;
    case "voicemail_left": return "Voicemail left";
    case "bg_ordered": return "Background check ordered";
    case "bg_form_completed": return "Background check form submitted";
    case "bg_result_received": return `Background check result: ${d.status === "clear" ? "clear" : "needs review"}`;
    case "results_overdue": return `Vendor results overdue (${d.days} days)`;
    case "drug_test_case_opened": return "Drug test authorization sent";
    case "drug_test_booked": return `Clinic appointment booked (${d.clinic})`;
    case "drug_visit_planned": return `Plans to walk in ${d.day}${d.time_of_day ? ` (${d.time_of_day})` : ""}${d.clinic ? ` at ${d.clinic}` : ""}`;
    case "drug_auth_signed": return "Signed drug test authorization";
    case "appointment_reminder": return d.kind === "morning_of" ? "Drug test reminder (morning of)" : "Drug test reminder (day before)";
    case "drug_test_no_show": return "Didn't make it in for the drug test";
    case "drug_test_collected": return "Drug test sample collected";
    case "drug_test_result": return `Drug test result: ${String(d.result).replace("_", "-")}`;
    case "training_enrolled": return "Enrolled in paid CDL training";
    case "training_reminder": return "Training reminder";
    case "training_sheet_completed_detected": return "Training completion picked up from trainer's roster";
    case "training_completed": return "Training complete";
    case "permit_track_started": return "CDL permit reminders started";
    case "permit_self_reported": return "Says they have their CDL permit";
    case "permit_photo_requested": return "Permit photo requested (before offer)";
    case "permit_photo_received": return "Permit photo received";
    case "permit_verified": return "Permit verified by recruiter";
    case "permit_new_photo_requested": return "New permit photo requested";
    case "skills_test_result": return `Skills test: ${d.result}${d.score ? ` (${d.score})` : ""}`;
    case "skills_retest_allowed": return "Retest allowed";
    case "offer_sent": return "Offer sent";
    case "offer_signed": return "Offer signed 🎉";
    case "offer_declined": return "Offer declined";
    case "recruiter_approved": return "Recruiter approved";
    case "recruiter_rejected": return `Recruiter rejected (${label(String(d.reason))})`;
    case "recruiter_marked_dropped": return `Marked dropped (${label(String(d.reason))})`;
    case "recruiter_extended_follow_up": return "Recruiter restarted follow-ups";
    case "workday_synced": return `Workday updated: ${d.next_step ?? d.disposition ?? (d.action === "Offer" ? "offer started" : d.action)}`;
    case "language_changed": return `Switched language to ${d.to === "es" ? "Spanish" : d.to === "en" ? "English" : String(d.to)}`;
    case "channel_changed": return `Switched to ${d.to === "whatsapp" ? "WhatsApp" : String(d.to)}`;
    case "opted_out": return "Opted out (STOP)";
    case "opted_in": return "Opted back in";
    case "candidate_claims_done": return "Says they finished the step (awaiting vendor confirmation)";
    case "demo_stage_forced": return `Demo: jumped to ${label(String(d.to))}`;
    case "ai_error": return "AI had trouble replying (sent a retry message)";
    default: return label(e.type);
  }
}

export const ACTOR_LABEL: Record<string, string> = { system: "System", ai: "AI", recruiter: "Recruiter", candidate: "Candidate", vendor: "Vendor" };
