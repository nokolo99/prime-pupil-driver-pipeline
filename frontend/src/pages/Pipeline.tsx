import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Candidate } from "../api";

export default function Pipeline() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  useEffect(() => { api<Candidate[]>("/candidates").then(setCandidates); }, []);

  return (
    <div>
      <h2 className="text-lg font-semibold mb-2">Pipeline ({candidates.length})</h2>
      <table className="w-full rounded-lg border bg-white text-sm">
        <thead className="text-left text-stone-500">
          <tr><th className="p-3">Name</th><th>Stage</th><th>Status</th><th>Language</th></tr>
        </thead>
        <tbody className="divide-y">
          {candidates.length === 0 && (
            <tr><td colSpan={4} className="p-4 text-stone-500">No candidates yet.</td></tr>
          )}
          {candidates.map((c) => (
            <tr key={c.id}>
              <td className="p-3"><Link className="text-emerald-800 hover:underline" to={`/candidates/${c.id}`}>{c.first_name} {c.last_name}</Link></td>
              <td>{c.stage}</td><td>{c.status}</td><td>{c.preferred_language}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
