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
  authorityHeaders,
  type ChannelBinding,
  type ControllerAuthority,
  type DomainName,
  type InstanceProof,
} from "@/api/instance-client";
import type { DomainTransport, LeaseIdentity, RuntimeSnapshot } from "@/state/domain-runtime";

export type RenewTarget = {
  method: string;
  path: string;
  body: Record<string, unknown>;
};

export type DomainEndpoints = {
  snapshotPath: string;
  eventsPath: string;
  renewPath: string;
  renewBody: Record<string, unknown>;
  /**
   * Optional lease-aware renewal. A domain that renews a specific lease by id cannot express that
   * with a static path, and the validation domain renews exactly that way; returning null means
   * there is nothing to renew.
   */
  renewTarget?: (lease: LeaseIdentity | null) => RenewTarget | null;
};

export const DOMAIN_ENDPOINTS: Record<DomainName, DomainEndpoints> = {
  teleop: { snapshotPath: "/snapshot", eventsPath: "/telemetry", renewPath: "/control/lease/renew", renewBody: {} },
  validation: {
    snapshotPath: "/expert-validation/campaigns",
    eventsPath: "/expert-validation/events",
    renewPath: "/expert-validation/lease",
    renewBody: {},
    renewTarget: (lease) =>
      // The guard is on the shape, not only on absence: a partial lease once produced
      // PUT /expert-validation/lease/undefined, which no server can act on.
      lease === null || typeof lease.lease_id !== "string" || lease.lease_id === ""
        ? null
        : {
            method: "PUT",
            path: `/expert-validation/lease/${encodeURIComponent(lease.lease_id)}`,
            body: {
              service_session_id: lease.service_session_id,
              generation: lease.generation,
            },
          },
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
  // The server checks instance authority on renewal, so the transport has to hold the authority the
  // runtime adopted; without it a renewal is refused with CONTROLLER_INSTANCE_REQUIRED.
  let authority: ControllerAuthority | null = null;
  let heldLease: LeaseIdentity | null = null;

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
    setAuthority(next: ControllerAuthority | null): void {
      authority = next;
    },
    setLease(next: LeaseIdentity | null): void {
      heldLease = next;
    },
    async renew(): Promise<Partial<LeaseIdentity> | void> {
      const target = endpoints.renewTarget
        ? endpoints.renewTarget(heldLease)
        : { method: "POST", path: endpoints.renewPath, body: endpoints.renewBody };
      if (target === null) return undefined;
      const response = await fetchImpl(`${baseUrl}${target.path}`, {
        method: target.method,
        headers: {
          "content-type": "application/json",
          ...(authority ? authorityHeaders(authority) : {}),
        },
        body: JSON.stringify(target.body),
      });
      if (!response.ok) throw new Error(`LEASE_RENEW_FAILED: ${response.status}`);
      const payload = (await response.json().catch(() => null)) as Partial<LeaseIdentity> | null;
      // The validation endpoint answers with the renewed lease; the teleop endpoint answers with a
      // CommandResult. Only a lease-shaped body is handed back for validation.
      if (payload && typeof payload.lease_id === "string" && typeof payload.generation === "number") {
        return payload;
      }
      return undefined;
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
