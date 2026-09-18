import { readFileSync } from "node:fs";

import { expect } from "@playwright/test";

export type ApiResponse = { status: number; body: any };
export type Api = {
  post: (path: string, body: Record<string, unknown>) => Promise<ApiResponse>;
  get: (path: string) => Promise<ApiResponse>;
  put: (path: string, body: Record<string, unknown>) => Promise<ApiResponse>;
  del: (path: string, body: Record<string, unknown>) => Promise<ApiResponse>;
};

export function api(baseURL: string): Api {
  const call = async (method: string, path: string, body?: Record<string, unknown>) => {
    const response = await fetch(`${baseURL}${path}`, {
      method,
      headers: { "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const text = await response.text();
    let parsed: any = null;
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = { raw: text };
    }
    return { status: response.status, body: parsed };
  };
  return {
    post: (path, body) => call("POST", path, body),
    get: (path) => call("GET", path),
    put: (path, body) => call("PUT", path, body),
    del: (path, body) => call("DELETE", path, body),
  };
}

export type Lease = { lease_id: string; generation: number };

export async function acquireLease(client: Api, session: string): Promise<Lease> {
  const response = await client.post("/expert-validation/lease", { service_session_id: session });
  expect(response.status).toBe(200);
  return response.body;
}

export async function createManifest(client: Api, totalPoints: number) {
  const response = await client.post("/expert-validation/manifests", { total_points: totalPoints });
  expect(response.status).toBe(200);
  return response.body as { manifest_id: string; points: Array<{ id: string }> };
}

export function fixedConfig(lease: Lease, session: string, manifestId: string) {
  return {
    contract_version: 2 as const,
    service_session_id: session,
    lease_id: lease.lease_id,
    lease_generation: lease.generation,
    manifest_id: manifestId,
    execution_mode: "SEQUENTIAL" as const,
    worker_count: 1,
  };
}

export function adaptiveConfig(lease: Lease, session: string, manifestId: string) {
  return {
    contract_version: 2 as const,
    service_session_id: session,
    lease_id: lease.lease_id,
    lease_generation: lease.generation,
    manifest_id: manifestId,
    execution_mode: "ADAPTIVE",
    preferred_worker_count: 2,
    fallback_worker_counts: [1],
    initial_points_per_worker: 2,
    worker_start_timeout_s: 30,
    max_infra_attempts_per_point: 2,
    yolo_executor_count: 2,
  };
}

export async function preflight(client: Api, config: Record<string, unknown>) {
  const response = await client.post("/expert-validation/campaigns/preflight", config);
  expect(response.status).toBe(200);
  return response.body.receipt_id as string;
}

export async function startCampaign(
  client: Api, config: Record<string, unknown>, commandId: string, receiptId: string,
) {
  const response = await client.post("/expert-validation/campaigns", {
    ...config,
    command_id: commandId,
    preflight_receipt_id: receiptId,
  });
  expect(response.status).toBe(200);
  return response.body.campaign_id as string;
}

export async function waitStatus(
  client: Api,
  campaignId: string,
  predicate: (projection: any) => boolean,
  timeoutMs = 60_000,
) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const response = await client.get(`/expert-validation/campaigns/${campaignId}`);
    expect(response.status).toBe(200);
    if (predicate(response.body)) return response.body;
    if (Date.now() > deadline) {
      throw new Error(`CAMPAIGN_WAIT_TIMEOUT: ${response.body.status}`);
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
  }
}

export function processAlive(pid: number): boolean {
  try {
    const stat = readFileSync(`/proc/${pid}/stat`, "utf-8");
    const tail = stat.slice(stat.lastIndexOf(")") + 2).split(" ");
    return tail[0] !== "Z";
  } catch {
    return false;
  }
}

export async function waitProcessGone(pid: number, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  while (processAlive(pid)) {
    if (Date.now() > deadline) throw new Error(`PROCESS_STILL_ALIVE: ${pid}`);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
}
