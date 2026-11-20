import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, demoHeaders, type Lookups } from "../api";

// Stand-in for Prime Pupil's career page. Submitting creates the application in Workday (poll mode:
// our connector picks it up with Get_Candidates) or posts it straight in (direct mode).
export default function Apply() {
  const nav = useNavigate();
  const [lk, setLk] = useState<Lookups>({ depots: [], recruiters: [] });
  const [mode, setMode] = useState("poll");
  const [f, setF] = useState({ first_name: "", last_name: "", phone: "", depot_id: 1, language: "en", channel: "whatsapp", first_contact: "text", sms_consent: true });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api<Lookups>("/lookups").then(setLk);
    api<{ workday_intake?: string }>("/demo/voice-status").then((v) => setMode(v.workday_intake ?? "poll"));
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      let phone = f.phone;
      if (mode === "poll") {
        const r = await fetch("/mock-workday/career-site/apply", { method: "POST", headers: { "Content-Type": "application/json", ...demoHeaders() },
          body: JSON.stringify({ first_name: f.first_name, last_name: f.last_name, phone: f.phone, depot_id: f.depot_id,
            preferred_language: f.language, sms_consent: f.sms_consent, contact_channel: f.channel, first_contact: f.first_contact }) });
        if (!r.ok) throw new Error((await r.json()).detail ?? "Couldn't submit");
      } else {
        const r = await api<{ phone: string }>("/integrations/workday/applicant", { method: "POST",
          body: JSON.stringify({ ...f, workday_id: `WD-${Math.floor(1000 + Math.random() * 9000)}` }) });
        phone = r.phone;
      }
      nav(`/demo?phone=${encodeURIComponent(phone)}&new=1`);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  const input = "w-full rounded-lg border border-stone-300 px-3 py-2 text-sm focus:border-emerald-700 focus:outline-none";
  return (
    <div className="mx-auto max-w-md">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-800">Prime Pupil Transportation · Careers</div>
      <h2 className="text-2xl font-semibold">School Bus Driver</h2>
      <p className="mb-5 text-sm text-stone-600">Paid CDL training · Split shift during the school year · No CDL needed to apply</p>
      <form onSubmit={submit} className="space-y-3 rounded-xl border bg-white p-5 shadow-sm">
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-stone-600">First name<input required className={input} value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} /></label>
          <label className="text-xs text-stone-600">Last name<input required className={input} value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} /></label>
        </div>
        <label className="block text-xs text-stone-600">Mobile phone<input required className={input} placeholder="(518) 555-0123" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></label>
        <label className="block text-xs text-stone-600">Closest depot
          <select className={input} value={f.depot_id} onChange={(e) => setF({ ...f, depot_id: Number(e.target.value) })}>
            {lk.depots.map((d) => <option key={d.id} value={d.id}>{d.name} ({d.city})</option>)}
          </select></label>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-xs text-stone-600">Preferred language
            <select className={input} value={f.language} onChange={(e) => setF({ ...f, language: e.target.value })}>
              <option value="en">English</option><option value="es">Español</option><option value="other">Other</option>
            </select></label>
          <label className="text-xs text-stone-600">Text me on
            <select className={input} value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })}>
              <option value="whatsapp">WhatsApp</option><option value="sms">SMS (text message)</option>
            </select></label>
        </div>
        <fieldset className="text-xs text-stone-600">
          <legend className="mb-1">How should we reach you first?</legend>
          <div className="grid grid-cols-2 gap-3">
            {[["text", "Text me"], ["call", "Give me a call"]].map(([v, l]) => (
              <label key={v} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm ${f.first_contact === v ? "border-emerald-700 bg-emerald-50 text-emerald-900" : "border-stone-300 text-stone-700"}`}>
                <input type="radio" name="first_contact" value={v} checked={f.first_contact === v} onChange={() => setF({ ...f, first_contact: v })} />{l}
              </label>))}
          </div>
          {f.first_contact === "call" && <p className="mt-1 text-stone-500">We'll call you within a minute for a few quick questions (about 3 minutes).</p>}
        </fieldset>
        <label className="flex items-start gap-2 text-xs text-stone-600">
          <input type="checkbox" className="mt-0.5" checked={f.sms_consent} onChange={(e) => setF({ ...f, sms_consent: e.target.checked })} />
          I agree to receive texts and calls about my application. Msg &amp; data rates may apply. Reply STOP to opt out.
        </label>
        <button disabled={busy} className="w-full rounded-lg bg-emerald-800 py-2.5 text-sm font-medium text-white hover:bg-emerald-900 disabled:opacity-50">{busy ? "Submitting…" : "Apply"}</button>
        {err && <p className="text-sm text-rose-700">⚠ {err}</p>}
      </form>
      <p className="mt-3 text-center text-xs text-stone-400">Demo: applications go into {mode === "poll" ? "a fake Workday; our connector picks them up within seconds" : "the system directly (shortcut mode)"}.</p>
    </div>
  );
}
