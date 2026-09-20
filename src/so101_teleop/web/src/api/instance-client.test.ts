import { expect, test, vi } from "vitest";

import { InstanceClient, authorityHeaders, type InstanceProof } from "./instance-client";

const PROOF: InstanceProof = { instance_id: "i1", proof: "secret-proof", domain: "teleop" };

function jsonResponse(body: unknown, ok = true, status = 200): Response {
  return { ok, status, json: async () => body } as unknown as Response;
}

test("registration returns a server-issued proof without touching storage", async () => {
  const fetcher = vi.fn(async () => jsonResponse(PROOF));
  const client = new InstanceClient("http://127.0.0.1:8000", fetcher);
  const proof = await client.register("teleop");
  expect(proof.instance_id).toBe("i1");
  expect(fetcher).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/control/instances",
    expect.objectContaining({ method: "POST" }),
  );
  expect(globalThis.localStorage?.length ?? 0).toBe(0);
  expect(globalThis.sessionStorage?.length ?? 0).toBe(0);
});

test("a failed registration is a structured refusal, never a silent success", async () => {
  const client = new InstanceClient("http://127.0.0.1:8000", async () =>
    jsonResponse({ code: "SERVICE_NOT_COMPOSED" }, false, 503),
  );
  await expect(client.register("teleop")).rejects.toThrow("INSTANCE_REGISTER_FAILED: 503");
});

test("the channel handshake binds the revision the server returned", async () => {
  const sent: string[] = [];
  const listeners = new Map<string, (event: unknown) => void>();
  const socket = {
    send: (payload: string) => sent.push(payload),
    close: vi.fn(),
    addEventListener: (name: string, handler: (event: unknown) => void) => listeners.set(name, handler),
  } as unknown as WebSocket;
  const client = new InstanceClient("http://127.0.0.1:8000");
  const pending = client.connect(PROOF, {
    origin: "http://127.0.0.1:8000",
    webSocketFactory: () => socket,
  });
  listeners.get("open")?.({});
  expect(JSON.parse(sent[0])).toEqual({ proof: "secret-proof", origin: "http://127.0.0.1:8000" });
  listeners.get("message")?.({ data: JSON.stringify({ instance_id: "i1", revision: 3, domain: "teleop" }) });
  await expect(pending).resolves.toEqual({ instance_id: "i1", revision: 3, domain: "teleop" });
});

test("a rejected handshake surfaces the server code", async () => {
  const listeners = new Map<string, (event: unknown) => void>();
  const socket = {
    send: vi.fn(),
    close: vi.fn(),
    addEventListener: (name: string, handler: (event: unknown) => void) => listeners.set(name, handler),
  } as unknown as WebSocket;
  const client = new InstanceClient("http://127.0.0.1:8000");
  const pending = client.connect(PROOF, { webSocketFactory: () => socket });
  listeners.get("message")?.({ data: JSON.stringify({ code: "INSTANCE_PROOF_MISMATCH: i1" }) });
  await expect(pending).rejects.toThrow("INSTANCE_PROOF_MISMATCH");
});

test("every mutation carries the four authority headers", async () => {
  const fetcher = vi.fn(async () => jsonResponse({ code: "OK", succeeded: true }));
  const client = new InstanceClient("http://127.0.0.1:8000", fetcher);
  await client.post(
    "/gripper/execute",
    { command_id: "c1" },
    { instanceId: "i1", proof: "p1", channelRevision: 2, executionGeneration: 7 },
  );
  const [call] = fetcher.mock.calls as unknown as Array<[string, RequestInit]>;
  const init = call[1];
  expect(init.headers).toMatchObject({
    "X-SO101-Instance-ID": "i1",
    "X-SO101-Instance-Proof": "p1",
    "X-SO101-Channel-Revision": "2",
    "X-SO101-Execution-Generation": "7",
  });
  expect(authorityHeaders({ instanceId: "i1", proof: "p1", channelRevision: 2, executionGeneration: 7 }))
    .toHaveProperty("X-SO101-Instance-Proof", "p1");
});

test("renewal carries the instance authority headers the server checks", async () => {
  const { createHttpTransport } = await import("./domain-transport");
  const calls: Array<[string, RequestInit]> = [];
  const fetchImpl = async (input: string, init?: RequestInit) => {
    calls.push([input, init ?? {}]);
    if (input.endsWith("/health/live")) {
      return jsonResponse({ service_epoch: "e1" });
    }
    return jsonResponse({ ok: true });
  };
  const transport = createHttpTransport("teleop", {
    baseUrl: "http://127.0.0.1:8000",
    fetchImpl: fetchImpl as unknown as typeof fetch,
  });
  transport.setAuthority?.({
    instanceId: "i1",
    proof: "p1",
    channelRevision: 2,
    executionGeneration: 3,
  });
  await transport.renew();
  const [, init] = calls[calls.length - 1];
  expect(init.headers).toMatchObject({
    "X-SO101-Instance-ID": "i1",
    "X-SO101-Instance-Proof": "p1",
    "X-SO101-Channel-Revision": "2",
    "X-SO101-Execution-Generation": "3",
  });
});
