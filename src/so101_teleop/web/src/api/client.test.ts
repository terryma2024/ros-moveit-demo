import { describe, expect, it, vi } from "vitest";

import { TeleopApiClient } from "./client";

describe("Execute All", () => {
  it("loads the immutable backend capability snapshot with GET", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      backend: "mujoco_py",
      owner_package: "so101_demo_py",
      capabilities: { backend_probe: true, workflow_run: false },
    })));
    const client = new TeleopApiClient(fetcher, () => "command-id");

    const result = await client.capabilities();

    expect(result.backend).toBe("mujoco_py");
    expect(fetcher).toHaveBeenCalledWith("/capabilities", { method: "GET" });
  });

  it("calls the browser fetch function without rebinding its native receiver", async () => {
    const original = globalThis.fetch;
    globalThis.fetch = function (this: unknown) {
      if (this !== undefined) throw new TypeError("Illegal invocation");
      return Promise.resolve(new Response(JSON.stringify({ code: "OK", succeeded: true })));
    } as typeof fetch;
    try {
      const client = new TeleopApiClient(undefined, () => "command-id");
      const result = await client.post("/control/lease", {});
      expect(result.code).toBe("OK");
    } finally {
      globalThis.fetch = original;
    }
  });

  it("sends one composite parent request instead of two independent POSTs", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          operation_id: "op-1",
          phase: "COMPLETE",
          blocked_reason: null,
          children: [
            { child_id: "arm", goal_uuid: "g-arm", succeeded: true, stopped_confirmed: true, cleanup_confirmed: true },
            { child_id: "gripper", goal_uuid: "g-grip", succeeded: true, stopped_confirmed: true, cleanup_confirmed: true },
          ],
        }),
      ),
    );
    const client = new TeleopApiClient(fetcher, () => "command-id");

    const result = await client.executeAll("p1", -0.04, "lease-a", "sim-a");

    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0][0]).toBe("/plans/p1/execute-all");
    expect(result.operation_id).toBe("op-1");
    expect(result.children.map((child) => child.child_id)).toEqual(["arm", "gripper"]);
  });

  it("carries the instance authority headers when the document holds them", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ operation_id: "op-2", phase: "BLOCKED", blocked_reason: null, children: [] })),
    );
    const client = new TeleopApiClient(fetcher, () => "command-id");

    await client.executeAll("p1", -0.04, "lease-a", "sim-a", {
      instanceId: "i1",
      proof: "p1",
      channelRevision: 2,
      executionGeneration: 3,
    });

    const [, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.headers).toMatchObject({
      "X-SO101-Instance-ID": "i1",
      "X-SO101-Channel-Revision": "2",
      "X-SO101-Execution-Generation": "3",
    });
  });

  it("never retries a non-complete parent with a second request", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ operation_id: "op-3", phase: "BLOCKED", blocked_reason: "CLEANUP_NOT_CONFIRMED", children: [] }),
      ),
    );
    const client = new TeleopApiClient(fetcher, () => "command-id");

    const result = await client.executeAll("p1", -0.04, "lease-a", "sim-a");

    expect(result.phase).toBe("BLOCKED");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
