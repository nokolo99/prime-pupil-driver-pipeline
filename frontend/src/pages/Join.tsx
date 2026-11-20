import { useEffect, useState } from "react";
import QRCode from "qrcode";
import { api } from "../api";

// Demo setup screen (not part of the product): scan to message Prime Pupil on WhatsApp once.
// That first message opens WhatsApp's 24-hour window, so our messages can reach them after they apply.
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
      <h1 className="text-3xl font-semibold">Scan to connect on WhatsApp</h1>
      <p className="mt-2 text-stone-600">Send the message that pops up so we can start messaging you.</p>
      <div className="mx-auto mt-6 w-fit rounded-2xl border bg-white p-4 shadow-sm">
        {qr ? <img src={qr} alt="QR code: message Prime Pupil on WhatsApp" className="h-72 w-72 sm:h-80 sm:w-80" /> : <div className="flex h-72 w-72 items-center justify-center text-sm text-stone-400">Loading…</div>}
      </div>
      {link && <a href={link} className="mt-6 inline-block rounded-lg bg-emerald-800 px-5 py-2.5 text-sm font-medium text-white hover:bg-emerald-900">On your phone? Tap here to open WhatsApp</a>}
    </div>
  );
}
