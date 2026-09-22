import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { liveSimTest as test, expect, recordGate, requireGate, requireGateDetail } from "../fixtures/live-sim";
import { readJournalEvents } from "../assertions/journal";
import {
  assertCampaignBatchEvidence,
  assertRoutingClaim,
  campaignJournalRoot,
  committedAttempts,
  readCampaignBatchEvidence,
  type CampaignBatchExpectation,
} from "../assertions/live-evidence";
import {
  ExpertValidationPage,
  releaseAcquiredLeases,
} from "../pages/expert-validation-page";

/**
 * R02: four-point PARALLEL exact N=2 live run; R04 (mid-run Chrome reload) is
 * embedded.  Requires the R01 gate receipt.
 *
 * On macOS this is the W2 route: the console claims the `MPS_W2_FIRST_PASS` matrix row (schema
 * v4, PARALLEL, two workers), the service resolves that document from its own bytes, and the
 * batch has to prove selected-only execution, the durability watermark, the sealed physical
 * evidence set and its own cleanup.
 */

const W2_ROUTE: CampaignBatchExpectation = {
  batchKind: "FIRST_PASS",
  executionProfile: "MPS_W2_FIRST_PASS",
  schemaVersion: 4,
  workerCount: 2,
  selectedPointIds: [],
};

// The exclusive lease belongs to the deployed service, not to this spec: hand it back
// even when the test fails, or the next spec is refused with 409 Conflict.
test.afterEach(async ({ request }) => {
  await releaseAcquiredLeases(request);
});

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
  // The generated manifest and the preflight receipt are this spec's own expectation: the
  // selection the console actually claimed, not a value re-read from the finished batch.
  const [manifestResponse] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.url().endsWith("/expert-validation/manifests")
        && candidate.request().method() === "POST",
    ),
    app.generateManifest(4),
  ]);
  const generated = (await manifestResponse.json()) as { points?: Array<{ id: string }> };
  const selectedPointIds = (generated.points ?? []).map((point) => point.id);
  expect(selectedPointIds).toHaveLength(4);
  const expectation: CampaignBatchExpectation = { ...W2_ROUTE, selectedPointIds };

  await app.configureParallel(2);
  const [preflightResponse] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.url().endsWith("/expert-validation/campaigns/preflight")
        && candidate.request().method() === "POST",
    ),
    app.runPreflight(),
  ]);
  expect(preflightResponse.status()).toBe(200);
  const receipt = (await preflightResponse.json()) as Record<string, unknown>;
  assertRoutingClaim(receipt, expectation);
  // The point count is not a routing input: four points claim the same W2 row as any other count.
  expect(receipt.execution_profile).toBe("MPS_W2_FIRST_PASS");

  // The campaign id comes from this spec's own start response: the campaign list also holds the
  // campaigns of every spec that ran before it.
  const campaignId = await app.startValidation();

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

  // Two isolated workers with distinct identities; the batch's own bytes name them below.
  const workers = projection.workers;
  expect(workers.length).toBe(2);
  const workerIds = workers.map((worker: any) => worker.worker_id).sort();
  expect(new Set(workerIds).size).toBe(2);

  const batchRoot = join(liveServer.stateDir, "campaigns", campaignId, projection.batch_id);
  const events = readJournalEvents(campaignJournalRoot(batchRoot));
  expect(events.filter((event) => event.type === "RESULT_COMMITTED")).toHaveLength(4);
  const evidence = readCampaignBatchEvidence(batchRoot);
  const commits = committedAttempts(evidence);
  expect(commits.map((attempt) => attempt.pointId).sort()).toEqual([...selectedPointIds].sort());
  expect(commits.every((attempt) => attempt.sealedDir.startsWith(batchRoot))).toBe(true);

  // Linux keeps the fixed coordinator's own worker roots; the composed macOS route keeps one
  // station tree per attempt and one station ack per worker, and both are this batch's own bytes.
  if (evidence.layout === "MACOS_COMPOSED") {
    expect(events.filter((event) => event.type === "CAMPAIGN_STARTED")).toHaveLength(1);
    expect(events.some((event) => event.type === "CLEANUP_COMMITTED")).toBe(true);
    // The projection's worker ids are the ids this batch's own commits carry, nothing else.
    expect(workerIds).toEqual([...new Set(commits.map((attempt) => attempt.workerId))].sort());
    for (const workerId of workerIds) {
      const acks = readdirSync(batchRoot).filter((name) => name.startsWith(`${workerId}-ack-`));
      expect(acks.length, `${workerId} station acks`).toBeGreaterThan(0);
      const ack = JSON.parse(readFileSync(join(batchRoot, acks[0]), "utf-8"));
      expect(ack.station, `${workerId} station`).toBe(true);
      writeFileSync(
        join(liveServer.caseDir, `runtime-identity-${workerId}.json`),
        JSON.stringify({
          worker_id: workerId, pid: ack.pid, pgid: ack.pgid, acks: acks.length,
          gz_partition: "not_applicable",
        }, null, 2) + "\n",
      );
    }
  } else {
    expect(workerIds).toEqual(["worker-01", "worker-02"]);
    expect(events.filter((event) => event.type === "BATCH_STARTED")).toHaveLength(1);
    expect(events.some((event) => event.type === "BATCH_CLEANUP_COMPLETE")).toBe(true);
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
  }

  // Selected-only execution: the projection carries one FIRST_PASS attempt per selected point and
  // nothing else, and the batch's own evidence proves the same set.
  expect(projection.points.map((point: any) => point.point_id).sort())
    .toEqual([...selectedPointIds].sort());
  for (const point of projection.points) {
    const kinds = (point.attempts ?? []).map((attempt: any) => attempt.kind);
    expect(kinds, `${point.display_id} attempts`).toEqual(["FIRST_PASS"]);
    expect(kinds).not.toContain("FULL_RESTART_RETRY");
  }

  assertCampaignBatchEvidence(evidence, { ...expectation, projection });
  writeFileSync(
    join(liveServer.caseDir, "w2-campaign-evidence.json"),
    JSON.stringify({
      expectation,
      watermark: evidence.watermark,
      manifest: evidence.manifest,
      commits,
      projection_attempts: projection.points.map((point: any) => ({
        point_id: point.point_id,
        attempts: point.attempts,
      })),
    }, null, 2) + "\n",
  );

  // The reload neither interrupted nor duplicated this campaign, and it left no other campaign
  // running.  The list also holds the campaigns of the specs that ran before this one, so the
  // check is on this spec's own id rather than on the size of the list.
  const campaignsAfter: Array<{ campaign_id: string; status: string }> = await (
    await fetch(`${liveServer.baseURL}/expert-validation/campaigns`)
  ).json();
  const mine = campaignsAfter.filter((entry) => entry.campaign_id === campaignId);
  expect(mine).toHaveLength(1);
  expect(mine[0].status).toBe(projection.status);
  expect(
    campaignsAfter.filter((entry) =>
      ["RUNNING", "STARTING", "CANCELLING"].includes(entry.status),
    ),
  ).toHaveLength(0);

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
