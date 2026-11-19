import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, label, timeAgo, type Candidate, type Event, type Task } from "../api";

export default function Today() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [cands, setCands] = useState<Candidate[]>([]);

  useEffect(() => {
    const load = () => {
      api<Task[]>("/tasks").then(setTasks);
      api<Event[]>("/events?limit=500").then(setEvents);
      api<Candidate[]>("/candidates").then(setCands);
    };
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  const name = (id: number) => { const c = cands.find((x) => x.id === id); return c ? `${c.first_name} ${c.last_name}` : `#${id}`; };
  const stage = (id: number) => label(cands.find((x) => x.id === id)?.stage ?? "");
  const auto = events.filter((e) => e.actor === "system" || e.actor === "ai");
  const count = (t: string) => auto.filter((e) => e.type === t).length;

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-2 text-lg font-semibold">Needs you today ({tasks.length})</h2>
        <div className="divide-y rounded-lg border bg-white">
          {tasks.length === 0 && <p className="p-4 text-sm text-stone-500">Nothing needs you right now.</p>}
          {tasks.map((t) => (
            <Link key={t.id} to={`/candidates/${t.candidate_id}`} className="flex items-center gap-3 p-3 text-sm hover:bg-stone-50">
              <span className={`h-2 w-2 rounded-full ${t.priority === 1 ? "bg-rose-500" : t.priority === 2 ? "bg-amber-500" : "bg-stone-400"}`} />
              <span className="w-40 font-medium">{name(t.candidate_id)}</span>
              <span className="w-32 text-stone-500">{stage(t.candidate_id)}</span>
              <span className="flex-1">{t.reason}</span>
              <span className="text-xs text-stone-400">{timeAgo(t.created_at)}</span>
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Handled for you</h2>
        <div className="rounded-lg border bg-white p-4 text-sm">
          <div className="mb-3 flex flex-wrap gap-6">
            <div><span className="text-2xl font-semibold">{count("message_sent")}</span> <span className="text-stone-500">messages sent</span></div>
            <div><span className="text-2xl font-semibold">{count("screening_answer")}</span> <span className="text-stone-500">answers recorded</span></div>
            <div><span className="text-2xl font-semibold">{count("stage_changed")}</span> <span className="text-stone-500">candidates moved forward</span></div>
          </div>
          <details>
            <summary className="cursor-pointer text-stone-500">Show log</summary>
            <ol className="mt-2 max-h-72 space-y-1 overflow-y-auto">
              {auto.map((e) => (
                <li key={e.id} className="flex gap-2"><span className="w-16 text-xs text-stone-400">{timeAgo(e.created_at)}</span><span className="w-40">{name(e.candidate_id)}</span><span>{label(e.type)}</span></li>
              ))}
            </ol>
          </details>
        </div>
      </section>
    </div>
  );
}
