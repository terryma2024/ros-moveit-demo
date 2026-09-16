import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

import { installedTest as test, expect, pythonExecutable } from "../fixtures/installed";
import { readJournalEvents, storeQuery } from "../assertions/journal";
import { ExpertValidationPage } from "../pages/expert-validation-page";
import {
  api, acquireLease, createManifest, fixedConfig, preflight, startCampaign,
  waitStatus, waitProcessGone,
} from "./support";

function database(serverRoot: string): string {
  return join(serverRoot, "validation-service", "supervisor.sqlite3");
}

function query(serverRoot: string, sql: string): Array<Record<string, any>> {
  return storeQuery(pythonExecutable(), database(serverRoot), sql) as Array<Record<string, any>>;
}

function journalEvents(serverRoot: string, campaignId: string, batchId: string) {
  const root = join(serverRoot, "campaigns", campaignId, batchId, "coordinator");
  if (!existsSync(root)) return [];
  return readJournalEvents(root);
}

function hasJournalEvent(events: Array<{ type?: string }>, type: string): boolean {
  return events.some((event) => event.type === type);
}

function retryBody(lease: { lease_id: string; generation: number }, session: string, commandId: string, pointIds: string[]) {
  return {
    service_session_id: session,
    lease_id: lease.lease_id,
    lease_generation: lease.generation,
    command_id: commandId,
    point_ids: pointIds,
    confirmation: "CONFIRM FULL_RESTART RETRIES",
  };
}

