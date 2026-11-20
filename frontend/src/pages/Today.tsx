import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ACTOR_LABEL, api, eventLabel, HIDDEN_EVENTS, label, timeAgo, type Candidate, type Event, type Lookups, type Task } from "../api";
import { TaskActions } from "../components";

const PRIORITY = { 1: { dot: "bg-rose-500", text: "Urgent" }, 2: { dot: "bg-amber-500", text: "Soon" }, 3: { dot: "bg-stone-400", text: "FYI" } } as const;

export default function Today() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [cands, setCands] = useState<Candidate[]>([]);
  const [flags, setFlags] = useState<{ candidate_id: number; stage: string; note: string }[]>([]);
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  // "My queue": each recruiter sees their own tasks (remembered per browser).
  const [me, setMe] = useState<string>(() => { try { return localStorage.getItem("pp_me") ?? ""; } catch { return ""; } });
  const chooseMe = (v: string) => { setMe(v); try { localStorage.setItem("pp_me", v); } catch { /* ignore */ } };

  const load = () => {
    api<Task[]>("/tasks").then(setTasks);
    api<Event[]>("/events?limit=500").then(setEvents);
    api<Candidate[]>("/candidates").then(setCands);
    api<typeof flags>("/flags").then(setFlags);
  };
  useEffect(() => { api<Lookups>("/lookups").then(setLk); load(); const t = setInterval(load, 3000); return () => clearInterval(t); }, []);

  const byId = new Map(cands.map((c) => [c.id, c]));
  const name = (id: number) => { const c = byId.get(id); return c ? `${c.first_name} ${c.last_name}` : `#${id}`; };
  const mine = (candidateId: number) => !me || String(byId.get(candidateId)?.recruiter_id ?? "") === me;
  const myTasks = tasks.filter((t) => mine(t.candidate_id));
  const myFlags = flags.filter((f) => mine(f.candidate_id));
  const auto = events.filter((e) => (e.actor === "system" || e.actor === "ai" || e.actor === "vendor") && !HIDDEN_EVENTS.has(e.type) && mine(e.candidate_id));
  const count = (...types: string[]) => auto.filter((e) => types.includes(e.type)).length;
  const myName = lk.recruiters.find((r) => String(r.id) === me)?.name;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-semibold">{myName ? `Good to see you, ${myName.split(" ")[0]}` : "Today"}</h2>
          <p className="text-sm text-stone-500">{myTasks.length ? `${myTasks.length} candidate${myTasks.length === 1 ? "" : "s"} need a person. Everything else is being handled.` : "Nothing needs you right now. The system is handling follow-ups."}</p>
        </div>
        <label className="text-sm text-stone-600">Queue for{" "}
          <select className="rounded-lg border bg-white px-2 py-1 text-sm" value={me} onChange={(e) => chooseMe(e.target.value)}>
            <option value="">All recruiters</option>
            {lk.recruiters.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </select>
        </label>
      </div>

      <section>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-stone-500">Needs you ({myTasks.length})</h3>
        <div className="divide-y overflow-hidden rounded-xl border bg-white">
          {myTasks.length === 0 && <p className="p-6 text-center text-sm text-stone-500">All clear 🎉 You'll see candidates here only when a person is needed.</p>}
          {myTasks.map((t) => {
            const c = byId.get(t.candidate_id);
            const pr = PRIORITY[(t.priority as 1 | 2 | 3) ?? 2] ?? PRIORITY[2];
            return (
              <div key={t.id} className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-stone-50">
                <span title={pr.text} className={`h-2.5 w-2.5 shrink-0 rounded-full ${pr.dot}`} />
                <Link to={`/candidates/${t.candidate_id}`} className="w-44 shrink-0">
                  <div className="font-medium text-stone-900 hover:underline">{name(t.candidate_id)}</div>
                  <div className="text-xs text-stone-500">{c ? label(c.stage) : ""}</div>
                </Link>
                <div className="min-w-[12rem] flex-1 text-sm text-stone-700">{t.reason}</div>
                <TaskActions task={t} onDone={load} />
                <span className="w-16 text-right text-xs text-stone-400">{timeAgo(t.created_at)}</span>
              </div>
            );
          })}
        </div>
      </section>

      {myFlags.length > 0 && <section>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-stone-500">FYI <span className="normal-case tracking-normal text-stone-400">(no action needed)</span></h3>
        <div className="divide-y overflow-hidden rounded-xl border border-amber-200 bg-amber-50">
          {myFlags.map((f) => (
            <Link key={`${f.candidate_id}-${f.stage}`} to={`/candidates/${f.candidate_id}`} className="flex flex-wrap gap-3 px-4 py-2.5 text-sm hover:bg-amber-100">
              <span className="w-44 font-medium">{name(f.candidate_id)}</span><span className="w-32 text-stone-600">{label(f.stage)}</span><span>{f.note}</span>
            </Link>
          ))}
        </div>
      </section>}

      <section>
        <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-stone-500">Handled for you</h3>
        <div className="rounded-xl border bg-white p-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            {[[count("nudge_sent", "ai_call_placed"), "follow-ups sent"], [count("screening_answer"), "answers recorded"],
              [count("bg_result_received", "drug_test_result", "skills_test_result"), "results processed"], [count("stage_changed"), "candidates moved forward"]].map(([n, l]) => (
              <div key={String(l)}><div className="text-2xl font-semibold tabular-nums">{n}</div><div className="text-xs text-stone-500">{l}</div></div>
            ))}
          </div>
          <details className="mt-3">
            <summary className="cursor-pointer text-sm text-stone-500">Show activity log</summary>
            <ol className="mt-2 max-h-80 divide-y overflow-y-auto text-sm">
              {auto.slice(0, 150).map((e) => (
                <li key={e.id} className="flex gap-3 py-1.5">
                  <span className="w-16 shrink-0 text-xs text-stone-400">{timeAgo(e.created_at)}</span>
                  <Link to={`/candidates/${e.candidate_id}`} className="w-40 shrink-0 truncate hover:underline">{name(e.candidate_id)}</Link>
                  <span className="w-14 shrink-0 text-xs uppercase text-stone-400">{ACTOR_LABEL[e.actor] ?? e.actor}</span>
                  <span className="text-stone-700">{eventLabel(e)}</span>
                </li>
              ))}
            </ol>
          </details>
        </div>
      </section>
    </div>
  );
}
