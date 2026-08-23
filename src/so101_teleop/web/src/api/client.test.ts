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

  it("executes the arm plan before q6 and returns both results", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: "OK", succeeded: true })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: "OK", succeeded: true })));
    const client = new TeleopApiClient(fetcher, () => "command-id");

    const result = await client.executeAll("p1", -0.04, "lease-a", "sim-a");

    expect(result.arm.code).toBe("OK");
    expect(result.gripper?.code).toBe("OK");
    expect(fetcher.mock.calls[0][0]).toBe("/plans/p1/execute");
    expect(fetcher.mock.calls[1][0]).toBe("/gripper/execute");
  });

  it("does not execute q6 when arm execution fails", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "PLAN_STALE_TARGET", succeeded: false })));
    const client = new TeleopApiClient(fetcher, () => "command-id");

    const result = await client.executeAll("p1", -0.04, "lease-a", "sim-a");

    expect(result.gripper).toBeUndefined();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
