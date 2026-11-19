import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Candidate } from "../api";

export default function CandidateDetail() {
  const { id } = useParams();
  const [data, setData] = useState<{ candidate: Candidate } | null>(null);
  useEffect(() => { api<{ candidate: Candidate }>(`/candidates/${id}`).then(setData); }, [id]);
  if (!data) return <p className="text-stone-500">Loading…</p>;
  const c = data.candidate;
  return <h2 className="text-lg font-semibold">{c.first_name} {c.last_name} · {c.stage} · {c.status}</h2>;
}
