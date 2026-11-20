import { useEffect, useState } from "react";
import { label } from "../api";

type Cadence = { preset?: string; texts: { first: number; every_early: number; early_until: number; every_after: number };
                 calls: { enabled: boolean; first: number; every: number } };
type S = {
  follow_up: Record<string, Cadence>; give_up_after_days: number; quiet_hours: [number, number]; ai_calls_enabled: boolean;
  templates: Record<string, Record<string, string>>;
  screening: { min_age: number; min_years_licensed: number; dui_lookback_years: number };
  stage_sla_days: Record<string, number>; results_overdue_days: Record<string, number>;
};
type Payload = { current: S; defaults: S; overrides: Partial<S>; template_labels: Record<string, string>; editable_stages: string[]; sla_stages: string[];
                 presets: Record<string, Cadence> };

// Same algorithm as the backend (settings.build_schedule): texts and calls separately; same day -> call.
function build(c: Cadence, giveUp: number) {
  const texts = new Set<number>(), calls = new Set<number>();
  for (let d = c.texts.first; d < giveUp && d > 0;) { texts.add(d); d += d < c.texts.early_until ? Math.max(1, c.texts.every_early) : Math.max(1, c.texts.every_after); }
  if (c.calls.enabled) for (let d = c.calls.first; d < giveUp && d > 0; d += Math.max(1, c.calls.every)) calls.add(d);
  for (const d of calls) texts.delete(d);
  return { texts, calls };
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api/settings${path}`, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json();
  if (!r.ok) throw j.detail?.errors ?? [JSON.stringify(j.detail)];
  return j;
}

function Section({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return <section className="rounded-lg border bg-white p-4"><h3 className="font-semibold">{title}</h3><p className="mb-3 text-xs text-stone-500">{sub}</p>{children}</section>;
}

export default function Settings() {
  const [p, setP] = useState<Payload | null>(null);
  const [draft, setDraft] = useState<S | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState("");
  const [tpl, setTpl] = useState("intro");
  const [openStage, setOpenStage] = useState<string | null>(() => new URLSearchParams(location.search).get("open"));
  const load = () => call<Payload>("GET", "").then((x) => { setP(x); setDraft(structuredClone(x.current)); });
  useEffect(() => { load(); }, []);
  if (!p || !draft) return <p className="text-stone-500">Loading…</p>;

  const dirty = JSON.stringify(draft) !== JSON.stringify(p.current);
  // Only send the parts that differ from what's saved.
  const changes = () => Object.fromEntries(Object.entries(draft).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify((p.current as Record<string, unknown>)[k])));
  async function save() {
    setErrors([]); setSaved("");
    try { await call("PUT", "", { changes: changes() }); await load(); setSaved("Saved. Changes apply to new messages and the next follow-up check."); }
    catch (e) { setErrors(e as string[]); }
  }
  async function reset(path: string[]) { setErrors([]); await call("POST", "/reset", { path }); await load(); setSaved("Reset to default."); }
  const set = (fn: (d: S) => void) => { const d = structuredClone(draft); fn(d); setDraft(d); setSaved(""); };
  const isOverridden = (path: string[]) => path.reduce<unknown>((n, k) => (n as Record<string, unknown> | undefined)?.[k], p.overrides) !== undefined;
  const num = "w-16 rounded border px-1 py-0.5 text-sm";

  return (
    <div className="space-y-5 pb-24">
      <div><h2 className="text-lg font-semibold">Settings</h2><p className="text-xs text-stone-500">Change how the system follows up and what it says, without engineers. Defaults are kept, so anything can be reset.</p></div>

      <Section title="A. Follow-ups" sub="When candidates get a reminder text or an AI call, per stage. Days count from the candidate's last activity; the schedule restarts whenever they reply.">
        <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
          <label>Stop reminders and hand to a recruiter after <input type="number" className={num} value={draft.give_up_after_days} onChange={(e) => set((d) => { d.give_up_after_days = +e.target.value; })} /> days</label>
          <label>Quiet hours: no messages or calls from <input type="number" className={num} value={draft.quiet_hours[0]} onChange={(e) => set((d) => { d.quiet_hours[0] = +e.target.value; })} />:00 to <input type="number" className={num} value={draft.quiet_hours[1]} onChange={(e) => set((d) => { d.quiet_hours[1] = +e.target.value; })} />:00</label>
          <label className="flex items-center gap-1"><input type="checkbox" checked={draft.ai_calls_enabled} onChange={(e) => set((d) => { d.ai_calls_enabled = e.target.checked; })} /> AI follow-up calls (off = text instead)</label>
        </div>
        <div className="space-y-2">
          {p.editable_stages.map((st) => {
            const c = draft.follow_up[st];
            const { texts, calls } = build(c, draft.give_up_after_days);
            const isOpen = openStage === st;
            const n = (v: number, fn: (d: S, x: number) => void) => (
              <input type="number" min={1} className="mx-1 w-12 rounded border px-1 py-0.5 text-sm" value={v} onChange={(e) => set((d) => { fn(d, +e.target.value); d.follow_up[st].preset = "custom"; })} />
            );
            return (
            <div key={st} className="rounded border px-3 py-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className="w-36 shrink-0 font-medium text-stone-700">{label(st)}{isOverridden(["follow_up", st]) && <span className="ml-1 text-xs font-normal text-amber-700">• edited</span>}</span>
                <span className="flex-1 text-xs text-stone-500">{label(c.preset ?? "custom")} · 💬 {texts.size} texts · 📞 {c.calls.enabled ? `${calls.size} AI calls` : "no calls"}</span>
                {isOverridden(["follow_up", st]) && <button className="text-xs text-stone-400 underline" onClick={() => reset(["follow_up", st])}>reset</button>}
                <button className="rounded border px-2 py-0.5 text-xs hover:bg-stone-50" onClick={() => setOpenStage(isOpen ? null : st)}>{isOpen ? "Done" : "Edit"}</button>
              </div>
              {isOpen && <div className="mt-3 space-y-2">
                <div className="flex items-center gap-2 text-xs"><span className="text-stone-500">Preset:</span>
                  {Object.keys(p.presets).map((name) => (
                    <button key={name} onClick={() => set((d) => { d.follow_up[st] = { ...structuredClone(p.presets[name]), preset: name }; })}
                      className={`rounded-full border px-2 py-0.5 ${c.preset === name ? "border-emerald-700 bg-emerald-50 text-emerald-900" : "hover:bg-stone-50"}`}>{label(name)}</button>
                  ))}
                  {c.preset === "custom" && <span className="text-stone-400">(custom)</span>}
                </div>
                <div>💬 <b>Texts:</b> first on day{n(c.texts.first, (d, x) => { d.follow_up[st].texts.first = x; })}, then every{n(c.texts.every_early, (d, x) => { d.follow_up[st].texts.every_early = x; })}days until day{n(c.texts.early_until, (d, x) => { d.follow_up[st].texts.early_until = x; })}, then every{n(c.texts.every_after, (d, x) => { d.follow_up[st].texts.every_after = x; })}days</div>
                <div className="flex flex-wrap items-center">📞 <b className="ml-1">AI calls:</b>
                  <label className="ml-2 mr-2 flex items-center gap-1 text-xs"><input type="checkbox" checked={c.calls.enabled} onChange={(e) => set((d) => { d.follow_up[st].calls.enabled = e.target.checked; d.follow_up[st].preset = "custom"; })} /> on</label>
                  <span className={c.calls.enabled ? "" : "opacity-40"}>first on day{n(c.calls.first, (d, x) => { d.follow_up[st].calls.first = x; })}, then every{n(c.calls.every, (d, x) => { d.follow_up[st].calls.every = x; })}days</span>
                </div>
                <p className="text-xs text-stone-500">{texts.size} texts + {calls.size} AI calls before day {draft.give_up_after_days}. If a text and a call fall on the same day, the call goes out and a text follows only if it isn't answered.</p>
                <button className="text-xs text-stone-500 underline" onClick={() => set((d) => { for (const o of p.editable_stages) d.follow_up[o] = structuredClone(d.follow_up[st]); })}>Copy this schedule to all stages</button>
              </div>}
            </div>
            );
          })}
        </div>
      </Section>

      <Section title="B. Message wording" sub="Edit what candidates receive. Keep the {placeholders}: they're filled in per candidate (name, links, clinic, time). SMS messages that include the opt-out instruction must keep it.">
        <div className="grid gap-4 lg:grid-cols-[16rem_1fr]">
          <div className="max-h-96 overflow-y-auto rounded border text-sm">
            {Object.entries(p.template_labels).map(([k, l]) => (
              <button key={k} onClick={() => setTpl(k)} className={`block w-full px-2 py-1.5 text-left ${tpl === k ? "bg-emerald-50 font-medium" : "hover:bg-stone-50"}`}>
                {l}{isOverridden(["templates", k]) && <span className="ml-1 text-xs text-amber-700">• edited</span>}
              </button>
            ))}
          </div>
          <div className="space-y-3">
            {["en", "es"].map((lang) => draft.templates[tpl]?.[lang] !== undefined && (
              <div key={lang}>
                <div className="mb-1 text-xs font-medium text-stone-600">{lang === "en" ? "English" : "Español"}</div>
                <textarea className="h-24 w-full rounded border p-2 text-sm" value={draft.templates[tpl][lang]} onChange={(e) => set((d) => { d.templates[tpl][lang] = e.target.value; })} />
                <div className="mt-1 rounded-2xl bg-stone-100 px-3 py-2 text-xs text-stone-700 whitespace-pre-line"><span className="text-stone-400">Preview: </span>{fill(draft.templates[tpl][lang])}</div>
              </div>
            ))}
            {isOverridden(["templates", tpl]) && <button className="text-xs text-stone-500 underline" onClick={() => reset(["templates", tpl])}>Reset this message to default</button>}
          </div>
        </div>
      </Section>

      <div className="grid gap-5 lg:grid-cols-2">
        <Section title="C. Screening rules" sub="Thresholds for the automatic-fail checks (from Prime Pupil). Failing still goes to a recruiter for review.">
          <div className="space-y-2 text-sm">
            <label className="flex items-center justify-between">Minimum age <input type="number" className={num} value={draft.screening.min_age} onChange={(e) => set((d) => { d.screening.min_age = +e.target.value; })} /></label>
            <label className="flex items-center justify-between">Minimum years licensed <input type="number" className={num} value={draft.screening.min_years_licensed} onChange={(e) => set((d) => { d.screening.min_years_licensed = +e.target.value; })} /></label>
            <label className="flex items-center justify-between">No DUI in the past (years) <input type="number" className={num} value={draft.screening.dui_lookback_years} onChange={(e) => set((d) => { d.screening.dui_lookback_years = +e.target.value; })} /></label>
            <p className="text-xs text-stone-400">The screening questions update automatically (e.g. "Have you had a DUI in the past {draft.screening.dui_lookback_years} years?").</p>
          </div>
        </Section>
        <Section title="D. Time limits" sub="When a candidate shows as stuck on the dashboard, and when vendor results are flagged as overdue (FYI only).">
          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-sm">
            {p.sla_stages.map((st) => (
              <label key={st} className="flex items-center justify-between">{label(st)} <span><input type="number" className={num} value={draft.stage_sla_days[st]} onChange={(e) => set((d) => { d.stage_sla_days[st] = +e.target.value; })} /> d</span></label>
            ))}
            <div className="col-span-2 mt-2 border-t pt-2 text-xs font-medium text-stone-600">Results overdue after</div>
            {Object.keys(draft.results_overdue_days).map((st) => (
              <label key={st} className="flex items-center justify-between">{label(st)} <span><input type="number" className={num} value={draft.results_overdue_days[st]} onChange={(e) => set((d) => { d.results_overdue_days[st] = +e.target.value; })} /> d</span></label>
            ))}
          </div>
        </Section>
      </div>

      <div className="fixed inset-x-0 bottom-0 border-t bg-white/95 px-4 py-3">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-3">
          <button disabled={!dirty} onClick={save} className="rounded bg-emerald-800 px-4 py-1.5 text-sm text-white disabled:opacity-40">Save changes</button>
          <button disabled={!dirty} onClick={() => { setDraft(structuredClone(p.current)); setErrors([]); }} className="text-sm text-stone-500 disabled:opacity-40">Discard</button>
          <button onClick={() => reset([])} className="ml-auto text-xs text-stone-400 underline">Reset everything to defaults</button>
          {saved && <span className="text-sm text-emerald-700">{saved}</span>}
          {errors.length > 0 && <ul className="w-full list-disc pl-5 text-sm text-rose-700">{errors.map((e) => <li key={e}>{e}</li>)}</ul>}
        </div>
      </div>
    </div>
  );
}
