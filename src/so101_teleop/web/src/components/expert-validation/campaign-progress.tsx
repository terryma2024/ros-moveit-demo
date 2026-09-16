import type { CampaignProjection } from "@/api/expert-validation-types";

export type CampaignView = Pick<CampaignProjection, "campaign_id" | "sequence"> &
  Partial<Omit<CampaignProjection, "campaign_id" | "sequence">>;

export function CampaignProgress({ campaign }: { campaign: CampaignView }) {
  const evaluated = campaign.evaluated ?? 0;
  const succeeded = campaign.valid_succeeded ?? 0;
  return (
    <section aria-label="Campaign progress" className="space-y-3 rounded-lg border border-slate-700 bg-slate-900 p-4">
      <header>
        <h2 className="text-lg font-semibold">Campaign {campaign.campaign_id}</h2>
        <p>{campaign.execution_mode ?? "UNKNOWN"} · {campaign.status ?? "RUNNING"} · sequence {campaign.sequence}</p>
      </header>
      <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <span>Requested {campaign.requested ?? 0}</span>
        <span>Evaluated {evaluated}</span>
        <span>Execution started {campaign.execution_started ?? 0}</span>
        <span>First pass {succeeded} / {evaluated} valid</span>
      </div>
      {campaign.broker && !campaign.broker.available ? (
        <p className="text-amber-300">Broker degraded: {campaign.broker.reason ?? "UNKNOWN"}</p>
      ) : <p>Broker healthy</p>}
      {(campaign.levels_used?.length ?? 0) > 0 ? (
        <p>Levels used {campaign.levels_used?.map((level) => `W${level}`).join(" -> ")}</p>
      ) : null}
      {campaign.fallback_history?.map((transition, index) => (
        <p key={index}>
          W{String(transition.from_count)} -&gt; W{String(transition.to_count)}: {String(transition.reason)}
        </p>
      ))}
      <div className="grid gap-2 md:grid-cols-2">
        {campaign.workers?.map((worker) => (
          <article key={worker.worker_id} aria-label={`Worker ${worker.worker_id}`} className="rounded border border-slate-600 p-3">
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
