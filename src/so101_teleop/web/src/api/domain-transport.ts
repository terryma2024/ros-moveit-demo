/**
 * The real browser transport for one domain runtime.
 *
 * It uses the same origin as the page: instance registration, the channel handshake, the
 * authoritative snapshot, the domain event stream and the mutation endpoint. Renewal uses the
 * domain's own lease endpoint with the instance authority headers. No proof is ever written to
 * storage, a URL or a log line.
 */
import {
  InstanceClient,
  type ChannelBinding,
  type ControllerAuthority,
  type DomainName,
  type InstanceProof,
} from "@/api/instance-client";
import type { DomainTransport, RuntimeSnapshot } from "@/state/domain-runtime";

export type DomainEndpoints = {
  snapshotPath: string;
  eventsPath: string;
  renewPath: string;
  renewBody: Record<string, unknown>;
};

export const DOMAIN_ENDPOINTS: Record<DomainName, DomainEndpoints> = {
  teleop: { snapshotPath: "/snapshot", eventsPath: "/telemetry", renewPath: "/control/lease/renew", renewBody: {} },
  validation: {
    snapshotPath: "/expert-validation/campaigns",
    eventsPath: "/expert-validation/events",
    renewPath: "/expert-validation/lease",
    renewBody: {},
  },
};

function sequenceOf(payload: unknown): number {
  if (payload && typeof payload === "object" && "sequence" in payload) {
    const value = (payload as { sequence?: unknown }).sequence;
    if (typeof value === "number") return value;
  }
  if (payload && typeof payload === "object" && "revision" in payload) {
    const value = (payload as { revision?: unknown }).revision;
    if (typeof value === "number") return value;
  }
  return 0;
}

export function createHttpTransport(
  domain: DomainName,
  options: {
    baseUrl?: string;
    client?: InstanceClient;
    fetchImpl?: (input: string, init?: RequestInit) => Promise<Response>;
    webSocketFactory?: (url: string) => WebSocket;
    endpoints?: DomainEndpoints;
  } = {},
): DomainTransport {
  const baseUrl = options.baseUrl ?? globalThis.location?.origin ?? "http://127.0.0.1:8000";
  const fetchImpl = options.fetchImpl ?? ((input, init) => fetch(input, init));
  const client = options.client ?? new InstanceClient(baseUrl, fetchImpl);
  const endpoints = options.endpoints ?? DOMAIN_ENDPOINTS[domain];
  let socket: WebSocket | null = null;
  let epoch = "unknown";

  return {
    register: (name: DomainName): Promise<InstanceProof> => client.register(name),
    connect: (proof: InstanceProof): Promise<ChannelBinding> =>
      client.connect(proof, { origin: baseUrl, webSocketFactory: options.webSocketFactory }),
    async snapshot(): Promise<RuntimeSnapshot> {
      const live = await fetchImpl(`${baseUrl}/health/live`, { method: "GET" });
      if (live.ok) {
        const body = (await live.json().catch(() => ({}))) as { service_epoch?: string };
        epoch = body.service_epoch ?? epoch;
      }
      const response = await fetchImpl(`${baseUrl}${endpoints.snapshotPath}`, { method: "GET" });
      if (!response.ok) throw new Error(`SNAPSHOT_FAILED: ${response.status}`);
      const payload = (await response.json()) as unknown;
      return {
        sequence: sequenceOf(payload),
        serviceEpoch: epoch,
        executionGeneration: 0,
        payload: payload as RuntimeSnapshot["payload"],
      };
    },
    subscribe(handler: (event: RuntimeSnapshot) => void): () => void {
      const url = `${baseUrl.replace(/^http/, "ws")}${endpoints.eventsPath}`;
      socket = (options.webSocketFactory ?? ((target: string) => new WebSocket(target)))(url);
      socket.addEventListener("message", (event: MessageEvent<string>) => {
        let payload: unknown;
        try {
          payload = JSON.parse(String(event.data));
        } catch {
          return;
        }
        handler({
          sequence: sequenceOf(payload),
          serviceEpoch: epoch,
          executionGeneration: 0,
          payload: payload as RuntimeSnapshot["payload"],
        });
      });
      return () => {
        try {
          socket?.close();
        } catch {
          /* already closed */
        }
        socket = null;
      };
    },
    async renew(): Promise<void> {
      const response = await fetchImpl(`${baseUrl}${endpoints.renewPath}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(endpoints.renewBody),
      });
      if (!response.ok) throw new Error(`LEASE_RENEW_FAILED: ${response.status}`);
    },
    post: (path: string, body: Record<string, unknown>, authority: ControllerAuthority) =>
      client.post(path, body, authority),
    close(): void {
      try {
        socket?.close();
      } catch {
        /* already closed */
      }
      socket = null;
    },
  };
}
