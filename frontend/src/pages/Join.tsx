import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { api } from "../api";

// Public page to screen-share at the start of the demo: scan, say hi to Prime Pupil on WhatsApp, then apply.
// Messaging first opens WhatsApp's 24-hour window, so our messages can reach them; we reply with the apply link.
export default function Join() {
  const [link, setLink] = useState("");
  const [qr, setQr] = useState("");
  useEffect(() => {
    api<{ whatsapp: string; prefill: string }>("/join-info").then(async (j) => {
      if (!j.whatsapp) return;
      const url = `https://wa.me/${j.whatsapp}?text=${encodeURIComponent(j.prefill)}`;
      setLink(url);
      setQr(await QRCode.toDataURL(url, { width: 520, margin: 1 }));
    });
  }, []);
  return (
    <div className="mx-auto max-w-lg text-center">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-800">Prime Pupil Transportation · Careers</div>
      <h1 className="text-3xl font-semibold">Drive a school bus with us</h1>
      <p className="mt-2 text-stone-600">Paid CDL training · No CDL needed to apply</p>
      <div className="mx-auto mt-6 w-fit rounded-2xl border bg-white p-4 shadow-sm">
        {qr ? <img src={qr} alt="QR code: message Prime Pupil on WhatsApp" className="h-72 w-72 sm:h-80 sm:w-80" /> : <div className="flex h-72 w-72 items-center justify-center text-sm text-stone-400">Loading…</div>}
      </div>
      <ol className="mx-auto mt-6 max-w-sm space-y-2 text-left text-sm text-stone-700">
        <li><b>1.</b> Scan with your phone camera and send the message on WhatsApp</li>
        <li><b>2.</b> Tap the link we send back and apply (about a minute)</li>
        <li><b>3.</b> Our assistant takes it from there, in English or Spanish</li>
      </ol>
      {link && <a href={link} className="mt-6 inline-block rounded-lg bg-emerald-800 px-5 py-2.5 text-sm font-medium text-white hover:bg-emerald-900">On your phone? Tap here to open WhatsApp</a>}
    </div>
  );
}
