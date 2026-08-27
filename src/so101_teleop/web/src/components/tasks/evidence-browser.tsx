import type { TaskArtifact, TaskRunSummary } from "@/api/task-types";

export function artifactLabel(artifact: TaskArtifact): string {
  const name = artifact.name.toLowerCase();
  if (name === "rgb.png") return "RGB PNG";
  if (name === "full-cloud.ply") return "Full PLY";
  if (name === "cup-cloud.ply") return "Cup PLY";
  if (name.includes("point-cloud") && name.endsWith(".png")) return "Point-cloud screenshot";
  if (name.includes("viewer") && name.endsWith(".png")) return "Viewer screenshot";
  if (name.includes("reachability") && name.endsWith(".json")) return "Reachability JSON";
  if (name.includes("manifest") && name.endsWith(".json")) return "Dynamic manifest";
  if (name.includes("physical") && name.endsWith(".json")) return "Physical outcome";
  if (name.endsWith(".log") || name.endsWith(".txt")) return "Task log";
  if (name.endsWith(".json")) return "JSON evidence";
  return artifact.media_type.startsWith("image/") ? "Image evidence" : "Download evidence";
}

export function EvidenceBrowser({
  run,
  artifactUrl,
}: {
  run?: TaskRunSummary;
  artifactUrl: (artifactId: string) => string;
}) {
  if (!run) return <p className="text-sm text-slate-400">No run evidence is available.</p>;
  return <section className="space-y-3" aria-label="Task evidence browser">
    {run.points.map((point) => <article key={point.id} className="rounded border border-slate-700 p-3">
      <div className="flex items-center justify-between gap-3">
        <strong className="text-sm">{point.id}</strong>
        <span className="text-xs text-slate-400">{point.artifacts?.length ?? 0} registered artifacts</span>
      </div>
      {point.artifacts?.length ? <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {point.artifacts.map((artifact) => <li key={artifact.artifact_id} className="rounded bg-slate-950 p-2 text-xs">
          <a className="font-medium text-cyan-400 underline" href={artifactUrl(artifact.artifact_id)} download>{artifactLabel(artifact)}</a>
          <div className="mt-1 text-slate-500">{artifact.name} · {artifact.byte_size.toLocaleString()} B</div>
          <div className="truncate text-slate-600" title={artifact.sha256}>sha256 {artifact.sha256}</div>
        </li>)}
      </ul> : <p className="mt-2 text-xs text-slate-500">No registered evidence for this point.</p>}
    </article>)}
  </section>;
}
