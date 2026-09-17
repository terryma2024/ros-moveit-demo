import type {
  CampaignHint,
  CampaignProjection,
} from "@/api/expert-validation-types";

type CampaignClient = {
  campaign(campaignId: string): Promise<CampaignProjection>;
  openEvents(after: number, apply: (event: CampaignHint) => void): () => void;
};

export class ExpertValidationStore {
  state: CampaignProjection | null = null;
  private closeEvents: (() => void) | null = null;
  private refresh: Promise<void> = Promise.resolve();

  constructor(private readonly client: CampaignClient) {}

  async reconnect(campaignId: string): Promise<void> {
    this.closeEvents?.();
    this.state = await this.client.campaign(campaignId);
    this.closeEvents = this.client.openEvents(this.state.sequence, (event) => {
      this.applyHint(event);
    });
  }

  private applyHint(event: CampaignHint): void {
    const current = this.state;
    if (current === null || event.campaign_id !== current.campaign_id) return;
    if (event.sequence <= current.sequence) return;
    if (event.sequence !== current.sequence + 1) {
      this.refresh = this.client.campaign(current.campaign_id).then((campaign) => {
        if (this.state?.campaign_id === campaign.campaign_id) this.state = campaign;
      });
      return;
    }
    // Events are hints only: advance the cursor but preserve the HTTP projection.
    this.state = { ...current, sequence: event.sequence };
  }

  settled(): Promise<void> {
    return this.refresh;
  }

  close(): void {
    this.closeEvents?.();
    this.closeEvents = null;
  }
}
