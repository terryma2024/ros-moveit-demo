import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { installedTest as test, expect, pythonExecutable } from "../fixtures/installed";
import { readJournalEvents, storeQuery } from "../assertions/journal";
import { EXECUTION_CONTRACT_VERSION, processAlive } from "../fixtures/host-routes";
import { api, hostClaimFor, waitProcessGone, type Api } from "./support";
import { ExpertValidationPage } from "../pages/expert-validation-page";

async function acquireLease(client: Api, session: string) {
  const response = await client.post("/expert-validation/lease", { service_session_id: session });
  expect(response.status).toBe(200);
  return response.body as { lease_id: string; generation: number };
}

async function createManifest(client: Api, totalPoints: number) {
  const response = await client.post("/expert-validation/manifests", { total_points: totalPoints });
  expect(response.status).toBe(200);
  return response.body as { manifest_id: string; points: Array<{ id: string }> };
}

function fixedConfig(lease: { lease_id: string; generation: number }, session: string, manifestId: string) {
  return {
    service_session_id: session,
    contract_version: EXECUTION_CONTRACT_VERSION,
    lease_id: lease.lease_id,
    lease_generation: lease.generation,
    manifest_id: manifestId,
    execution_mode: "SEQUENTIAL",
    worker_count: 1,
    ...hostClaimFor("SEQUENTIAL", 1),
  };
}

async function preflight(client: Api, config: Record<string, unknown>) {
  const response = await client.post("/expert-validation/campaigns/preflight", config);
  return response;
}

async function startCampaign(
  client: Api,
  config: Record<string, unknown>,
  commandId: string,
  receiptId: string,
) {
  return client.post("/expert-validation/campaigns", {
    ...config,
    command_id: commandId,
    preflight_receipt_id: receiptId,
  });
}

async function waitStatus(
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
    if (Date.now() > deadline) throw new Error(`CAMPAIGN_WAIT_TIMEOUT: ${response.body.status}`);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 250));
  }
}

function campaignDirs(serverRoot: string): string[] {
  const root = join(serverRoot, "campaigns");
  return existsSync(root) ? readdirSync(root) : [];
}

test("S05 server restart reconciles a running campaign spec:slow", async ({ page, installedServer }) => {
  const client = api(installedServer.baseURL);
  const session = "s05-session-a";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const config = fixedConfig(lease, session, manifest.manifest_id);
  const receipt = await preflight(client, config);
  expect(receipt.status).toBe(200);
  const started = await startCampaign(client, config, "s05-start", receipt.body.receipt_id);
  expect(started.status).toBe(200);
  const campaignId = started.body.campaign_id;
  await waitStatus(client, campaignId, (projection) => projection.status === "RUNNING");

  const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
  const ownersBefore = storeQuery(
    pythonExecutable(), database, "SELECT batch_id, pid FROM owned_execution",
  ) as Array<Record<string, unknown>>;
  expect(ownersBefore).toHaveLength(1);

  await installedServer.restart();

  // The old lease is invalidated by the restart.
  const staleRenew = await client.put(`/expert-validation/lease/${lease.lease_id}`, {
    service_session_id: session,
    generation: lease.generation,
  });
  expect(staleRenew.status).toBe(409);

  // Read-only reconciliation: the campaign is listed and projects from the journal.
  const list = await client.get("/expert-validation/campaigns");
  expect(list.status).toBe(200);
  expect(list.body.map((entry: any) => entry.campaign_id)).toEqual([campaignId]);
  const terminal = await waitStatus(
    client, campaignId,
    (projection) => projection.status === "COMPLETED_WITH_FAILURES" && projection.batch_cleanup_complete === true,
  );
  expect(terminal.points).toHaveLength(4);

  // Journal cleanup precedes process exit by a small window; wait for the
  // recorded owner pid to actually disappear before expecting control back.
  const oldPid = ownersBefore[0].pid as number;
  const exitDeadline = Date.now() + 15_000;
  while (processAlive(oldPid)) {
    if (Date.now() > exitDeadline) throw new Error(`OWNER_PROCESS_STILL_ALIVE: ${oldPid}`);
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 100));
  }

  // A new lease regains control only after reconciliation is clean.
  const leaseB = await acquireLease(client, "s05-session-b");
  const manifestB = await createManifest(client, 4);
  const configB = fixedConfig(leaseB, "s05-session-b", manifestB.manifest_id);
  const receiptB = await preflight(client, configB);
  expect(receiptB.status).toBe(200);
  const startedB = await startCampaign(client, configB, "s05-start-b", receiptB.body.receipt_id);
  expect(startedB.status).toBe(200);
  await waitStatus(
    client, startedB.body.campaign_id,
    (projection) => projection.status === "COMPLETED_WITH_FAILURES" && projection.batch_cleanup_complete === true,
  );

  const ownersAfter = storeQuery(
    pythonExecutable(), database, "SELECT batch_id FROM owned_execution ORDER BY batch_id",
  ) as Array<Record<string, unknown>>;
  expect(new Set(ownersAfter.map((row) => row.batch_id)).size).toBe(2);

  const app = new ExpertValidationPage(page);
  await app.goto();
  await expect(
    page.getByRole("heading", { name: new RegExp(`^Campaign ${startedB.body.campaign_id}`) }),
  ).toBeVisible({ timeout: 15_000 });
});

