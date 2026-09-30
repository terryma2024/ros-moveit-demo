import { describe, expect, it } from "vitest";

import { HeadCameraClient } from "./head-camera-client";

type Call = { path: string; init: RequestInit };

function fetcher(responses: Array<{ status: number; body: unknown }>, calls: Call[]): typeof fetch {
  return (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ path: String(input), init: init ?? {} });
    const next = responses.shift() ?? { status: 200, body: {} };
    return new Response(JSON.stringify(next.body), { status: next.status });
  }) as typeof fetch;
}

const authority = { leaseId: "lease-1", sessionId: "session-1" } as never;

describe("HeadCameraClient", () => {
  it("reads the composed status without constructing anything", async () => {
    const calls: Call[] = [];
    const client = new HeadCameraClient(
      fetcher([{ status: 200, body: { available: true, detector_constructed: 0, runtime_id: "r1" } }], calls),
    );

    const status = await client.status();

    expect(status.detector_constructed).toBe(0);
    expect(calls[0]?.path).toBe("/teleop/head-camera/status");
  });

  it("sends a target angle and never the sealed interval", async () => {
    const calls: Call[] = [];
    const client = new HeadCameraClient(fetcher([{ status: 200, body: { state: "SUBMITTED" } }], calls));

    const result = await client.submitTarget(0.25, authority);

    expect(result.ok).toBe(true);
    expect(JSON.parse(String(calls[0]?.init.body))).toEqual({ target_rad: 0.25 });
  });

  it("reports a refusal by its code rather than retrying", async () => {
    const calls: Call[] = [];
    const client = new HeadCameraClient(
      fetcher([{ status: 409, body: { detail: { code: "HEAD_TARGET_OUT_OF_RANGE" } } }], calls),
    );

    const result = await client.submitTarget(99, authority);

    expect(result.ok).toBe(false);
    expect(result.code).toBe("HEAD_TARGET_OUT_OF_RANGE");
    expect(calls).toHaveLength(1);
  });

  it("reports a missing domain as unavailable instead of inventing a status", async () => {
    const client = new HeadCameraClient(fetcher([{ status: 503, body: {} }], []));

    await expect(client.status()).rejects.toThrow("HEAD_CAMERA_STATUS_503");
  });

  it("derives the stream url from the current origin", () => {
    const client = new HeadCameraClient(fetcher([], []));

    expect(client.streamUrl()).toMatch(/\/teleop\/head-camera\/stream$/);
  });
});
