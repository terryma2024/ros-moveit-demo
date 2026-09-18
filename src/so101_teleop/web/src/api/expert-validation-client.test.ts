import { describe, expect, test, vi } from "vitest";

import { ExpertValidationApiError, ExpertValidationClient } from "./expert-validation-client";

function recorder(responses: Array<{ ok: boolean; status: number; body: unknown }>) {
  const calls: Array<{ path: string; init?: RequestInit; body?: Record<string, unknown> }> = [];
  const fetcher = async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    calls.push({ path, init, body });
    const response = responses.shift() ?? { ok: true, status: 200, body: {} };
    return {
      ok: response.ok,
      status: response.status,
      json: async () => response.body,
    } as Response;
  };
  return { fetcher: fetcher as typeof fetch, calls };
}

const lease = {
  service_session_id: "browser-a",
  lease_id: "lease-a",
  lease_generation: 3,
};

describe("ExpertValidationClient", () => {
  test("restores a bound manifest by an encoded read-only URL without execution authority", async () => {
    const document = { manifest_id: "manifest/4", point_count: 4, stale: true, points: [] };
    const transport = recorder([{ ok: true, status: 200, body: document }]);
    const result = await new ExpertValidationClient(transport.fetcher).getManifest("manifest/4");
    expect(result).toEqual(document);
    expect(transport.calls).toEqual([{ path: "/expert-validation/manifests/manifest%2F4", init: {}, body: undefined }]);
  });

  test("renewal sends current server lease identity and fencing generation via PUT", async () => {
    const renewed = { lease_id: "lease-a", service_session_id: "browser-a", generation: 4, expires_monotonic_ns: 2000 };
    const transport = recorder([{ ok: true, status: 200, body: renewed }]);
    const client = new ExpertValidationClient(transport.fetcher);
    const result = await client.renewLease({
      lease_id: "lease-a", service_session_id: "browser-a", generation: 3, expires_monotonic_ns: 1000,
    });
    expect(result).toEqual(renewed);
    expect(transport.calls[0]).toMatchObject({
      path: "/expert-validation/lease/lease-a",
      init: { method: "PUT" },
      body: { service_session_id: "browser-a", generation: 3 },
    });
  });

  test("watch polls authoritative HTTP without hints and stops cleanly", async () => {
    vi.useFakeTimers();
    try {
      const terminal = { campaign_id: "campaign-1", sequence: 2, status: "COMPLETED" };
      const transport = recorder([{ ok: true, status: 200, body: terminal }]);
      const close = vi.fn();
      const client = new ExpertValidationClient(
        transport.fetcher,
        () => "command-1",
        () => ({ addEventListener: vi.fn(), close }) as unknown as WebSocket,
      );
      const apply = vi.fn();
      const stop = client.watchCampaign("campaign-1", 1, apply);

      await vi.advanceTimersByTimeAsync(2_000);

      expect(transport.calls).toHaveLength(1);
      expect(apply).toHaveBeenCalledWith(terminal);
      stop();
      await vi.advanceTimersByTimeAsync(4_000);
      expect(transport.calls).toHaveLength(1);
      expect(close).toHaveBeenCalledOnce();
    } finally {
      vi.useRealTimers();
    }
  });

  test("parallel start preserves admitted mode N and K", async () => {
    const transport = recorder([
      { ok: true, status: 200, body: { receipt_id: "receipt-1", admitted: true } },
      { ok: true, status: 200, body: { campaign_id: "campaign-1", sequence: 1 } },
    ]);
    const client = new ExpertValidationClient(transport.fetcher, () => "command-1");
    const config = {
      contract_version: 3 as const,
      manifest_id: "manifest-20",
      execution_mode: "PARALLEL" as const,
      worker_count: 2,
    };
    const receipt = await client.preflight(config, lease);
    await client.startCampaign({ ...config, preflight_receipt_id: receipt.receipt_id }, lease);

    expect(transport.calls[1].body).toMatchObject({
      contract_version: 3,
      execution_mode: "PARALLEL",
      worker_count: 2,
      command_id: "command-1",
    });
  });

  test("adaptive start preserves ladder and never sends K", async () => {
    const transport = recorder([
      { ok: true, status: 200, body: { receipt_id: "receipt-1", admitted: true } },
      { ok: true, status: 200, body: { campaign_id: "campaign-1", sequence: 1 } },
    ]);
    const client = new ExpertValidationClient(transport.fetcher, () => "command-2");
    const request = {
      contract_version: 3 as const,
      manifest_id: "manifest-20",
      execution_mode: "ADAPTIVE" as const,
      preferred_worker_count: 8,
      fallback_worker_counts: [6, 4, 2, 1],
      initial_points_per_worker: 3,
      worker_start_timeout_s: 120,
      max_infra_attempts_per_point: 5,
      yolo_executor_count: 2 as const,
    };
    const receipt = await client.preflight(request, lease);
    await client.startCampaign({ ...request, preflight_receipt_id: receipt.receipt_id }, lease);

    expect(transport.calls[1].body?.max_points_per_worker).toBeUndefined();
    expect(transport.calls[1].body?.fallback_worker_counts).toEqual([6, 4, 2, 1]);
    expect(transport.calls[1].body?.yolo_executor_count).toBe(2);
  });

  test("retry sends exact confirmation and selected failed ids", async () => {
    const transport = recorder([
      { ok: true, status: 200, body: { campaign_id: "campaign-1", sequence: 9 } },
    ]);
    const client = new ExpertValidationClient(transport.fetcher, () => "retry-1");
    await client.retry(
      "campaign-1",
      ["sample_05_near_center"],
      lease,
      "CONFIRM FULL_RESTART RETRIES",
    );
    expect(transport.calls[0].body).toMatchObject({
      command_id: "retry-1",
      point_ids: ["sample_05_near_center"],
      confirmation: "CONFIRM FULL_RESTART RETRIES",
    });
  });

  test("machine-readable error codes survive non-2xx responses", async () => {
    const transport = recorder([
      { ok: false, status: 409, body: { code: "PREFLIGHT_REQUEST_MISMATCH" } },
    ]);
    const client = new ExpertValidationClient(transport.fetcher);
    await expect(client.campaign("campaign-1")).rejects.toMatchObject({
      name: "ExpertValidationApiError",
      code: "PREFLIGHT_REQUEST_MISMATCH",
      status: 409,
    } satisfies Partial<ExpertValidationApiError>);
  });
});