test("S06 start and retry command ids are idempotent spec:canonical-retry", async ({ installedServer }) => {
  const client = api(installedServer.baseURL);
  const session = "s06-session";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const config = fixedConfig(lease, session, manifest.manifest_id);
  const receipt = await preflight(client, config);
  expect(receipt.status).toBe(200);
  const body = { ...config, command_id: "s06-start", preflight_receipt_id: receipt.body.receipt_id };

  const first = await client.post("/expert-validation/campaigns", body);
  expect(
    first.status,
    `start: sent ${JSON.stringify(body)} -> ${JSON.stringify(first.body)}`,
  ).toBe(200);
  const campaignId = first.body.campaign_id;

  // Lost-response replay with the same command id returns the stored outcome.
  const replay = await client.post("/expert-validation/campaigns", body);
  expect(replay.status).toBe(200);
  expect(replay.body.campaign_id).toBe(campaignId);
  const list = await client.get("/expert-validation/campaigns");
  expect(list.body).toHaveLength(1);

  // The same command id with different content is a conflict.
  const otherManifest = await createManifest(client, 4);
  const conflict = await client.post("/expert-validation/campaigns", {
    ...body,
    manifest_id: otherManifest.manifest_id,
  });
  expect(conflict.status).toBe(409);
  expect(conflict.body.code).toBe("COMMAND_ID_REUSED");

  await waitStatus(
    client, campaignId,
    (projection) => projection.status === "COMPLETED_WITH_FAILURES" && projection.batch_cleanup_complete === true,
  );

  const projection = (await client.get(`/expert-validation/campaigns/${campaignId}`)).body;
  const pointId = projection.points.find((point: any) => point.status === "FAILED").point_id;
  const retryBody = {
    service_session_id: session,
    lease_id: lease.lease_id,
    lease_generation: lease.generation,
    command_id: "s06-retry",
    point_ids: [pointId],
    confirmation: "CONFIRM FULL_RESTART RETRIES",
  };
  const retry = await client.post(
    `/expert-validation/campaigns/${campaignId}/full-restart-retries`, retryBody,
  );
  expect(retry.status, `retry: ${JSON.stringify(retry.body)}`).toBe(200);

  const retryReplay = await client.post(
    `/expert-validation/campaigns/${campaignId}/full-restart-retries`, retryBody,
  );
  expect(retryReplay.status).toBe(200);

  const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
  const retryBatches = storeQuery(
    pythonExecutable(), database,
    "SELECT batch_id FROM campaign_batches WHERE batch_kind='FULL_RESTART_RETRY'",
  ) as Array<Record<string, unknown>>;
  expect(retryBatches).toHaveLength(1);

  const after = (await client.get(`/expert-validation/campaigns/${campaignId}`)).body;
  expect(after.valid_failed).toBe(projection.valid_failed);
  expect(after.requested).toBe(projection.requested);
});

