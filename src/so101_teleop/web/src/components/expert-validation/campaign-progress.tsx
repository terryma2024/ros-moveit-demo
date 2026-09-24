import type { CampaignProjection } from "@/api/expert-validation-types";
import { Button } from "@/components/ui/button";

export type CampaignView = Pick<CampaignProjection, "campaign_id" | "sequence"> &
  Partial<Omit<CampaignProjection, "campaign_id" | "sequence">>;

export function CampaignProgress({ campaign, selectedPointId, onSelect, onCancel }: {
  campaign: CampaignView;
  selectedPointId?: string;
  onSelect?: (pointId: string) => void;
  onCancel?: () => void;
}) {
  const evaluated = campaign.evaluated ?? 0;
  const succeeded = campaign.valid_succeeded ?? 0;
  return (
    <section aria-label="Campaign progress" className="validation-progress min-w-0 space-y-3 rounded-lg border border-border bg-card p-4 text-card-foreground [overflow-wrap:anywhere]">
      <header>
        <h2 className="text-lg font-semibold">Campaign {campaign.campaign_id}</h2>
        <p>{campaign.execution_mode ?? "UNKNOWN"} · {campaign.status ?? "RUNNING"} · sequence {campaign.sequence}</p>
        {onCancel && ["STARTED", "RUNNING", "EXECUTING", "CANCELLING"].includes(campaign.status ?? "")
          ? <Button variant="outline" onClick={onCancel}>Cancel campaign</Button> : null}
      </header>
      <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <span>Requested {campaign.requested ?? 0}</span>
        <span>Evaluated {evaluated}</span>
        <span>Execution started {campaign.execution_started ?? 0}</span>
        <span>First pass {succeeded} / {evaluated} valid</span>
        <span>Failed {campaign.valid_failed ?? 0}</span>
        <span>Indeterminate {campaign.indeterminate ?? 0}</span>
        <span>Unrun {campaign.not_executed ?? 0}</span>
      </div>
      {campaign.execution_mode === "ADAPTIVE" ? (
        <>
          <p>Infra attempts {campaign.infra_attempts ?? 0}</p>
          <p className="text-muted-foreground">
            Resource observations only: {Object.entries(campaign.resource_observations ?? {})
              .map(([key, value]) => `${key}=${String(value)}`)
              .join(", ") || "none"}
          </p>
        </>
      ) : null}
      {campaign.broker && !campaign.broker.available ? (
        <p className="text-warning">Broker degraded: {campaign.broker.reason ?? "UNKNOWN"}</p>
      ) : <p>Broker healthy</p>}
      {(campaign.levels_used?.length ?? 0) > 0 ? (
        <p>Levels used {campaign.levels_used?.map((level) => `W${level}`).join(" -> ")}</p>
      ) : null}
      {campaign.fallback_history?.map((transition, index) => (
        <p key={index}>
          W{String(transition.from_count)} -&gt; W{String(transition.to_count)}: {String(transition.reason)}
        </p>
      ))}
      <h3 className="font-semibold">Point execution results</h3>
      <div role="group" aria-label="Point execution results" className="validation-point-results gap-2">
        {campaign.points?.map((point) => (
          <button
            key={point.point_id}
            type="button"
            aria-label={`Point ${point.display_id ?? point.point_id}`}
            aria-pressed={selectedPointId === point.point_id}
            onClick={() => onSelect?.(point.point_id)}
            className="min-w-0 rounded border border-border bg-background p-2 text-left text-sm aria-pressed:border-primary aria-pressed:bg-sidebar-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring"
          >
            <span className="block font-semibold">{point.display_id ?? point.point_id}</span>
            <span className="block">{point.status ?? "UNKNOWN"}</span>
            {point.reason ? <span className="block text-muted-foreground">{point.reason}</span> : null}
          </button>
        ))}
      </div>
      <div className="grid gap-2 md:grid-cols-2">
        {campaign.workers?.map((worker) => (
          <article key={worker.worker_id} aria-label={`Worker ${worker.worker_id}`} className="rounded border border-border bg-background p-3">
            <h3>{worker.worker_id} · generation {worker.generation}</h3>
            <p>{worker.state}{worker.current_point_id ? ` · ${worker.current_point_id}` : ""}</p>
            <p>Leases {worker.lease_count}{worker.max_points_per_worker == null ? "" : ` / ${worker.max_points_per_worker}`}</p>
            {worker.recovery_result ? <p>Recovery {worker.recovery_result}</p> : null}
            {worker.quarantine_reason ? <p>Quarantine {worker.quarantine_reason}</p> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
