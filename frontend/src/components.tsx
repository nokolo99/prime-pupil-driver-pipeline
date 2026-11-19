import { label, STATUS_STYLE } from "./api";

export function StatusPill({ status }: { status: string }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_STYLE[status] ?? "bg-stone-100"}`}>{label(status)}</span>;
}
