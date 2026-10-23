import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";import { join } from "node:path";

import { installedTest as test, expect, pythonExecutable } from "../fixtures/installed";
import { readJournalEvents, storeQuery } from "../assertions/journal";
import { processAlive } from "../fixtures/host-routes";
import {
  api, acquireLease, capabilities, createManifest, fixedConfig,
  preflight, startCampaign, waitStatus, waitProcessGone,
} from "./support";

function ownerRows(serverRoot: string) {
  const database = join(serverRoot, "validation-service", "supervisor.sqlite3");
  return storeQuery(
    pythonExecutable(),
    database,
    "SELECT batch_id, owner_kind, state, pid, pgid, started_ticks, runner_pid FROM owned_execution ORDER BY batch_id",
  ) as Array<Record<string, any>>;
}

function readDescendantPid(logPath: string): number {
  const content = readFileSync(logPath, "utf-8");
  const match = content.match(/descendant_pid=(\d+)/);
  if (!match) throw new Error(`DESCENDANT_PID_NOT_LOGGED: ${logPath}`);
  return Number(match[1]);
}

function campaignRoot(serverRoot: string, campaignId: string): string {
  return join(serverRoot, "campaigns", campaignId);
}

test("S07 a surviving descendant blocks the next batch until inventory clears spec:descendant-survive", async ({ installedServer }) => {
  const client = api(installedServer.baseURL);
  const session = "s07-session";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const campaignId = await startCampaign(
    client, fixedConfig(lease, session, manifest.manifest_id), "s07-start-a",
    await preflight(client, fixedConfig(lease, session, manifest.manifest_id)),
  );

  // The helper leader exits immediately while its descendant survives.
  await expect
    .poll(() => ownerRows(installedServer.serverRoot).length, { timeout: 15_000 })
    .toBe(1);
  const owner = ownerRows(installedServer.serverRoot)[0];
  await waitProcessGone(owner.pid);

  const leaderLog = join(campaignRoot(installedServer.serverRoot, campaignId), `${owner.batch_id}.coordinator.log`);
  const descendantPid = readDescendantPid(leaderLog);
  expect(processAlive(descendantPid)).toBe(true);

  // The campaign is not terminal and no descendant-free claim is possible.
  const projection = (await client.get(`/expert-validation/campaigns/${campaignId}`)).body;
  expect(projection.status).toBe("RUNNING");

  try {
    // The next batch must see zero spawns while the descendant survives.
    const manifestB = await createManifest(client, 4);
    const configB = fixedConfig(lease, session, manifestB.manifest_id);
    const receiptB = await client.post("/expert-validation/campaigns/preflight", configB);
    expect(receiptB.status).toBe(409);
    expect(receiptB.body.code).toBe("VALIDATION_RECOVERY_REQUIRED");
    expect(ownerRows(installedServer.serverRoot)).toHaveLength(1);
    expect(readdirSync(join(installedServer.serverRoot, "campaigns"))).toHaveLength(1);
  } finally {
    process.kill(descendantPid, "SIGTERM");
  }
  await waitProcessGone(descendantPid);

  // Only after the descendant inventory clears may the next batch advance.
  const manifestB = await createManifest(client, 4);
  const configB = fixedConfig(lease, session, manifestB.manifest_id);
  const campaignB = await startCampaign(
    client, configB, "s07-start-b", await preflight(client, configB),
  );
  await expect
    .poll(() => ownerRows(installedServer.serverRoot).length, { timeout: 15_000 })
    .toBe(2);
  const ownerIds = ownerRows(installedServer.serverRoot).map((row) => row.batch_id);
  expect(new Set(ownerIds).size).toBe(2);
  expect(ownerIds).toContain(owner.batch_id);
  const ownerB = ownerRows(installedServer.serverRoot).find(
    (row) => row.batch_id !== owner.batch_id,
  )!;
  // A started batch is reported STARTED until the coordinator picks it up, which on a host that
  // runs the real coordinator is not instantaneous. The claim is that it reaches RUNNING, so the
  // assertion waits for it instead of sampling once.
  await expect
    .poll(async () => (await client.get(`/expert-validation/campaigns/${campaignB}`)).body.status, {
      timeout: 30_000,
    })
    .toBe("RUNNING");

  // This spec's helpers always leave a descendant behind; reap B's as well.
  const descendantB = readDescendantPid(
    join(campaignRoot(installedServer.serverRoot, campaignB), `${ownerB.batch_id}.coordinator.log`),
  );
  process.kill(descendantB, "SIGTERM");
  await waitProcessGone(descendantB);
});