test("S10 renew advances generation and active release fails closed spec:slow", async ({ installedServer }) => {
  const client = api(installedServer.baseURL);
  const session = "s10-session";
  const lease = await acquireLease(client, session);

  const renewed = await client.put(`/expert-validation/lease/${lease.lease_id}`, {
    service_session_id: session,
    generation: lease.generation,
  });
  expect(renewed.status).toBe(200);
  expect(renewed.body.generation).toBeGreaterThan(lease.generation);
  const current = { lease_id: lease.lease_id, generation: renewed.body.generation };

  const staleMutation = await client.put(`/expert-validation/lease/${lease.lease_id}`, {
    service_session_id: session,
    generation: lease.generation,
  });
  expect(staleMutation.status).toBe(409);
  expect(staleMutation.body.code).toBe("STALE_LEASE_GENERATION");

  const manifest = await createManifest(client, 4);
  const config = fixedConfig(current, session, manifest.manifest_id);
  const receipt = await preflight(client, config);
  expect(receipt.status).toBe(200);
  const started = await startCampaign(client, config, "s10-start", receipt.body.receipt_id);
  expect(started.status).toBe(200);
  await waitStatus(client, started.body.campaign_id, (projection) => projection.status === "RUNNING");

  const activeRelease = await client.del(`/expert-validation/lease/${lease.lease_id}`, {
    service_session_id: session,
    generation: current.generation,
  });
  expect(activeRelease.status).toBe(409);
  expect(activeRelease.body.code).toBe("ACTIVE_CAMPAIGN");

  const terminal = await waitStatus(
    client, started.body.campaign_id,
    (projection) => projection.status === "COMPLETED_WITH_FAILURES" && projection.batch_cleanup_complete === true,
  );
  const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
  const owners = storeQuery(
    pythonExecutable(), database,
    `SELECT pid FROM owned_execution WHERE batch_id='${terminal.batch_id}'`,
  ) as Array<{ pid: number }>;
  expect(owners).toHaveLength(1);
  await waitProcessGone(owners[0].pid);
  const released = await client.del(`/expert-validation/lease/${lease.lease_id}`, {
    service_session_id: session,
    generation: current.generation,
  });
  expect(released.status).toBe(200);
  expect(released.body.released).toBe(true);
});

test("S16 preflight receipts stay bound to their lease generation spec:default", async ({ installedServer }) => {
  const client = api(installedServer.baseURL);
  const session = "s16-session";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const configG1 = fixedConfig(lease, session, manifest.manifest_id);
  const receiptG1 = await preflight(client, configG1);
  expect(receiptG1.status).toBe(200);

  const renewed = await client.put(`/expert-validation/lease/${lease.lease_id}`, {
    service_session_id: session,
    generation: lease.generation,
  });
  expect(renewed.status).toBe(200);
  const generation2 = renewed.body.generation;

  // The generation-g receipt is rejected before any spawn, with either generation.
  const withNewGeneration = await startCampaign(
    client, { ...configG1, lease_generation: generation2 }, "s16-start-stale", receiptG1.body.receipt_id,
  );
  expect(withNewGeneration.status).toBe(409);
  const withOldGeneration = await startCampaign(
    client, configG1, "s16-start-stale-old", receiptG1.body.receipt_id,
  );
  expect(withOldGeneration.status).toBe(409);
  expect(campaignDirs(installedServer.serverRoot)).toEqual([]);

  // A fresh receipt bound to generation g+1 admits exactly one spawn.
  const configG2 = fixedConfig({ lease_id: lease.lease_id, generation: generation2 }, session, manifest.manifest_id);
  const receiptG2 = await preflight(client, configG2);
  expect(receiptG2.status).toBe(200);
  const started = await startCampaign(client, configG2, "s16-start", receiptG2.body.receipt_id);
  expect(started.status).toBe(200);

  const reuse = await startCampaign(client, configG2, "s16-start-again", receiptG2.body.receipt_id);
  expect(reuse.status).toBe(409);
  expect(campaignDirs(installedServer.serverRoot)).toHaveLength(1);

  await waitStatus(
    client, started.body.campaign_id,
    (projection) => projection.status === "COMPLETED_WITH_FAILURES" && projection.batch_cleanup_complete === true,
  );
});
