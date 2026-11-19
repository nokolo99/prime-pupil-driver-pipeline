import { useEffect, useRef, useState } from "react";
import { api, type Lookups, type Message } from "../api";

// Demo control panel: drives the story. Not part of the recruiter product.
export default function Demo() {
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  const [form, setForm] = useState({ first_name: "María", last_name: "González", phone: "+15550001111", depot_id: 1, language: "es", sms_consent: true });
  const [phone, setPhone] = useState("+15550001111");
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const end = useRef<HTMLDivElement>(null);

  const [outbox, setOutbox] = useState<{ id: number; workday_id: string | null; action: string; payload: Record<string, unknown> }[]>([]);
  useEffect(() => { api<Lookups>("/lookups").then(setLk); }, []);
  useEffect(() => {
    const load = () => { api<typeof outbox>("/demo/workday-outbox").then(setOutbox); };
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  async function skip(days: number) {
    setNote(`Skipping ahead ${days} day(s)…`);
    const r = await api<{ offset_days: number; actions: number }>("/demo/clock/advance", { method: "POST", body: JSON.stringify({ days }) });
    setNote(`Simulated time is now +${r.offset_days} days. The engine took ${r.actions} action(s).`);
  }
  const [voice, setVoice] = useState<{ ready: boolean } | null>(null);
  useEffect(() => {
    const load = () => { api<{ ready: boolean }>("/demo/voice-status").then(setVoice).catch(() => setVoice({ ready: false })); };
    load();
    const t = setInterval(load, 5000);
    return () => clearInterval(t);
  }, []);
  async function callNow() {
    try { await api("/demo/call", { method: "POST", body: JSON.stringify({ phone }) }); setNote(`Calling ${phone}… answer your phone!`); }
    catch (e) { setNote(String(e)); }
  }

  async function resetClock() { await api("/demo/clock/reset", { method: "POST" }); setNote("Clock reset to real time."); }
  useEffect(() => {
    const load = () => api<Message[]>(`/sim/messages?phone=${encodeURIComponent(phone)}`).then(setMsgs);
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [phone]);
  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs.length]);

  async function apply() {
    const workday_id = `WD-${Math.floor(1000 + Math.random() * 9000)}`;
    const r = await api<{ candidate_id: number }>("/integrations/workday/applicant", { method: "POST", body: JSON.stringify({ ...form, workday_id }) });
    setPhone(form.phone);
    setNote(`Workday applicant ${workday_id} received → candidate #${r.candidate_id}`);
  }

  async function send() {
    if (!text.trim() || busy) return;
    const body = text; setText(""); setBusy(true);
    try { await api("/sim/inbound", { method: "POST", body: JSON.stringify({ phone, body }) }); }
    catch (e) { setNote(String(e)); }
    finally { setBusy(false); }
  }

  const input = "w-full rounded border px-2 py-1 text-sm";
  return (
    <div className="grid gap-8 md:grid-cols-2">
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Simulate: new Workday applicant</h2>
        <p className="text-sm text-stone-500">Stands in for Workday Recruiting sending us a new application from the career page.</p>
        <div className="grid grid-cols-2 gap-2 rounded-lg border bg-white p-3">
          <input className={input} placeholder="First name" value={form.first_name} onChange={(e) => setForm({ ...form, first_name: e.target.value })} />
          <input className={input} placeholder="Last name" value={form.last_name} onChange={(e) => setForm({ ...form, last_name: e.target.value })} />
          <input className={`${input} col-span-2`} placeholder="Mobile phone" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <select className={input} value={form.depot_id} onChange={(e) => setForm({ ...form, depot_id: Number(e.target.value) })}>
            {lk.depots.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.city})</option>)}
          </select>
          <select className={input} value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })}>
            <option value="en">English</option><option value="es">Español</option><option value="other">Other</option>
          </select>
          <label className="col-span-2 flex items-center gap-2 text-xs text-stone-600">
            <input type="checkbox" checked={form.sms_consent} onChange={(e) => setForm({ ...form, sms_consent: e.target.checked })} />
            Candidate agreed to receive texts about their application
          </label>
          <button className="col-span-2 rounded bg-emerald-800 py-1.5 text-sm text-white" onClick={apply}>Submit application</button>
        </div>
        {note && <p className="text-xs text-stone-600">{note}</p>}

        <h2 className="pt-4 text-lg font-semibold">Simulate: time passing</h2>
        <p className="text-sm text-stone-500">Moves the system clock forward so follow-ups fire as if days went by.</p>
        <div className="flex flex-wrap gap-2">
          {[1, 3, 7, 30, 90].map((d) => <button key={d} className="rounded border bg-white px-3 py-1 text-sm hover:bg-stone-100" onClick={() => skip(d)}>+{d} day{d > 1 ? "s" : ""}</button>)}
          <button className="rounded px-3 py-1 text-sm text-stone-500 hover:underline" onClick={resetClock}>Reset clock</button>
        </div>

        <h2 className="pt-4 text-lg font-semibold">Workday: what we sent</h2>
        <p className="text-sm text-stone-500">Mock outbound connector. In production, these are Workday API calls.</p>
        <div className="max-h-48 divide-y overflow-y-auto rounded-lg border bg-white text-xs">
          {outbox.length === 0 && <p className="p-3 text-stone-500">Nothing sent yet.</p>}
          {outbox.map((o) => <div key={o.id} className="p-2 font-mono">{o.workday_id ?? "—"} · {o.action} · {JSON.stringify(o.payload)}</div>)}
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-lg font-semibold">Candidate's phone</h2>
        <div className="mb-2 flex gap-2">
          <input className={input} value={phone} onChange={(e) => setPhone(e.target.value)} />
          <button title="AI calls this number now"
            className="whitespace-nowrap rounded bg-sky-700 px-3 text-sm text-white hover:bg-sky-800" onClick={callNow}>📞 Call me now</button>
        </div>
        <p className="mb-1 text-xs">{voice?.ready ? <span className="text-emerald-700">● Voice ready</span> : <span className="text-rose-700">● Voice not connected (backend or tunnel down)</span>}</p>
        <p className="mb-2 text-xs text-stone-500">Texts appear below. Voice calls go to the real phone number; their transcript shows here and on the candidate page.</p>
        <div className="mx-auto w-80 rounded-[2rem] border-8 border-stone-800 bg-white">
          <div className="h-[28rem] space-y-2 overflow-y-auto p-3">
            {msgs.map((m) => (
              <div key={m.id} className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${m.direction === "in" ? "ml-auto bg-sky-500 text-white" : "bg-stone-200"}`}>{m.channel === "voice" ? "📞 " : ""}{m.body}</div>
            ))}
            {busy && <div className="w-12 rounded-2xl bg-stone-200 px-3 py-2 text-sm text-stone-500">…</div>}
            <div ref={end} />
          </div>
          <div className="flex gap-1 border-t p-2">
            <input className="flex-1 rounded-full border px-3 py-1 text-sm" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Text message" />
            <button className="rounded-full bg-sky-500 px-3 text-sm text-white" onClick={send}>↑</button>
          </div>
        </div>
      </section>
    </div>
  );
}
