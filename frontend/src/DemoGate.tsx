import { useEffect, useState } from "react";
import { demoHeaders, setDemoKey } from "./api";

// Wraps demo-only pages: asks for the demo password once (remembered in this browser).
export default function DemoGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<"checking" | "locked" | "open">("checking");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const check = () => fetch("/api/demo/check", { headers: demoHeaders() }).then((r) => setState(r.ok ? "open" : "locked")).catch(() => setState("locked"));
  useEffect(() => { check(); }, []);
  if (state === "checking") return <p className="text-stone-500">…</p>;
  if (state === "open") return <>{children}</>;
  return (
    <form className="mx-auto mt-16 max-w-sm space-y-3 rounded-xl border bg-white p-6" onSubmit={async (e) => {
      e.preventDefault(); setDemoKey(pw);
      const r = await fetch("/api/demo/check", { headers: demoHeaders() });
      if (r.ok) { setState("open"); window.dispatchEvent(new Event("pp-demo-unlocked")); } else { setDemoKey(""); setErr("Wrong password."); }
    }}>
      <h2 className="text-lg font-semibold">Demo controls</h2>
      <p className="text-sm text-stone-500">These pages are for running the demo. Enter the demo password.</p>
      <input type="password" autoFocus className="w-full rounded-lg border px-3 py-2 text-sm" value={pw} onChange={(e) => setPw(e.target.value)} placeholder="Password" />
      <button className="w-full rounded-lg bg-emerald-800 py-2 text-sm text-white">Unlock</button>
      {err && <p className="text-sm text-rose-700">{err}</p>}
    </form>
  );
}
