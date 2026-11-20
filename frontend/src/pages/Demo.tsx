import { useEffect, useRef, useState } from "react";
import { api, label, STAGES, type Lookups, type Message } from "../api";
import { Linkify } from "../components";

// Demo control panel: drives the story. Not part of the recruiter product.
export default function Demo() {
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  const [form, setForm] = useState({ first_name: "Maria", last_name: "Gonzalez", phone: "+15550001111", depot_id: 1, language: "en", sms_consent: true, channel: "whatsapp" });
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
    catch (e) { setNote(`⚠ ${(e as Error).message}`); }
  }

  const [forceTo, setForceTo] = useState("screening");
  async function restartCandidate() {
    if (!confirm(`Restart ${phone} from scratch? Their conversation and progress will be cleared.`)) return;
    try { await api("/demo/candidate/restart", { method: "POST", body: JSON.stringify({ phone }) }); setNote(`Restarted ${phone}: intro re-sent.`); }
    catch (e) { setNote(`⚠ ${(e as Error).message}`); }
  }
  async function forceStage() {
    try { await api("/demo/candidate/stage", { method: "POST", body: JSON.stringify({ phone, stage: forceTo }) }); setNote(`${phone} moved to ${label(forceTo)}.`); }
    catch (e) { setNote(`⚠ ${(e as Error).message}`); }
  }

  type Email = { from: string; subject: string; body: string };
  type VCtx = { stage: string; status: string;
    bg: null | { order_id: string; form_link: string; form_completed: boolean; report_status: string; email_clear: Email; email_flagged: Email };
    drug: null | { case_id: string; booking_link: string; appointment_at: string | null; collected: boolean; result: string | null };
    skills?: { test_id: string; link: string; result: string | null; attempts: number };
    offer?: { offer_id: string; link: string; signed: boolean; declined: boolean };
    candidate_id?: number };
  const [vctx, setVctx] = useState<VCtx | null>(null);
  const [email, setEmail] = useState<Email | null>(null);
  useEffect(() => {
    const load = () => { api<VCtx>(`/demo/vendor-context?phone=${encodeURIComponent(phone)}`).then(setVctx).catch(() => setVctx(null)); };
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [phone]);
  async function sendEmail(e: Email) {
    setNote("Vendor email received. Claude is reading it…");
    try {
      const r = await api<{ processed: boolean; parsed: { status: string; summary: string } }>("/integrations/bg-vendor/email", { method: "POST", body: JSON.stringify({ sender: e.from, subject: e.subject, body: e.body }) });
      setNote(r.processed ? `Email read: ${r.parsed.status.toUpperCase()}. ${r.parsed.summary}` : "Couldn't match/read the email → sent to a recruiter.");
      setEmail(null);
    } catch (err) { setNote(`⚠ ${(err as Error).message}`); }
  }
  async function drugEvent(event: string, result?: string) {
    if (!vctx?.drug) return;
    try { await api("/integrations/drug-vendor/webhook", { method: "POST", body: JSON.stringify({ case_id: vctx.drug.case_id, event, result }) }); setNote(`Drug test vendor: ${label(event)}${result ? ` (${result})` : ""}`); }
    catch (err) { setNote(`⚠ ${(err as Error).message}`); }
  }

  async function later(path: string, body: object, msg: string) {
    try { await api(path, { method: "POST", body: JSON.stringify(body) }); setNote(msg); }
    catch (err) { setNote(`⚠ ${(err as Error).message}`); }
  }
  async function uploadPhoto(f: File) {
    const fd = new FormData(); fd.append("phone", phone); fd.append("photo", f);
    const r = await fetch("/api/sim/inbound-photo", { method: "POST", body: fd });
    setNote(r.ok ? "Photo sent from the candidate's phone." : `⚠ ${await r.text()}`);
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
    let r: { candidate_id: number; phone: string };
    try { r = await api("/integrations/workday/applicant", { method: "POST", body: JSON.stringify({ ...form, workday_id }) }); }
    catch (e) { setNote(`⚠ ${(e as Error).message}`); return; }
    setPhone(r.phone);
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
          <select className={`${input} col-span-2`} value={form.channel} onChange={(e) => setForm({ ...form, channel: e.target.value })}>
            <option value="whatsapp">Texts via WhatsApp (works on real phones today)</option>
            <option value="sms">Texts via SMS (needs carrier approval)</option>
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

        <h2 className="pt-4 text-lg font-semibold">Simulate: vendors</h2>
        <p className="text-sm text-stone-500">Events the background-check and drug-test vendors would send for this candidate{vctx ? ` (now: ${label(vctx.stage)} · ${label(vctx.status)})` : ""}.</p>
        <div className="space-y-2 rounded-lg border bg-white p-3 text-sm">
          <div className="font-medium">Background check {vctx?.bg ? <span className="font-mono text-xs text-stone-500">{vctx.bg.order_id} · {label(vctx.bg.report_status)}</span> : <span className="text-xs text-stone-400">(not started)</span>}</div>
          {vctx?.bg && <div className="flex flex-wrap gap-2">
            <a className="rounded border px-2 py-1 hover:bg-stone-100" href={vctx.bg.form_link} target="_blank" rel="noreferrer">Open candidate form ↗</a>
            <button className="rounded border px-2 py-1 hover:bg-stone-100" onClick={() => later("/integrations/bg-vendor/webhook", { order_id: vctx.bg!.order_id, event: "result", status: "clear" }, "Vendor integration: background check CLEAR")}>Result (integration): clear</button>
            <button className="rounded border px-2 py-1 hover:bg-stone-100" onClick={() => later("/integrations/bg-vendor/webhook", { order_id: vctx.bg!.order_id, event: "result", status: "consider", summary: "1 reckless driving violation (2024-03-11)" }, "Vendor integration: background check needs review")}>Result (integration): flagged</button>
            <span className="self-center text-xs text-stone-400">Fallback:</span>
            <button className="rounded border px-2 py-1 hover:bg-stone-100" onClick={() => setEmail(vctx.bg!.email_clear)}>Result email: clear</button>
            <button className="rounded border px-2 py-1 hover:bg-stone-100" onClick={() => setEmail(vctx.bg!.email_flagged)}>Result email: flagged</button>
          </div>}
          {email && <div className="space-y-1 rounded border bg-stone-50 p-2">
            <div className="text-xs text-stone-500">From: {email.from}</div>
            <input className={input} value={email.subject} onChange={(e) => setEmail({ ...email, subject: e.target.value })} />
            <textarea className={`${input} h-36 font-mono text-xs`} value={email.body} onChange={(e) => setEmail({ ...email, body: e.target.value })} />
            <div className="flex gap-2"><button className="rounded bg-emerald-800 px-3 py-1 text-white" onClick={() => sendEmail(email)}>Deliver email</button><button className="text-stone-500" onClick={() => setEmail(null)}>Cancel</button></div>
          </div>}
          <div className="pt-2 font-medium">Drug test {vctx?.drug ? <span className="font-mono text-xs text-stone-500">{vctx.drug.case_id}{vctx.drug.appointment_at ? " · booked" : ""}{vctx.drug.collected ? " · collected" : ""}{vctx.drug.result ? ` · ${vctx.drug.result}` : ""}</span> : <span className="text-xs text-stone-400">(not started)</span>}</div>
          {vctx?.drug && <div className="flex flex-wrap gap-2">
            <a className="rounded border px-2 py-1 hover:bg-stone-100" href={vctx.drug.booking_link} target="_blank" rel="noreferrer">Open booking page ↗</a>
            <button className="rounded border px-2 py-1 hover:bg-stone-100" onClick={() => drugEvent("no_show")}>Missed appointment</button>
            <button className="rounded border px-2 py-1 hover:bg-stone-100" onClick={() => drugEvent("collected")}>Sample collected</button>
            <button className="rounded border px-2 py-1 hover:bg-stone-100" onClick={() => drugEvent("result", "negative")}>Result: negative</button>
            <button className="rounded border px-2 py-1 hover:bg-stone-100" onClick={() => drugEvent("result", "non_negative")}>Result: non-negative</button>
          </div>}
          <div className="pt-2 font-medium">Training (+ CDL permit in parallel) → skills test → permit verified → offer</div>
          <div className="flex flex-wrap gap-2">
            <a className="rounded border px-2 py-1 hover:bg-stone-100" href="/training-roster" target="_blank" rel="noreferrer">Trainer's roster ↗</a>
            <button disabled={!["training", "skills_test"].includes(vctx?.stage ?? "")} className="rounded border px-2 py-1 hover:bg-stone-100 disabled:opacity-40" onClick={() => later("/demo/candidate/says-permit", { phone }, "Candidate says they have their permit: reminders stop.")}>Candidate: "I have my permit"</button>
            <button disabled={!["training", "skills_test", "offer"].includes(vctx?.stage ?? "")} className="rounded border px-2 py-1 hover:bg-stone-100 disabled:opacity-40" onClick={() => later("/demo/send-sample-permit", { phone }, "Sample permit photo sent. Claude is reading it…")}>Send sample permit photo</button>
            <a className="rounded border px-2 py-1 hover:bg-stone-100" href={`/api/demo/sample-permit?phone=${encodeURIComponent(phone)}`} target="_blank" rel="noreferrer">View sample permit ↗</a>
            <button disabled={!vctx?.skills || vctx.stage !== "skills_test"} className="rounded border px-2 py-1 hover:bg-stone-100 disabled:opacity-40" onClick={() => later("/integrations/skills-platform/webhook", { test_id: vctx?.skills?.test_id, result: "pass", score: 91 }, "Skills platform: PASS (91)")}>Skills test: pass</button>
            <button disabled={!vctx?.skills || vctx.stage !== "skills_test"} className="rounded border px-2 py-1 hover:bg-stone-100 disabled:opacity-40" onClick={() => later("/integrations/skills-platform/webhook", { test_id: vctx?.skills?.test_id, result: "fail", score: 62 }, "Skills platform: FAIL (62)")}>Skills test: fail</button>
            {vctx?.offer && <a className="rounded border px-2 py-1 hover:bg-stone-100" href={vctx.offer.link} target="_blank" rel="noreferrer">Open offer ↗</a>}
          </div>
        </div>

        <h2 className="pt-4 text-lg font-semibold">Candidate controls</h2>
        <p className="text-sm text-stone-500">Acts on the candidate whose phone is selected on the right.</p>
        <div className="flex flex-wrap items-center gap-2">
          <button className="rounded border bg-white px-3 py-1 text-sm hover:bg-stone-100" onClick={restartCandidate}>↺ Restart from scratch</button>
          <select className="rounded border bg-white px-2 py-1 text-sm" value={forceTo} onChange={(e) => setForceTo(e.target.value)}>
            {STAGES.filter((st) => st !== "application").map((st) => <option key={st} value={st}>{label(st)}</option>)}
          </select>
          <button className="rounded border bg-white px-3 py-1 text-sm hover:bg-stone-100" onClick={forceStage}>Jump to stage</button>
        </div>

        <h2 className="pt-4 text-lg font-semibold">Demo data</h2>
        <p className="text-sm text-stone-500">~1,500 realistic candidates over 150 days across 12 depots (fictional 555-01XX numbers, never texted or called).</p>
        <div className="flex gap-2">
          <button className="rounded border bg-white px-3 py-1 text-sm hover:bg-stone-100" onClick={() => later("/demo/seed", {}, "Demo data loaded.")}>Load demo data</button>
          <button className="rounded border bg-white px-3 py-1 text-sm hover:bg-stone-100" onClick={() => later("/demo/seed/clear", {}, "Demo data cleared.")}>Clear demo data</button>
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
              <div key={m.id} className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${m.direction === "in" ? "ml-auto bg-sky-500 text-white" : "bg-stone-200"}`}>{m.channel === "voice" ? "📞 " : m.channel === "whatsapp" ? "💬 " : ""}<Linkify text={m.body} /></div>
            ))}
            {busy && <div className="w-12 rounded-2xl bg-stone-200 px-3 py-2 text-sm text-stone-500">…</div>}
            <div ref={end} />
          </div>
          <div className="flex gap-1 border-t p-2">
            <input className="flex-1 rounded-full border px-3 py-1 text-sm" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Text message" />
            <label title="Send a photo (picture message)" className="cursor-pointer rounded-full px-2 text-lg">📷<input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadPhoto(e.target.files[0])} /></label>
            <button className="rounded-full bg-sky-500 px-3 text-sm text-white" onClick={send}>↑</button>
          </div>
        </div>
      </section>
    </div>
  );
}
