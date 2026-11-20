import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, label, STAGES, type Candidate, type Message } from "../api";
import { Linkify, StatusPill } from "../components";

// Demo console: everything here acts on ONE selected candidate (picked at the top), so the phone and the
// controls can never drift apart. New applicants are created on the "New applicant" page.

type Email = { from: string; subject: string; body: string };
type VCtx = {
  stage: string; status: string; candidate_id?: number;
  bg: null | { order_id: string; form_link: string; form_completed: boolean; report_status: string; email_clear: Email; email_flagged: Email };
  drug: null | { case_id: string; booking_link: string; appointment_at: string | null; collected: boolean; result: string | null };
  skills?: { test_id: string; link: string; result: string | null; attempts: number };
  offer?: { offer_id: string; link: string; signed: boolean; declined: boolean };
};

const btn = "rounded-lg border bg-white px-3 py-1.5 text-sm hover:bg-stone-50 disabled:opacity-40";
const linkBtn = `${btn} inline-block`;

function Card({ title, children, hint }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border bg-white p-4">
      <h3 className="font-semibold">{title}</h3>
      {hint && <p className="mb-3 text-xs text-stone-500">{hint}</p>}
      <div className={hint ? "" : "mt-3"}>{children}</div>
    </section>
  );
}

export default function Demo() {
  const [params, setParams] = useSearchParams();
  const phone = params.get("phone") ?? "";
  const setPhone = (p: string) => setParams(p ? { phone: p } : {});

  // ---- candidate picker ----
  const [q, setQ] = useState("");
  const [options, setOptions] = useState<Candidate[]>([]);
  const [picking, setPicking] = useState(!phone);
  useEffect(() => {
    const t = setTimeout(() => {
      api<Candidate[]>(`/candidates?limit=20${q ? `&q=${encodeURIComponent(q)}` : "&exclude_seed=true"}`).then(setOptions).catch(() => setOptions([]));
    }, 200);
    return () => clearTimeout(t);
  }, [q, phone]);

  // ---- selected candidate state ----
  const [cand, setCand] = useState<Candidate | null>(null);
  const [vctx, setVctx] = useState<VCtx | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [note, setNote] = useState(params.get("new") ? "Application submitted. Waiting for it to arrive from Workday…" : "");
  useEffect(() => {
    if (!phone) { setCand(null); setVctx(null); setMsgs([]); return; }
    const load = () => {
      api<Message[]>(`/sim/messages?phone=${encodeURIComponent(phone)}`).then(setMsgs).catch(() => setMsgs([]));
      api<VCtx>(`/demo/vendor-context?phone=${encodeURIComponent(phone)}`).then((v) => {
        setVctx(v);
        if (v.candidate_id) api<{ candidate: Candidate }>(`/candidates/${v.candidate_id}`).then((d) => setCand(d.candidate));
      }).catch(() => { setVctx(null); setCand(null); });
    };
    load();
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [phone]);
  useEffect(() => { if (cand && note.startsWith("Application submitted")) setNote(`${cand.first_name} arrived from Workday. The first message is on their phone.`); }, [cand]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- voice status ----
  const [voiceReady, setVoiceReady] = useState(false);
  useEffect(() => {
    const load = () => { api<{ ready: boolean }>("/demo/voice-status").then((v) => setVoiceReady(v.ready)).catch(() => setVoiceReady(false)); };
    load(); const t = setInterval(load, 5000); return () => clearInterval(t);
  }, []);

  // ---- actions ----
  async function act(path: string, body: unknown, msg: string, method = "POST") {
    try { await api(path, { method, body: body === undefined ? undefined : JSON.stringify(body) }); setNote(msg); }
    catch (e) { setNote(`⚠ ${(e as Error).message}`); }
  }
  const [email, setEmail] = useState<Email | null>(null);
  async function sendEmail(e: Email) {
    setNote("Vendor email received. Claude is reading it…");
    try {
      const r = await api<{ processed: boolean; parsed: { status: string; summary: string } }>("/integrations/bg-vendor/email", { method: "POST", body: JSON.stringify({ sender: e.from, subject: e.subject, body: e.body }) });
      setNote(r.processed ? `Email read: ${r.parsed.status.toUpperCase()}. ${r.parsed.summary}` : "Couldn't read the email → sent to a recruiter."); setEmail(null);
    } catch (err) { setNote(`⚠ ${(err as Error).message}`); }
  }
  const drug = (event: string, result?: string) => vctx?.drug && act("/integrations/drug-vendor/webhook", { case_id: vctx.drug.case_id, event, result }, `Drug test vendor: ${label(event)}${result ? ` (${result.replace("_", "-")})` : ""}`);
  const [forceTo, setForceTo] = useState("background_check");
  const [showEnv, setShowEnv] = useState(false);

  // ---- phone ----
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const thread = useRef<HTMLDivElement>(null);
  // Scroll only the phone's thread (scrollIntoView would scroll the whole page).
  useEffect(() => { const el = thread.current; if (el) el.scrollTop = el.scrollHeight; }, [msgs.length, busy]);
  async function send() {
    if (!text.trim() || busy || !phone) return;
    const body = text; setText(""); setBusy(true);
    try { await api("/sim/inbound", { method: "POST", body: JSON.stringify({ phone, body }) }); }
    catch (e) { setNote(`⚠ ${(e as Error).message}`); } finally { setBusy(false); }
  }
  async function uploadPhoto(file: File) {
    const fd = new FormData(); fd.append("phone", phone); fd.append("photo", file);
    const r = await fetch("/api/sim/inbound-photo", { method: "POST", body: fd });
    setNote(r.ok ? "Photo sent from the candidate's phone." : `⚠ ${await r.text()}`);
  }

  const stage = vctx?.stage ?? "";
  const permitStages = ["training", "skills_test", "offer"];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><h2 className="text-lg font-semibold">Demo console</h2><p className="text-xs text-stone-500">Pick a candidate, then act as them (phone) or as the outside world (vendors, time). New applicants: <Link to="/apply" className="underline">New applicant page</Link>.</p></div>
      </div>

      {/* Candidate picker */}
      <section className="rounded-xl border bg-white p-4">
        {cand && !picking ? (
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 font-semibold text-emerald-900">{cand.first_name[0]}{cand.last_name?.[0] ?? ""}</div>
            <div className="mr-auto">
              <div className="font-semibold">{cand.first_name} {cand.last_name} <span className="ml-1 text-sm font-normal text-stone-500">{cand.phone} · {cand.preferred_language.toUpperCase()} · {cand.preferred_channel === "whatsapp" ? "WhatsApp" : "SMS"}</span></div>
              <div className="mt-0.5 flex items-center gap-2 text-sm"><span className="font-medium">{label(cand.stage)}</span><StatusPill status={cand.status} /></div>
            </div>
            <Link to={`/candidates/${cand.id}`} className="text-sm text-emerald-800 underline">Open recruiter view →</Link>
            <button className={btn} onClick={() => { setPicking(true); setQ(""); }}>Change candidate</button>
          </div>
        ) : (
          <div>
            <div className="mb-2 flex items-center gap-2">
              <input autoFocus className="flex-1 rounded-lg border px-3 py-2 text-sm" placeholder="Search by name or phone (demo data included when searching)…" value={q} onChange={(e) => setQ(e.target.value)} />
              {cand && <button className={btn} onClick={() => setPicking(false)}>Cancel</button>}
            </div>
            <div className="max-h-56 divide-y overflow-y-auto rounded-lg border text-sm">
              {options.length === 0 && <p className="p-3 text-stone-500">{q ? "No matches." : "No live candidates yet. Create one on the New applicant page."}</p>}
              {options.map((o) => (
                <button key={o.id} className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-stone-50" onClick={() => { setPhone(o.phone); setPicking(false); setNote(""); }}>
                  <span className="w-44 font-medium">{o.first_name} {o.last_name}</span><span className="w-32 text-stone-500">{o.phone}</span>
                  <span className="w-32">{label(o.stage)}</span><StatusPill status={o.status} />
                </button>
              ))}
            </div>
          </div>
        )}
        {note && <p className="mt-3 rounded-lg bg-stone-50 px-3 py-2 text-sm text-stone-700">{note}</p>}
      </section>

      {phone && (
        <div className="grid gap-4 lg:grid-cols-[1fr_22rem]">
          <div className="space-y-4">
            {/* Contextual: what can happen next at this stage */}
            <Card title={`Simulate: ${label(stage || "…")}`} hint="Events from the outside world for this candidate's current step.">
              {cand?.status === "needs_review" && <p className="mb-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-800">Waiting on a recruiter decision. <Link to="/" className="underline">Open Today →</Link></p>}
              {stage === "screening" && <p className="text-sm text-stone-600">Reply on the phone to answer the screening questions (or use Call me now).</p>}
              {stage === "background_check" && vctx?.bg && (
                <div className="space-y-2">
                  <div className="flex flex-wrap gap-2">
                    <a className={linkBtn} href={vctx.bg.form_link} target="_blank" rel="noreferrer">Open vendor form ↗</a>
                    <button className={btn} onClick={() => act("/integrations/bg-vendor/webhook", { order_id: vctx.bg!.order_id, event: "result", status: "clear" }, "Vendor integration: background check CLEAR")}>Result: clear</button>
                    <button className={btn} onClick={() => act("/integrations/bg-vendor/webhook", { order_id: vctx.bg!.order_id, event: "result", status: "consider", summary: "1 reckless driving violation (2024-03-11)" }, "Vendor integration: needs review")}>Result: needs review</button>
                  </div>
                  <details className="text-sm"><summary className="cursor-pointer text-xs text-stone-500">Fallback: results by email (Claude reads it)</summary>
                    <div className="mt-2 flex gap-2"><button className={btn} onClick={() => setEmail(vctx.bg!.email_clear)}>Email: clear</button><button className={btn} onClick={() => setEmail(vctx.bg!.email_flagged)}>Email: flagged</button></div>
                    {email && <div className="mt-2 space-y-1 rounded-lg border bg-stone-50 p-2">
                      <div className="text-xs text-stone-500">From: {email.from}</div>
                      <input className="w-full rounded border px-2 py-1 text-sm" value={email.subject} onChange={(e) => setEmail({ ...email, subject: e.target.value })} />
                      <textarea className="h-32 w-full rounded border px-2 py-1 font-mono text-xs" value={email.body} onChange={(e) => setEmail({ ...email, body: e.target.value })} />
                      <div className="flex gap-2"><button className="rounded-lg bg-emerald-800 px-3 py-1 text-sm text-white" onClick={() => sendEmail(email)}>Deliver email</button><button className="text-sm text-stone-500" onClick={() => setEmail(null)}>Cancel</button></div>
                    </div>}
                  </details>
                </div>
              )}
              {stage === "drug_test" && vctx?.drug && (
                <div className="flex flex-wrap gap-2">
                  <a className={linkBtn} href={vctx.drug.booking_link} target="_blank" rel="noreferrer">Open booking page ↗</a>
                  <button className={btn} onClick={() => drug("no_show")}>Missed appointment</button>
                  <button className={btn} onClick={() => drug("collected")}>Sample collected</button>
                  <button className={btn} onClick={() => drug("result", "negative")}>Result: negative</button>
                  <button className={btn} onClick={() => drug("result", "non_negative")}>Result: non-negative</button>
                  <span className="w-full text-xs text-stone-500">{vctx.drug.appointment_at ? "Appointment booked. " : "Not booked yet. "}{vctx.drug.collected ? "Sample collected." : ""}</span>
                </div>
              )}
              {stage === "training" && (
                <div className="flex flex-wrap gap-2">
                  <a className={linkBtn} href="/training-roster" target="_blank" rel="noreferrer">Trainer's roster ↗ (tick Completed)</a>
                </div>
              )}
              {stage === "skills_test" && vctx?.skills && (
                <div className="flex flex-wrap gap-2">
                  <button className={btn} onClick={() => act("/integrations/skills-platform/webhook", { test_id: vctx.skills!.test_id, result: "pass", score: 91 }, "Skills platform: PASS (91)")}>Skills test: pass</button>
                  <button className={btn} onClick={() => act("/integrations/skills-platform/webhook", { test_id: vctx.skills!.test_id, result: "fail", score: 62 }, "Skills platform: FAIL (62)")}>Skills test: fail</button>
                </div>
              )}
              {stage === "offer" && (
                <div className="flex flex-wrap gap-2">
                  {vctx?.offer ? <a className={linkBtn} href={vctx.offer.link} target="_blank" rel="noreferrer">Open offer (sign / decline) ↗</a>
                    : <span className="text-sm text-stone-600">Offer goes out once the recruiter verifies the CDL permit photo.</span>}
                </div>
              )}
              {permitStages.includes(stage) && (
                <div className="mt-3 border-t pt-3">
                  <div className="mb-2 text-xs font-medium text-stone-600">CDL permit (parallel track)</div>
                  <div className="flex flex-wrap gap-2">
                    {stage !== "offer" && <button className={btn} onClick={() => act("/demo/candidate/says-permit", { phone }, "Candidate says they have their permit: reminders stop.")}>Candidate: "I have my permit"</button>}
                    <button className={btn} onClick={() => act("/demo/send-sample-permit", { phone }, "Sample permit photo sent. Claude is reading it…")}>Send sample permit photo</button>
                    <a className={linkBtn} href={`/api/demo/sample-permit?phone=${encodeURIComponent(phone)}`} target="_blank" rel="noreferrer">View sample ↗</a>
                  </div>
                </div>
              )}
              {stage === "hired" && <p className="text-sm text-emerald-800">Hired 🎉 Nothing left to simulate.</p>}
            </Card>

            <div className="grid gap-4 md:grid-cols-2">
              <Card title="Time" hint="Move the system clock so follow-ups fire as if days passed.">
                <div className="flex flex-wrap gap-2">
                  {[1, 3, 7, 30, 90].map((d) => <button key={d} className={btn} onClick={async () => {
                    setNote(`Skipping ahead ${d} day(s)…`);
                    const r = await api<{ offset_days: number; actions: number }>("/demo/clock/advance", { method: "POST", body: JSON.stringify({ days: d }) });
                    setNote(`Simulated time is +${r.offset_days} days. The engine took ${r.actions} action(s).`);
                  }}>+{d}d</button>)}
                  <button className="text-sm text-stone-500 underline" onClick={() => act("/demo/clock/reset", undefined, "Clock reset to real time.")}>Reset</button>
                </div>
              </Card>
              <Card title="Candidate controls" hint="Shortcuts for demoing.">
                <div className="flex flex-wrap items-center gap-2">
                  <select className="rounded-lg border px-2 py-1.5 text-sm" value={forceTo} onChange={(e) => setForceTo(e.target.value)}>
                    {STAGES.filter((s) => !["application", "cdl_permit"].includes(s)).map((s) => <option key={s} value={s}>{label(s)}</option>)}
                  </select>
                  <button className={btn} onClick={() => act("/demo/candidate/stage", { phone, stage: forceTo }, `Moved to ${label(forceTo)}.`)}>Jump to stage</button>
                  <button className={btn} onClick={() => { if (confirm("Restart this candidate from scratch?")) act("/demo/candidate/restart", { phone }, "Restarted: intro re-sent."); }}>↺ Restart</button>
                </div>
              </Card>
            </div>
          </div>

          {/* Phone */}
          <div>
            <div className="mb-2 flex items-center justify-between text-xs">
              <span className={voiceReady ? "text-emerald-700" : "text-rose-700"}>● {voiceReady ? "Voice ready" : "Voice not connected"}</span>
              <button className="rounded-lg bg-sky-700 px-3 py-1.5 text-sm text-white hover:bg-sky-800" onClick={() => act("/demo/call", { phone }, `Calling ${phone}… answer the phone!`)}>📞 Call me now</button>
            </div>
            <div className="mx-auto w-80 overflow-hidden rounded-[2rem] border-8 border-stone-800 bg-white">
              <div className="border-b bg-stone-50 px-3 py-2 text-center text-xs text-stone-500">{cand ? `${cand.first_name} · ${cand.preferred_channel === "whatsapp" ? "WhatsApp" : "SMS"}` : "…"}</div>
              <div ref={thread} className="h-[30rem] space-y-2 overflow-y-auto p-3">
                {msgs.map((m) => (
                  <div key={m.id} className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${m.direction === "in" ? "ml-auto bg-sky-500 text-white" : "bg-stone-200"}`}>
                    {m.channel === "voice" ? "📞 " : ""}<Linkify text={m.body} />
                  </div>
                ))}
                {busy && <div className="w-12 rounded-2xl bg-stone-200 px-3 py-2 text-sm text-stone-500">…</div>}
              </div>
              <div className="flex items-center gap-1 border-t p-2">
                <label title="Send a photo" className="cursor-pointer px-1 text-lg">📷<input type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadPhoto(e.target.files[0])} /></label>
                <input className="flex-1 rounded-full border px-3 py-1 text-sm" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Reply as the candidate" />
                <button className="rounded-full bg-sky-500 px-3 py-1 text-sm text-white" onClick={send}>↑</button>
              </div>
            </div>
            <p className="mt-2 text-center text-xs text-stone-400">Messages also go to the real phone ({cand?.preferred_channel === "whatsapp" ? "WhatsApp" : "SMS"}). Replies typed here act as the candidate.</p>
          </div>
        </div>
      )}

      <section className="rounded-xl border border-dashed bg-white/60 p-3">
        <button className="text-sm text-stone-500" onClick={() => setShowEnv(!showEnv)}>{showEnv ? "▾" : "▸"} Environment</button>
        {showEnv && <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-stone-500">Demo data (~1,500 candidates, fictional numbers):</span>
          <button className={btn} onClick={() => act("/demo/seed", {}, "Demo data loaded.")}>Load</button>
          <button className={btn} onClick={() => act("/demo/seed/clear", {}, "Demo data cleared.")}>Clear</button>
        </div>}
      </section>
    </div>
  );
}
