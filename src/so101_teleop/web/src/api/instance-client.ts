/**
 * Document-instance transport.
 *
 * A document registers itself, proves possession of the server-generated proof on a live
 * channel, and then carries four authority headers on every mutation. The proof lives in
 * this module's memory only: it is never written to storage, never put in a URL, and never
 * logged. Registration grants no control — control still needs the domain lease and the
 * server's controller binding.
 */
import type { components } from "@/api/unified-schema";

export type InstanceProof = components["schemas"]["InstanceProofResponse"];
export type DomainName = "teleop" | "validation";

/**
 * The live channel revision a handshake bound. The channel handshake message is not
 * expressible in an OpenAPI document (it is a WebSocket frame), so this shape is declared
 * here and mirrors the server's `ChannelBinding` dataclass field for field.
 */
export type ChannelBinding = { instance_id: string; revision: number; domain: string };

export type ControllerAuthority = {
  instanceId: string;
  proof: string;
  channelRevision: number;
  executionGeneration: number;
};

export const INSTANCE_ID_HEADER = "X-SO101-Instance-ID";
export const INSTANCE_PROOF_HEADER = "X-SO101-Instance-Proof";
export const CHANNEL_REVISION_HEADER = "X-SO101-Channel-Revision";
export const EXECUTION_GENERATION_HEADER = "X-SO101-Execution-Generation";

export function authorityHeaders(authority: ControllerAuthority): Record<string, string> {
  return {
    [INSTANCE_ID_HEADER]: authority.instanceId,
    [INSTANCE_PROOF_HEADER]: authority.proof,
    [CHANNEL_REVISION_HEADER]: String(authority.channelRevision),
    [EXECUTION_GENERATION_HEADER]: String(authority.executionGeneration),
  };
}

export type Fetcher = (input: string, init?: RequestInit) => Promise<Response>;

export class InstanceClient {
  constructor(
    private readonly baseUrl: string,
    private readonly fetchImpl: Fetcher = (input, init) => fetch(input, init),
  ) {}

  async register(domain: DomainName): Promise<InstanceProof> {
    const response = await this.fetchImpl(`${this.baseUrl}/control/instances`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ domain }),
    });
    if (!response.ok) {
      throw new Error(`INSTANCE_REGISTER_FAILED: ${response.status}`);
    }
    return (await response.json()) as InstanceProof;
  }

  async connect(
    proof: InstanceProof,
    options: { origin?: string; webSocketFactory?: (url: string) => WebSocket } = {},
  ): Promise<ChannelBinding> {
    const origin = options.origin ?? this.baseUrl;
    const factory =
      options.webSocketFactory ??
      ((url: string) => new WebSocket(url));
    const socketUrl = `${this.baseUrl.replace(/^http/, "ws")}/control/instances/${proof.instance_id}/channel`;
    const socket = factory(socketUrl);
    return await new Promise<ChannelBinding>((resolve, reject) => {
      const fail = (error: Error) => {
        try {
          socket.close();
        } catch {
          /* the socket is already gone */
        }
        reject(error);
      };
      socket.addEventListener("open", () => {
        socket.send(JSON.stringify({ proof: proof.proof, origin }));
      });
      socket.addEventListener("message", (event: MessageEvent<string>) => {
        let payload: { instance_id?: string; revision?: number; domain?: string; code?: string };
        try {
          payload = JSON.parse(String(event.data));
        } catch (error) {
          fail(new Error(`CHANNEL_HANDSHAKE_UNREADABLE: ${String(error)}`));
          return;
        }
        if (payload.code) {
          fail(new Error(payload.code));
          return;
        }
        if (!payload.instance_id || typeof payload.revision !== "number") {
          fail(new Error("CHANNEL_HANDSHAKE_INCOMPLETE"));
          return;
        }
        resolve({
          instance_id: payload.instance_id,
          revision: payload.revision,
          domain: payload.domain ?? proof.domain,
        });
      });
      socket.addEventListener("error", () => fail(new Error("CHANNEL_CONNECT_FAILED")));
    });
  }

  async post(
    path: string,
    body: Record<string, unknown>,
    authority: ControllerAuthority,
  ): Promise<unknown> {
    const response = await this.fetchImpl(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", ...authorityHeaders(authority) },
      body: JSON.stringify(body),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok && !(payload as { code?: string }).code) {
      throw new Error(`COMMAND_FAILED: ${response.status}`);
    }
    return payload;
  }
}
