import { useState } from "react";
import { api } from "../api";

type Line = { from: "me" | "bot"; text: string };

// Demo control panel. Increment 0: chat simulator (echo). Later: form link, fast-forward, vendor events.
export default function Demo() {
  const [phone, setPhone] = useState("+15550001111");
  const [text, setText] = useState("");
  const [lines, setLines] = useState<Line[]>([]);

  async function send() {
    if (!text.trim()) return;
    setLines((l) => [...l, { from: "me", text }]);
    setText("");
    const { reply } = await api<{ reply: string }>("/chat", { method: "POST", body: JSON.stringify({ phone, body: text }) });
    setLines((l) => [...l, { from: "bot", text: reply }]);
  }

  return (
    <div className="max-w-sm">
      <h2 className="text-lg font-semibold mb-2">Chat simulator</h2>
      <input className="w-full border rounded px-2 py-1 text-sm mb-2" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <div className="h-80 overflow-y-auto rounded-lg border bg-white p-3 space-y-2">
        {lines.map((l, i) => (
          <div key={i} className={`max-w-[80%] rounded-2xl px-3 py-2 text-sm ${l.from === "me" ? "ml-auto bg-emerald-700 text-white" : "bg-stone-200"}`}>{l.text}</div>
        ))}
      </div>
      <div className="mt-2 flex gap-2">
        <input className="flex-1 border rounded px-2 py-1 text-sm" value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Type a text…" />
        <button className="rounded bg-emerald-800 px-3 text-sm text-white" onClick={send}>Send</button>
      </div>
    </div>
  );
}
