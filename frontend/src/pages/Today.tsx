import { useEffect, useState } from "react";
import { api, type Event, type Task } from "../api";

export default function Today() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  useEffect(() => {
    api<Task[]>("/tasks").then(setTasks);
    api<Event[]>("/events").then(setEvents);
  }, []);

  return (
    <div className="space-y-6">
      <section>
        <h2 className="text-lg font-semibold mb-2">Needs you today ({tasks.length})</h2>
        <div className="rounded-lg border bg-white divide-y">
          {tasks.length === 0 && <p className="p-4 text-stone-500 text-sm">Nothing needs you right now.</p>}
          {tasks.map((t) => (
            <div key={t.id} className="p-4 text-sm">{t.reason}</div>
          ))}
        </div>
      </section>
      <section>
        <h2 className="text-lg font-semibold mb-2">Handled for you</h2>
        <div className="rounded-lg border bg-white p-4 text-sm text-stone-500">
          {events.filter((e) => e.actor === "system" || e.actor === "ai").length} actions taken by the system.
        </div>
      </section>
    </div>
  );
}
