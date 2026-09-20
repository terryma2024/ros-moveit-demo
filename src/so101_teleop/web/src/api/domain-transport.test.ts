/**
 * The validation domain renews a lease it holds: PUT /expert-validation/lease/{id} with the session
 * and generation. The transport used to POST a static, empty body to /expert-validation/lease - the
 * acquire endpoint - so every renewal was refused with 422 while the campaign was running.
 */
import { describe, expect, test } from "vitest";

import { createHttpTransport } from "./domain-transport";
import type { ControllerAuthority } from "./instance-client";

const AUTHORITY: ControllerAuthority = {
  instanceId: "i1",
  proof: "p1",
  channelRevision: 1,
  executionGeneration: 1,
};

describe("validation renewal", () => {
  test("renews the adopted lease with PUT on its own id", async () => {
    const calls: Array<{ url: string; method: string; body: unknown }> = [];
    const transport = createHttpTransport("validation", {
      baseUrl: "http://127.0.0.1:8800",
      fetchImpl: async (url, init) => {
        calls.push({ url, method: String(init?.method ?? "GET"), body: init?.body });
        return new Response(
          JSON.stringify({
            lease_id: "l1",
            service_session_id: "s1",
            generation: 2,
            expires_monotonic_ns: 10 ** 15,
          }),
          { status: 200 },
        );
      },
    });
    transport.setAuthority?.(AUTHORITY);
    transport.setLease?.({
      lease_id: "l1",
      service_session_id: "s1",
      generation: 1,
      expires_monotonic_ns: 10 ** 15,
    });

    const renewed = await transport.renew();

    expect(calls).toHaveLength(1);
    expect(calls[0].url).toBe("http://127.0.0.1:8800/expert-validation/lease/l1");
    expect(calls[0].method).toBe("PUT");
    expect(JSON.parse(String(calls[0].body))).toEqual({
      service_session_id: "s1",
      generation: 1,
    });
    expect(renewed).toMatchObject({ lease_id: "l1", generation: 2 });
  });

  test("renewing with no lease held asks for nothing", async () => {
    const calls: string[] = [];
    const transport = createHttpTransport("validation", {
      baseUrl: "http://127.0.0.1:8800",
      fetchImpl: async (url) => {
        calls.push(url);
        return new Response("{}", { status: 200 });
      },
    });
    transport.setAuthority?.(AUTHORITY);
    expect(await transport.renew()).toBeUndefined();
    expect(calls).toEqual([]);
  });
});

test("a lease without an id never builds a renewal URL", async () => {
  const calls: string[] = [];
  const transport = createHttpTransport("validation", {
    baseUrl: "http://127.0.0.1:8800",
    fetchImpl: async (url) => {
      calls.push(url);
      return new Response("{}", { status: 200 });
    },
  });
  transport.setAuthority?.(AUTHORITY);
  // A partial lease reached the transport in a live run and the renewal PUT went to
  // /expert-validation/lease/undefined; the guard has to be on the shape, not only on absence.
  transport.setLease?.({ service_session_id: "s1", generation: 1 } as never);
  expect(await transport.renew()).toBeUndefined();
  expect(calls.filter((u) => u.includes("undefined"))).toEqual([]);
});
