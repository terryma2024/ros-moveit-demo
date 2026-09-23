import { useState } from "react";

import type { PointProjection } from "@/api/expert-validation-types";
import { Button } from "@/components/ui/button";
import type { CampaignView } from "./campaign-progress";

type PointView = Pick<PointProjection, "point_id"> & Partial<PointProjection>;

export function RetryPanel({
  campaign,
  onRetry,
}: {
  campaign: CampaignView & { points?: PointView[] };
  onRetry: (pointIds: string[], confirmation: string) => void | Promise<void>;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const enabled = campaign.batch_cleanup_complete === true && campaign.status !== "INFRA_FAILED";
  return (
    <section aria-label="Full restart retries" className="space-y-3 rounded-lg border border-border bg-card p-4 text-card-foreground">
      <h2>FULL_RESTART retries</h2>
      {campaign.points?.map((point) => {
        const eligible = enabled && point.status === "FAILED" && point.retry_eligible === true;
        return (
          <label key={point.point_id} className="mr-4 inline-flex items-center gap-2">
            <input
              type="checkbox"
              aria-label={`Retry ${point.display_id ?? point.point_id}`}
              disabled={!eligible}
              checked={selected.includes(point.point_id)}
              onChange={(event) => setSelected((current) => event.target.checked
                ? [...current, point.point_id]
                : current.filter((id) => id !== point.point_id))}
            />
            {point.display_id ?? point.point_id}
          </label>
        );
      })}
      <div>
        <Button disabled={!selected.length || !enabled} onClick={() => setConfirming(true)}>
          Retry selected with FULL_RESTART
        </Button>
      </div>
      {confirming ? (
        <div className="space-y-2">
          <label className="block">Confirmation
            <input aria-label="Confirmation" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} className="ml-2 px-2" />
          </label>
          <Button
            disabled={confirmation !== "CONFIRM FULL_RESTART RETRIES"}
            onClick={() => onRetry(selected, confirmation)}
          >
            Confirm retry
          </Button>
        </div>
      ) : null}
    </section>
  );
}
