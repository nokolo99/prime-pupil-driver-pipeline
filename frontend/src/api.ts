// Thin wrapper around the backend JSON API.
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

export type Candidate = {
  id: number; first_name: string; last_name: string; phone: string;
  preferred_language: string; depot_id: number | null; recruiter_id: number | null;
  stage: string; status: string; stage_entered_at: string; last_contacted_at: string | null;
};
export type Task = { id: number; candidate_id: number; type: string; reason: string; priority: number };
export type Event = { id: number; candidate_id: number; type: string; actor: string; details: Record<string, unknown>; created_at: string };
