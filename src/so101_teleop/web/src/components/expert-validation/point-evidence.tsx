import type { ArtifactProjection, PointProjection } from "@/api/expert-validation-types";

type PointView = Pick<PointProjection, "point_id"> & Partial<PointProjection>;
type Artifact = Pick<ArtifactProjection, "artifact_id" | "role" | "media_type">;

export function PointEvidence({ point, artifacts }: { point: PointView; artifacts: Artifact[] }) {
  return (
    <section aria-label={`Evidence for ${point.display_id ?? point.point_id}`} className="space-y-2 rounded-lg border border-border bg-card p-4 text-card-foreground">
      <h2>Point evidence · {point.display_id ?? point.point_id}</h2>
      <p>{point.status ?? "UNKNOWN"}{point.reason ? ` · ${point.reason}` : ""}</p>
      {point.attempts?.map((attempt) => (
        <p key={attempt.attempt_id ?? attempt.generation}>
          {attempt.kind === "FULL_RESTART_RETRY" ? "FULL_RESTART" : "First-pass"} attempt {attempt.generation}: {attempt.status}
        </p>
      ))}
      {artifacts.length === 0 ? <p>No committed evidence available</p> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {artifacts.map((artifact) => {
          const url = `/expert-validation/artifacts/${encodeURIComponent(artifact.artifact_id)}`;
          return artifact.media_type.startsWith("image/") ? (
            <figure key={artifact.artifact_id}>
              <img src={url} alt={artifact.role} className="max-h-72 rounded" />
              <figcaption>{artifact.role}</figcaption>
            </figure>
          ) : (
            <a key={artifact.artifact_id} href={url} download className="text-link underline">
              Download {artifact.role}
            </a>
          );
        })}
      </div>
    </section>
  );
}
