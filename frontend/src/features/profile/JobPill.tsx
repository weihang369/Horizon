// Background job pill (STATE-02): foundation stub (Builder B replaces it). Owner: EE (stub).
import { useActiveJobs } from "../../client/hooks";

export function JobPill() {
  const jobs = useActiveJobs().data ?? [];
  if (!jobs.length) return null;
  const j = jobs[0];
  return (
    <div role="status" style={{ position: "fixed", bottom: 16, right: 16, font: "600 12px/1 var(--font-mono)", padding: "6px 10px", background: "var(--ink-700)", color: "var(--paper-50)" }}>
      {j.kind} · {Math.round(j.progress * 100)}%{jobs.length > 1 ? ` · +${jobs.length - 1}` : ""}
    </div>
  );
}
