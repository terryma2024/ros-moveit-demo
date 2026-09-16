import { createCommandId } from "@/lib/command-id";
import type {
  Capabilities,
  CampaignHint,
  CampaignProjection,
  Lease,
  LeaseAuthority,
  Manifest,
  PreflightInput,
  PreflightReceipt,
  StartCampaignInput,
} from "./expert-validation-types";

type Fetcher = typeof fetch;
type CommandId = () => string;
type EventHandler = (event: CampaignHint) => void;
type CampaignHandler = (campaign: CampaignProjection) => void;
type SocketFactory = (url: string) => WebSocket;

const browserFetch: Fetcher = (input, init) => fetch(input, init);
const browserSocket: SocketFactory = (url) => new WebSocket(url);

export class ExpertValidationApiError extends Error {
  readonly name = "ExpertValidationApiError";

  constructor(readonly code: string, readonly status: number) {
    super(code);
  }
}

export class ExpertValidationClient {
  constructor(
    private readonly fetcher: Fetcher = browserFetch,
    private readonly commandId: CommandId = createCommandId,
    private readonly socketFactory: SocketFactory = browserSocket,
  ) {}

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const response = await this.fetcher(path, init);
    const body = (await response.json()) as T | { code?: string };
    if (!response.ok) {
      const code = typeof body === "object" && body !== null && "code" in body
        ? String(body.code)
        : `HTTP_${response.status}`;
      throw new ExpertValidationApiError(code, response.status);
    }
    return body as T;
  }

  private post<T>(path: string, body: Record<string, unknown>): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  }

  capabilities(): Promise<Capabilities> {
    return this.request<Capabilities>("/expert-validation/capabilities");
  }

  acquireLease(serviceSessionId: string): Promise<Lease> {
    return this.post<Lease>("/expert-validation/lease", {
      service_session_id: serviceSessionId,
    });
  }

  createManifest(totalPoints: number): Promise<Manifest> {
    return this.post<Manifest>("/expert-validation/manifests", {
      total_points: totalPoints,
    });
  }

  preflight(input: PreflightInput, lease: LeaseAuthority): Promise<PreflightReceipt> {
    return this.post<PreflightReceipt>("/expert-validation/campaigns/preflight", {
      ...input,
      ...lease,
    });
  }

  startCampaign(
    input: StartCampaignInput,
    lease: LeaseAuthority,
  ): Promise<CampaignProjection> {
    return this.post<CampaignProjection>("/expert-validation/campaigns", {
      ...input,
      ...lease,
      command_id: this.commandId(),
    });
  }

  campaign(campaignId: string): Promise<CampaignProjection> {
    return this.request<CampaignProjection>(
      `/expert-validation/campaigns/${encodeURIComponent(campaignId)}`,
    );
  }

  async restoreCampaign(): Promise<CampaignProjection | null> {
    const campaigns = await this.request<CampaignProjection[]>(
      "/expert-validation/campaigns",
    );
    return campaigns.at(-1) ?? null;
  }

  watchCampaign(
    campaignId: string,
    after: number,
    apply: CampaignHandler,
  ): () => void {
    let sequence = after;
    let closed = false;
    let refresh = Promise.resolve();
    const stop = this.openEvents(after, (event) => {
      if (closed || event.campaign_id !== campaignId || event.sequence <= sequence) return;
      if (event.sequence === sequence + 1) {
        sequence = event.sequence;
        return;
      }
      refresh = refresh.then(async () => {
        const campaign = await this.campaign(campaignId);
        if (!closed && campaign.sequence > sequence) {
          sequence = campaign.sequence;
          apply(campaign);
        }
      });
    });
    return () => {
      closed = true;
      stop();
    };
  }

  retry(
    campaignId: string,
    pointIds: string[],
    lease: LeaseAuthority,
    confirmation: string,
  ): Promise<CampaignProjection> {
    return this.post<CampaignProjection>(
      `/expert-validation/campaigns/${encodeURIComponent(campaignId)}/full-restart-retries`,
      {
        ...lease,
        command_id: this.commandId(),
        point_ids: pointIds,
        confirmation,
      },
    );
  }

  cancel(campaignId: string, lease: LeaseAuthority): Promise<CampaignProjection> {
    return this.post<CampaignProjection>(
      `/expert-validation/campaigns/${encodeURIComponent(campaignId)}/cancel`,
      { ...lease, command_id: this.commandId() },
    );
  }

  openEvents(after: number, apply: EventHandler): () => void {
    const scheme = globalThis.location?.protocol === "https:" ? "wss:" : "ws:";
    const host = globalThis.location?.host ?? "127.0.0.1";
    const socket = this.socketFactory(
      `${scheme}//${host}/expert-validation/events?after=${after}`,
    );
    socket.addEventListener("message", (message) => {
      apply(JSON.parse(String(message.data)) as CampaignHint);
    });
    return () => socket.close();
  }
}