test("S11 fixed lease expiry cancels only through the control channel spec:expire", async ({ installedServer }) => {
  test.setTimeout(120_000);
  const client = api(installedServer.baseURL);
  const session = "s11-session";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const config = fixedConfig(lease, session, manifest.manifest_id);
  const campaignId = await startCampaign(
    client, config, "s11-start", await preflight(client, config),
  );
  await waitStatus(client, campaignId, (value) => value.status === "RUNNING");
  const owner = ownerRows(installedServer.serverRoot)[0];

  // Never renew: the lease crosses its TTL and the server must cancel cooperatively.
  const terminal = await waitStatus(
    client, campaignId,
    (value) => value.status === "CANCELLED" && value.batch_cleanup_complete === true,
    90_000,
  );
  expect(terminal.status).toBe("CANCELLED");

  const events = readJournalEvents(
    join(campaignRoot(installedServer.serverRoot, campaignId), owner.batch_id, "coordinator"),
  );
  const stopping = events.filter((event) => event.type === "BATCH_STOPPING");
  expect(stopping).toHaveLength(1);
  const terminalEvent = events.find((event) => event.type === "BATCH_TERMINAL");
  expect(
    (terminalEvent?.payload?.delta as Record<string, unknown> | undefined)?.terminal_reason,
  ).toBe("WEB_CANCEL_REQUESTED");
  await waitProcessGone(owner.pid);

  const database = join(installedServer.serverRoot, "validation-service", "supervisor.sqlite3");
  const leases = storeQuery(
    pythonExecutable(), database, "SELECT state FROM leases ORDER BY generation DESC LIMIT 1",
  ) as Array<Record<string, any>>;
  expect(leases[0].state).toBe("EXPIRED");
});

test("S13 operator cancel reaches a safe terminal state spec:slow", async ({ installedServer }) => {
  test.setTimeout(90_000);
  const client = api(installedServer.baseURL);
  const session = "s13-session";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const config = fixedConfig(lease, session, manifest.manifest_id);
  const campaignId = await startCampaign(
    client, config, "s13-start", await preflight(client, config),
  );
  await waitStatus(client, campaignId, (value) => value.status === "RUNNING");

  const cancelled = await client.post(`/expert-validation/campaigns/${campaignId}/cancel`, {
    service_session_id: session,
    lease_id: lease.lease_id,
    lease_generation: lease.generation,
    command_id: "s13-cancel",
  });
  expect(cancelled.status).toBe(200);

  // Until cleanup completes, a fresh campaign is fenced out.
  const manifestB = await createManifest(client, 4);
  const configB = fixedConfig(lease, session, manifestB.manifest_id);
  const blocked = await client.post("/expert-validation/campaigns/preflight", configB);
  expect(blocked.status).toBe(409);

  await waitStatus(
    client, campaignId,
    (value) => value.status === "CANCELLED" && value.batch_cleanup_complete === true,
  );
  await waitProcessGone(ownerRows(installedServer.serverRoot)[0].pid);

  // After cleanup the same holder may start the next campaign.
  const receiptB = await preflight(client, configB);
  const campaignB = await startCampaign(client, configB, "s13-start-b", receiptB);
  await waitStatus(
    client, campaignB,
    (value) => value.status === "COMPLETED_WITH_FAILURES" && value.batch_cleanup_complete === true,
  );
});
