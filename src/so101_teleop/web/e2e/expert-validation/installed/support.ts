import { expect } from "@playwright/test";

import type { CapabilitiesDocument } from "../fixtures/functional-cases";
import {
  EXECUTION_CONTRACT_VERSION,
  type HostMode,
  hostRoute,
  processAlive as hostProcessAlive,
} from "../fixtures/host-routes";

export type ApiResponse = { status: number; body: any };
export type Api = {
  post: (path: string, body: Record<string, unknown>) => Promise<ApiResponse>;
  get: (path: string) => Promise<ApiResponse>;
  put: (path: string, body: Record<string, unknown>) => Promise<ApiResponse>;
  del: (path: string, body: Record<string, unknown>) => Promise<ApiResponse>;
};

export function api(baseURL: string): Api {
  const call = async (method: string, path: string, body?: Record<string, unknown>) => {
    // The host's capabilities are needed by every configuration built after the first request
    // (the claim), and specs that keep their own client would otherwise build configs before
    // anything primed the cache. Priming here makes the order a property of the client.
    await ensurePrimed(baseURL);
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

/**
 * The host's capabilities, fetched once per test process.
 *
 * A platform-bound host refuses any campaign request that does not name the exact matrix row it
 * serves, and it refuses a start whose body differs from the body its preflight receipt recorded.
 * Both mean the claim has to be on *every* request built from a configuration - including the ones
 * specs assemble by hand - so it lives here, next to the configurations themselves, rather than at
 * each call site.
 */
let cachedCapabilities: CapabilitiesDocument | null = null;
let priming: Promise<void> | null = null;

/** Prime once per process, from whichever client asks first. */
export async function ensurePrimed(baseURL: string): Promise<void> {
  if (cachedCapabilities !== null || priming !== null) {
    await priming;
    return;
  }
  priming = (async () => {
    const response = await fetch(`${baseURL}/expert-validation/capabilities`);
    if (response.ok) cachedCapabilities = (await response.json()) as CapabilitiesDocument;
  })().finally(() => {
    priming = null;
  });
  await priming;
}

export async function primeHostCapabilities(client: Api): Promise<CapabilitiesDocument> {
  cachedCapabilities = await capabilities(client);
  return cachedCapabilities;
}

/** The claim this host requires for one shape, or an empty spread where no matrix applies. */
export function hostClaimFor(
  mode: HostMode,
  workerCount: number,
  batchKind: "FIRST_PASS" | "FULL_RESTART_RETRY" = "FIRST_PASS",
): Record<string, unknown> {
  if (cachedCapabilities === null) return {};
  const route = hostRoute(cachedCapabilities, { mode, workerCount, batchKind });
  return route.platformBound && route.runnable && route.profile !== null
    ? { execution_profile: route.profile, batch_kind: batchKind }
    : {};
}

export async function acquireLease(client: Api, session: string): Promise<Lease> {
  const response = await client.post("/expert-validation/lease", { service_session_id: session });
  expect(response.status).toBe(200);
  // Every caller builds its configuration after this, so the claim is primed before the first one.
  await primeHostCapabilities(client);
  return response.body;
}

export async function createManifest(client: Api, totalPoints: number) {
  const response = await client.post("/expert-validation/manifests", { total_points: totalPoints });
  expect(response.status).toBe(200);
  return response.body as { manifest_id: string; points: Array<{ id: string }> };
}

export function fixedConfig(lease: Lease, session: string, manifestId: string) {
  return {
    contract_version: EXECUTION_CONTRACT_VERSION,
    service_session_id: session,
    lease_id: lease.lease_id,
    lease_generation: lease.generation,
    manifest_id: manifestId,
    execution_mode: "SEQUENTIAL" as const,
    worker_count: 1,
    ...hostClaimFor("SEQUENTIAL", 1),
  };
}

export function adaptiveConfig(lease: Lease, session: string, manifestId: string) {
  return {
    contract_version: EXECUTION_CONTRACT_VERSION,
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
    ...hostClaimFor("ADAPTIVE", 2),
  };
}

/**
 * Add the profile claim a platform-bound host requires.
 *
 * "A request that names a profile must name the exact combination its installed document declares;
 * one that names nothing is never completed by inference" - so macOS refuses a configuration that
 * omits the claim with `EXECUTION_PROFILE_REQUIRED`. The claim is read from the host's own
 * capabilities document rather than guessed, and a host with no matrix is sent exactly what the
 * caller built.
 */
async function claimed(
  client: Api, config: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  if (config.execution_profile !== undefined) return config;
  if (cachedCapabilities === null) await primeHostCapabilities(client);
  return {
    ...config,
    ...hostClaimFor(
      String(config.execution_mode ?? "SEQUENTIAL") as HostMode,
      Number(config.worker_count ?? config.preferred_worker_count ?? 1),
    ),
  };
}

export async function preflight(client: Api, config: Record<string, unknown>) {
  const body = await claimed(client, config);
  // The body a receipt records is compared byte for byte when the campaign starts, so a mismatch
  // can only be explained by seeing what was sent. Off unless asked for.
  if (process.env.SO101_E2E_TRACE_REQUESTS) console.log(`PREFLIGHT_SENT ${JSON.stringify(body)}`);
  const response = await client.post("/expert-validation/campaigns/preflight", body);
  // A refused request answers with its own code, and a bare status assertion hides it. The body is
  // carried too: a start is refused with PREFLIGHT_REQUEST_MISMATCH when it differs from the exact
  // body its receipt recorded, so both sides have to be visible to tell why.
  expect(
    response.status,
    `preflight: sent ${JSON.stringify(body)} -> ${JSON.stringify(response.body)}`,
  ).toBe(200);
  return response.body.receipt_id as string;
}

export async function startCampaign(
  client: Api, config: Record<string, unknown>, commandId: string, receiptId: string,
) {
  const body = {
    ...(await claimed(client, config)),
    command_id: commandId,
    preflight_receipt_id: receiptId,
  };
  const response = await client.post("/expert-validation/campaigns", body);
  expect(
    response.status,
    `start ${commandId}: sent ${JSON.stringify(body)} -> ${JSON.stringify(response.body)}`,
  ).toBe(200);
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

/**
 * Liveness through the platform's own reader: `/proc` on Linux, `ps` on macOS.
 *
 * The previous `/proc`-only version returned false for every pid on macOS, which turned every
 * "wait until it is gone" into an immediate pass and every "must still be alive" into a failure -
 * the check has to be able to succeed and to fail on the host it runs on.
 */
export function processAlive(pid: number): boolean {
  return hostProcessAlive(pid);
}

/** The deployed capabilities document: the host's own answer about what it serves. */
export async function capabilities(client: Api): Promise<CapabilitiesDocument> {
  const response = await client.get("/expert-validation/capabilities");
  expect(response.status).toBe(200);
  return response.body as CapabilitiesDocument;
}

export async function waitProcessGone(pid: number, timeoutMs = 15_000) {
  const deadline = Date.now() + timeoutMs;
  while (processAlive(pid)) {
    if (Date.now() > deadline) throw new Error(`PROCESS_STILL_ALIVE: ${pid}`);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }
}
