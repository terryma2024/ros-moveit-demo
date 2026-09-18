import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { liveSimTest as test, expect, recordGate, requireGate, requireGateDetail } from "../fixtures/live-sim";
import { readJournalEvents } from "../assertions/journal";
import { ExpertValidationPage } from "../pages/expert-validation-page";

/**
 * R02: four-point PARALLEL exact N=2 live run; R04 (mid-run Chrome reload) is
 * embedded.  Requires the R01 gate receipt.
 */

test("R02 parallel two-worker live run with mid-run reload @live-sim", async ({ page, liveServer }) => {
  test.setTimeout(1_800_000);
  const producer = requireGateDetail(process.env.SO101_E2E_EVIDENCE_ROOT!, "R01", {
    evidenceRoot: process.env.SO101_E2E_EVIDENCE_ROOT,
  });
  expect(producer.producer).toBe("producer01");
  expect(producer.cleanup_complete).toBe(true);

  void requireGate;
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(4);
  await app.configureParallel(2);
  await app.runPreflight();
  await app.startValidation();

  const campaigns = await (
    await fetch(`${liveServer.baseURL}/expert-validation/campaigns`)
  ).json();
  expect(campaigns).toHaveLength(1);
  const campaignId = campaigns[0].campaign_id;

  const deadline = Date.now() + 1_500_000;
  let projection: any = null;
  let reloaded = false;
  while (Date.now() < deadline) {
    const response = await fetch(`${liveServer.baseURL}/expert-validation/campaigns/${campaignId}`);
    expect(response.status).toBe(200);
    projection = await response.json();
    if (
      ["COMPLETED", "COMPLETED_WITH_FAILURES", "INFRA_FAILED", "CANCELLED"].includes(projection.status)
      && projection.batch_cleanup_complete === true
    ) {
      break;
    }
    // R04: reload Chrome exactly once while the campaign is executing.
    if (!reloaded && projection.status === "RUNNING" && projection.execution_started >= 1) {
      await page.reload();
      await expect(
        page.getByRole("heading", { name: new RegExp(`^Campaign ${campaignId}`) }),
      ).toBeVisible({ timeout: 30_000 });
      reloaded = true;
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 5_000));
  }
  expect(reloaded).toBe(true);
  expect(projection?.batch_cleanup_complete).toBe(true);
  expect(["COMPLETED", "COMPLETED_WITH_FAILURES"]).toContain(projection?.status);

  // Two isolated workers with distinct identities.
  const workers = projection.workers;
  expect(workers.length).toBe(2);
  const workerIds = workers.map((worker: any) => worker.worker_id).sort();
  expect(workerIds).toEqual(["worker-01", "worker-02"]);

  const batchRoot = join(liveServer.stateDir, "campaigns", campaignId, projection.batch_id);
  for (const workerId of workerIds) {
    const workerRoot = join(batchRoot, "workers", workerId);
    expect(existsSync(workerRoot)).toBe(true);
    const owned = JSON.parse(
      readFileSyncSafe(join(workerRoot, "owned-runtime-processes.json")),
    );
    writeFileSync(
      join(liveServer.caseDir, `runtime-identity-${workerId}.json`),
      JSON.stringify({ worker_id: workerId, owned, gz_partition: "not_applicable" }, null, 2) + "\n",
    );
  }

  const events = readJournalEvents(join(batchRoot, "coordinator"));
  expect(events.filter((event) => event.type === "BATCH_STARTED")).toHaveLength(1);
  expect(events.filter((event) => event.type === "RESULT_COMMITTED")).toHaveLength(4);
  expect(events.some((event) => event.type === "BATCH_CLEANUP_COMPLETE")).toBe(true);

  // The reload neither interrupted nor duplicated the campaign.
  const campaignsAfter = await (
    await fetch(`${liveServer.baseURL}/expert-validation/campaigns`)
  ).json();
  expect(campaignsAfter).toHaveLength(1);
  expect(campaignsAfter[0].campaign_id).toBe(campaignId);

  await page.screenshot({ path: join(liveServer.caseDir, "final.png") });
  recordGate(process.env.SO101_E2E_EVIDENCE_ROOT!, "R02", {
    campaign_id: campaignId,
    status: projection.status,
    workers: workerIds,
    r04_reloaded: reloaded,
  });
});

function readFileSyncSafe(path: string): string {
  try {
    return readFileSync(path, "utf-8");
  } catch {
    return "{}";
  }
}
