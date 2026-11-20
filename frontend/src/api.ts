// Thin wrapper around the backend JSON API.
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, { headers: { "Content-Type": "application/json" }, ...init });
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
  preferred_language: string; preferred_channel?: string; depot_id: number | null; recruiter_id: number | null;
  stage: string; status: string; stage_entered_at: string; last_contacted_at: string | null;
  last_reply_at: string | null; workday_id: string | null; created_at: string; drop_reason: string | null;
};
export type Task = { id: number; candidate_id: number; type: string; reason: string; priority: number; status: string; created_at: string };
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
