import { createCommandId } from "@/lib/command-id";
import type {
  CampaignHint,
  CampaignProjection,
  LeaseAuthority,
  PreflightInput,
  PreflightReceipt,
  StartCampaignInput,
} from "./expert-validation-types";

type Fetcher = typeof fetch;
type CommandId = () => string;
type EventHandler = (event: CampaignHint) => void;
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
