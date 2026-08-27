import type { TaskRunSummary } from "@/api/task-types";

function statusColor(status: string): string {
  if (status === "SUCCEEDED" || status === "REACHABLE") return "border-emerald-700 bg-emerald-950/40";
  if (status === "RUNNING") return "border-cyan-600 bg-cyan-950/40";
  if (status === "PENDING") return "border-slate-700 bg-slate-900";
  return "border-rose-700 bg-rose-950/40";
}

export function TaskProgress({ run, currentPhase }: { run?: TaskRunSummary; currentPhase?: string }) {
  if (!run) return <p className="text-sm text-slate-400">No task run has been started.</p>;
  return <section className="space-y-3" aria-label="Task progress">
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
      <strong>{run.run_id}</strong><span>{run.status}</span>
      {currentPhase && <span className="text-cyan-400">phase {currentPhase}</span>}
      {run.first_shared_failure && <span className="text-rose-400">shared failure {run.first_shared_failure}</span>}
    </div>
    <ol className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
      {run.points.map((point) => <li key={point.id} className={`rounded border p-3 text-sm ${statusColor(point.status)}`}>
        <div className="font-medium">{point.id} — {point.status}</div>
        <div className="mt-1 space-x-2 text-xs text-slate-400">
          {point.reachability_status && <span>{point.reachability_status}</span>}
          {point.reset_epoch != null && <span>reset epoch {point.reset_epoch}</span>}
        </div>
        {point.failure_code && <div className="mt-2 text-xs text-rose-300">{point.failure_code}</div>}
      </li>)}
    </ol>
  </section>;
}