test("S14 two failed points retry as serial N=1/K=1 batches spec:slow", async ({ page, installedServer, consoleErrors }) => {
  test.setTimeout(120_000);
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(4);
  await app.configureSequential();
  await app.runPreflight();
  await app.startValidation();

  const client = api(installedServer.baseURL);
  const campaigns = await client.get("/expert-validation/campaigns");
  const campaignId = campaigns.body[0].campaign_id;
  const terminal = await waitStatus(
    client, campaignId,
    (value) => value.status === "COMPLETED_WITH_FAILURES" && value.batch_cleanup_complete === true,
  );
  const failed = terminal.points.filter((point: any) => point.status === "FAILED");
  expect(failed).toHaveLength(4);
  const displayIds = failed.slice(0, 2).map((point: any) => point.display_id);
  const pointIds = failed.slice(0, 2).map((point: any) => point.point_id);

  await app.selectPoint(displayIds[0]);
  await app.retryCheckbox(displayIds[0]).check();
  await app.retryCheckbox(displayIds[1]).check();
  await page.getByRole("button", { name: "Retry selected with FULL_RESTART" }).click();
  await page.getByLabel("Confirmation").fill("CONFIRM FULL_RESTART RETRIES");
  await page.getByRole("button", { name: "Confirm retry" }).click();

  await expect
    .poll(async () => {
      const rows = query(
        installedServer.serverRoot,
        `SELECT state FROM retry_queue WHERE campaign_id='${campaignId}' ORDER BY ordinal`,
      );
      return rows.map((row) => row.state).join(",");
    }, { timeout: 60_000 })
    .toBe("COMPLETE,COMPLETE");

  const batches = query(
    installedServer.serverRoot,
    `SELECT batch_id, point_id, state, cleanup_receipt_sha256 FROM campaign_batches
     WHERE batch_kind='FULL_RESTART_RETRY' ORDER BY batch_id`,
  );
  expect(batches).toHaveLength(2);
  expect(batches[0].batch_id).toBe("retry-001");
  expect(batches[1].batch_id).toBe("retry-002");
  expect(batches.map((row) => row.state)).toEqual(["CLEANED", "CLEANED"]);
  expect(batches.map((row) => Boolean(row.cleanup_receipt_sha256))).toEqual([true, true]);
  expect(new Set(batches.map((row) => row.point_id))).toEqual(new Set(pointIds));

  // Each retry was its own N=1/K=1 batch with exactly one point.
  for (const batch of batches) {
    const events = journalEvents(installedServer.serverRoot, campaignId, batch.batch_id);
    const started = events.filter((event) => event.type === "BATCH_STARTED");
    expect(started).toHaveLength(1);
    const config = started[0].payload.batch as Record<string, any>;
    expect(config.worker_count).toBe(1);
    expect(config.max_points_per_worker).toBe(1);
    expect(config.point_ids).toHaveLength(1);
  }

  // Serial ownership: three owners total, strictly ordered acknowledgements.
  const owners = query(
    installedServer.serverRoot,
    "SELECT batch_id, acknowledged_at_ns FROM owned_execution ORDER BY acknowledged_at_ns",
  );
  expect(owners.map((row) => row.batch_id)).toEqual([terminal.batch_id, "retry-001", "retry-002"]);
  expect(owners[2].acknowledged_at_ns).toBeGreaterThan(owners[1].acknowledged_at_ns);

  // First-pass statistics are untouched by the retry batches.
  const after = (await client.get(`/expert-validation/campaigns/${campaignId}`)).body;
  expect(after.requested).toBe(4);
  expect(after.valid_failed).toBe(4);
  expect(after.valid_succeeded).toBe(0);
  await expect(page.getByText("First pass 0 / 4 valid")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("S15 terminal-to-cleanup window never replays or skips spec:window-terminal-cleanup", async ({ installedServer }) => {
  test.setTimeout(90_000);
  const client = api(installedServer.baseURL);
  const session = "s15-w1";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const config = fixedConfig(lease, session, manifest.manifest_id);
  const campaignId = await startCampaign(client, config, "s15w1-start", await preflight(client, config));
  const terminal = await waitStatus(
    client, campaignId,
    (value) => value.status === "COMPLETED_WITH_FAILURES" && value.batch_cleanup_complete === true,
  );
  const pointIds = terminal.points.slice(0, 2).map((point: any) => point.point_id);

  // The retry helper stops between terminal and cleanup: the command stays open.
  const first = await client.post(
    `/expert-validation/campaigns/${campaignId}/full-restart-retries`,
    retryBody(lease, session, "s15w1-retry", pointIds),
  );
  expect(first.status).toBe(409);
  expect(first.body.code).toBe("RETRY_CLEANUP_INCOMPLETE");

  const replay = await client.post(
    `/expert-validation/campaigns/${campaignId}/full-restart-retries`,
    retryBody(lease, session, "s15w1-retry", pointIds),
  );
  expect(replay.status).toBe(409);
  expect(replay.body.code).toBe("COMMAND_OUTCOME_UNKNOWN");

  await installedServer.restart();

  const leaseB = await acquireLease(client, session);
  const resumed = await client.post(
    `/expert-validation/campaigns/${campaignId}/full-restart-retries`,
    retryBody(leaseB, session, "s15w1-retry-resume", pointIds),
  );
  expect(resumed.status).toBe(409);
  expect(resumed.body.code).toBe("RETRY_CLEANUP_INCOMPLETE");

  // No re-execution, no skip: one retry batch exists and the queue is unchanged.
  const owners = query(installedServer.serverRoot, "SELECT batch_id FROM owned_execution");
  expect(owners).toHaveLength(2);
  const queue = query(
    installedServer.serverRoot,
    `SELECT ordinal, state FROM retry_queue WHERE campaign_id='${campaignId}' ORDER BY ordinal`,
  );
  expect(queue.map((row) => row.state)).toEqual(["RUNNING", "QUEUED"]);
  const events = journalEvents(installedServer.serverRoot, campaignId, "retry-001");
  expect(hasJournalEvent(events, "BATCH_TERMINAL")).toBe(true);
  expect(hasJournalEvent(events, "BATCH_FINISHED")).toBe(false);
});

test("S15 cleanup-to-dequeue window advances exactly once spec:slow", async ({ installedServer }) => {
  test.setTimeout(120_000);
  const client = api(installedServer.baseURL);
  const session = "s15-w2";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const config = fixedConfig(lease, session, manifest.manifest_id);
  const campaignId = await startCampaign(client, config, "s15w2-start", await preflight(client, config));
  const terminal = await waitStatus(
    client, campaignId,
    (value) => value.status === "COMPLETED_WITH_FAILURES" && value.batch_cleanup_complete === true,
  );
  const pointIds = terminal.points.slice(0, 2).map((point: any) => point.point_id);

  // Crash the server while retry-001 is executing; the helper survives and
  // commits terminal+cleanup to its journal while the server is down.
  const pending = client
    .post(
      `/expert-validation/campaigns/${campaignId}/full-restart-retries`,
      retryBody(lease, session, "s15w2-retry", pointIds),
    )
    .catch((error) => error);
  await expect
    .poll(
      () => hasJournalEvent(journalEvents(installedServer.serverRoot, campaignId, "retry-001"), "ATTEMPT_STARTED"),
      { timeout: 30_000 },
    )
    .toBe(true);
  await installedServer.killHard();
  await pending;

  // The orphaned helper completes its journal, then exits.
  await expect
    .poll(
      () => hasJournalEvent(journalEvents(installedServer.serverRoot, campaignId, "retry-001"), "BATCH_FINISHED"),
      { timeout: 30_000 },
    )
    .toBe(true);
  const framesAtCrash = journalEvents(installedServer.serverRoot, campaignId, "retry-001").length;
  const orphan = query(
    installedServer.serverRoot,
    "SELECT pid FROM owned_execution WHERE batch_id='retry-001'",
  )[0];
  await waitProcessGone(orphan.pid, 30_000);

  await installedServer.start();

  // The crashed command remains outcome-unknown; a new command reconciles.
  const leaseB = await acquireLease(client, session);
  const replay = await client.post(
    `/expert-validation/campaigns/${campaignId}/full-restart-retries`,
    retryBody(leaseB, session, "s15w2-retry", pointIds),
  );
  expect(replay.status).toBe(409);
  expect(replay.body.code).toBe("COMMAND_OUTCOME_UNKNOWN");

  const resumed = await client.post(
    `/expert-validation/campaigns/${campaignId}/full-restart-retries`,
    retryBody(leaseB, session, "s15w2-retry-resume", pointIds),
  );
  expect(resumed.status).toBe(200);
  expect(resumed.body.status).toBe("RETRIES_COMPLETE");

  // Point one was not re-executed; point two ran exactly once.
  expect(journalEvents(installedServer.serverRoot, campaignId, "retry-001")).toHaveLength(framesAtCrash);
  const queue = query(
    installedServer.serverRoot,
    `SELECT ordinal, state, cleanup_receipt_sha256 FROM retry_queue WHERE campaign_id='${campaignId}' ORDER BY ordinal`,
  );
  expect(queue.map((row) => row.state)).toEqual(["COMPLETE", "COMPLETE"]);
  expect(queue.every((row) => Boolean(row.cleanup_receipt_sha256))).toBe(true);
  const owners = query(
    installedServer.serverRoot,
    "SELECT batch_id FROM owned_execution ORDER BY acknowledged_at_ns",
  );
  expect(owners.map((row) => row.batch_id)).toEqual([terminal.batch_id, "retry-001", "retry-002"]);
});

test("S15 spawn-intent-to-ack window stays fenced spec:slow", async ({ installedServer }) => {
  test.setTimeout(120_000);
  const client = api(installedServer.baseURL);
  const session = "s15-w3";
  const lease = await acquireLease(client, session);
  const manifest = await createManifest(client, 4);
  const config = fixedConfig(lease, session, manifest.manifest_id);
  const campaignId = await startCampaign(client, config, "s15w3-start", await preflight(client, config));
  const terminal = await waitStatus(
    client, campaignId,
    (value) => value.status === "COMPLETED_WITH_FAILURES" && value.batch_cleanup_complete === true,
  );
  const pointIds = [terminal.points[0].point_id];

  // Kill the server between the durable spawn intent and its ACK.
  const pending = client
    .post(
      `/expert-validation/campaigns/${campaignId}/full-restart-retries`,
      retryBody(lease, session, "s15w3-retry", pointIds),
    )
    .catch((error) => error);
  await expect
    .poll(
      () => query(
        installedServer.serverRoot,
        "SELECT state FROM owned_execution WHERE batch_id='retry-001'",
      )[0]?.state,
      { timeout: 30_000, intervals: [2, 5, 10] },
    )
    .toBe("INTENT");
  await installedServer.killHard();
  await pending;

  // Let the possibly-spawned helper finish and exit before judging.
  await expect
    .poll(
      () => hasJournalEvent(journalEvents(installedServer.serverRoot, campaignId, "retry-001"), "BATCH_FINISHED"),
      { timeout: 30_000 },
    )
    .toBe(true);
  await expect
    .poll(() => {
      try {
        execFileSync("pgrep", ["-f", join(installedServer.serverRoot, "campaigns", campaignId)], {
          encoding: "utf-8",
        });
        return true;
      } catch {
        return false;
      }
    }, { timeout: 30_000 })
    .toBe(false);

  await installedServer.start();

  const leaseB = await acquireLease(client, session);
  const resumed = await client.post(
    `/expert-validation/campaigns/${campaignId}/full-restart-retries`,
    retryBody(leaseB, session, "s15w3-retry-resume", pointIds),
  );
  expect(resumed.status).toBe(409);
  expect(resumed.body.code).toBe("COMMAND_OUTCOME_UNKNOWN");

  // The unacknowledged intent fences new campaigns too.
  const manifestB = await createManifest(client, 4);
  const configB = fixedConfig(leaseB, session, manifestB.manifest_id);
  const blocked = await client.post("/expert-validation/campaigns/preflight", configB);
  expect(blocked.status).toBe(409);
  expect(blocked.body.code).toBe("VALIDATION_RECOVERY_REQUIRED");

  // Nothing advanced and nothing re-executed.
  const owners = query(installedServer.serverRoot, "SELECT batch_id, state FROM owned_execution");
  expect(owners).toHaveLength(2);
  const queue = query(
    installedServer.serverRoot,
    `SELECT ordinal, state FROM retry_queue WHERE campaign_id='${campaignId}' ORDER BY ordinal`,
  );
  expect(queue.map((row) => row.state)).toEqual(["RUNNING"]);
  expect(terminal.batch_id).not.toBe("retry-001");
});
