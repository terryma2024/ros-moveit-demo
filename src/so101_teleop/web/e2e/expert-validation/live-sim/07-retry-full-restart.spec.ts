import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { liveSimTest as test, expect } from "../fixtures/live-sim";
import { storeQuery } from "../assertions/journal";
import {
  assertCampaignBatchEvidence,
  assertRoutingClaim,
  campaignJournalRoot,
  readCampaignBatchEvidence,
  type CampaignBatchExpectation,
} from "../assertions/live-evidence";
import {
  ExpertValidationPage,
  releaseAcquiredLeases,
} from "../pages/expert-validation-page";

/**
 * The manual single-point failure retry, driven through the real console.
 *
 * A retry is only reachable when a point genuinely fails, so this case runs against a
 * task-owned points catalog whose `cup_test_right_5cm` anchor sits outside the robot's reach
 * (`$TASK_ROOT/fault-injection/points-unreachable-anchor.yaml`, selected with the product's own
 * `SO101_VALIDATION_POINTS`).  Nothing is faked: the sim really cannot perform that point, the
 * failure is a valid business failure, and the retry runs the point again as its own
 * `FULL_RESTART_RETRY` batch.  It is fault injection for the retry workflow only and is never
 * counted as a normal acceptance campaign.
 *
 * On macOS the first pass is the W1 route (schema v6, SEQUENTIAL, one worker) and the retry is the
 * v5 single-point FULL_RESTART route.  Both batches have to prove selected-only execution, the
 * durability watermark, the sealed physical evidence set and their own cleanup.
 */

test.afterEach(async ({ request }) => {
  await releaseAcquiredLeases(request);
});

test("R07 a genuinely failed point retries as its own SEQUENTIAL N1 FULL_RESTART batch @live-sim", async ({
  page,
  liveServer,
}) => {
  test.setTimeout(1_800_000);
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  const [manifestResponse] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.url().endsWith("/expert-validation/manifests")
        && candidate.request().method() === "POST",
    ),
    app.generateManifest(4),
  ]);
  const generated = (await manifestResponse.json()) as { points?: Array<{ id: string }> };
  const firstPassSelection = (generated.points ?? []).map((point) => point.id);
  expect(firstPassSelection).toHaveLength(4);
  await app.configureSequential();

  // The first pass claims the W1 first-pass row; the console never infers it from the point count.
  const firstPassExpectation: CampaignBatchExpectation = {
    batchKind: "FIRST_PASS",
    executionProfile: "MPS_W1_FIRST_PASS",
    schemaVersion: 6,
    workerCount: 1,
    selectedPointIds: firstPassSelection,
  };
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
  assertRoutingClaim(receipt, firstPassExpectation);

  const campaignId = await app.startValidation();

  const readCampaign = async () =>
    await (
      await fetch(`${liveServer.baseURL}/expert-validation/campaigns/${campaignId}`)
    ).json();

  const waitForTerminal = async (deadlineMs: number) => {
    const deadline = Date.now() + deadlineMs;
    let projection: any = null;
    while (Date.now() < deadline) {
      projection = await readCampaign();
      if (
        ["COMPLETED", "COMPLETED_WITH_FAILURES", "INFRA_FAILED", "CANCELLED"].includes(
          projection.status,
        ) &&
        projection.batch_cleanup_complete === true
      ) {
        return projection;
      }
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 15_000));
    }
    return projection;
  };

  const firstPass = await waitForTerminal(600_000);
  expect(firstPass?.batch_cleanup_complete).toBe(true);
  const firstPassBatchId = firstPass.batch_id as string;

  // The W1 first pass is a complete batch of its own: its selection, watermark, sealed physical
  // evidence and cleanup all come from its own bytes.
  assertCampaignBatchEvidence(
    readCampaignBatchEvidence(join(liveServer.stateDir, "campaigns", campaignId, firstPassBatchId)),
    { ...firstPassExpectation, projection: firstPass },
  );

  // A genuine, valid failure is the precondition for the workflow -- never assumed, never faked.
  const failed = (firstPass.points ?? []).filter((point: any) => point.status === "FAILED");
  expect(
    failed.length,
    `expected the unreachable anchor to fail; statuses: ${JSON.stringify(
      (firstPass.points ?? []).map((point: any) => [point.point_id, point.status]),
    )}`,
  ).toBeGreaterThan(0);
  expect(failed.length, "exactly the injected anchor fails").toBe(1);
  const target = failed[0];
  expect(target.retry_eligible, "a valid failure is retry eligible").toBe(true);

  // The real console workflow: select the failed point, confirm, retry.
  await app.retryFailedPoints([target.display_id]);
  const afterRetry = await waitForTerminal(900_000);
  expect(afterRetry?.batch_cleanup_complete).toBe(true);

  // The retry is an independent, fresh batch on disk: its own selection, journal and cleanup.
  const campaignRoot = join(liveServer.stateDir, "campaigns", campaignId);
  const retryRoot = join(campaignRoot, "retry-001");
  expect(existsSync(retryRoot), `retry batch directory: ${retryRoot}`).toBe(true);
  const retryEvidence = readCampaignBatchEvidence(retryRoot);
  // The retry batch's own selection, read from whichever layout the route wrote: the fixed
  // coordinator's frozen manifest, or the composed campaign's selection binding and verdict.
  const retrySelection = retryEvidence.layout === "LINUX_FIXED"
    ? (() => {
      const manifest = JSON.parse(
        readFileSync(join(retryRoot, "batch_manifest.json"), "utf8"),
      ) as { batch_id?: string; batch_kind?: string; selected_point_ids?: string[]; worker_count?: number };
      expect(existsSync(join(retryRoot, "cleanup-gates.json"))).toBe(true);
      return {
        batch_id: String(manifest.batch_id), batch_kind: String(manifest.batch_kind),
        selected_point_ids: manifest.selected_point_ids as string[],
        worker_count: Number(manifest.worker_count),
      };
    })()
    : {
      batch_id: String(retryEvidence.manifest.batch_id),
      batch_kind: String((retryEvidence.manifest.binding as Record<string, unknown>).kind),
      selected_point_ids: retryEvidence.manifest.selected_point_ids as string[],
      worker_count: Number((retryEvidence.cleanup.route as Record<string, unknown>).worker_count),
    };
  expect(retrySelection.batch_kind).toBe("FULL_RESTART_RETRY");
  expect(retrySelection.batch_id).not.toBe(firstPassBatchId);
  expect(retrySelection.selected_point_ids).toEqual([target.point_id]);
  expect(retrySelection.worker_count).toBe(1);
  expect(existsSync(join(campaignJournalRoot(retryRoot), "events"))).toBe(true);

  // The retry batch proves the same four claims as any other batch, from its own bytes: exactly
  // the one failed point was executed (never a second point and never a repeat of the first
  // pass), the published watermark closes its sequence, the sealed physical evidence set is
  // intact and the retry batch completed its own cleanup.
  const retryExpectation: CampaignBatchExpectation = {
    batchKind: "FULL_RESTART_RETRY",
    executionProfile: "MPS_W1_FULL_RESTART_RETRY",
    schemaVersion: 5,
    workerCount: 1,
    selectedPointIds: [target.point_id],
  };
  // The campaign endpoint keeps projecting the *first-pass* batch, so the retry is asserted from
  // its own bytes only: its selection, journal, watermark, per-point evidence and cleanup.
  assertCampaignBatchEvidence(retryEvidence, retryExpectation);
  expect(retryEvidence.watermark?.batch_id).toBe(retrySelection.batch_id);

  // The store keeps the first pass and the retry as separate batches with separate statistics.
  const python = process.env.SO101_E2E_PYTHON ?? join(process.env.SO101_TASK_ROOT ?? "", "venv/bin/python");
  const database = join(liveServer.stateDir, "validation-service", "supervisor.sqlite3");
  const rows = storeQuery(
    python,
    database,
    `SELECT batch_id, batch_kind FROM campaign_batches WHERE campaign_id = '${campaignId}' ORDER BY batch_id`,
  ) as Array<{ batch_id: string; batch_kind: string }>;
  const kinds = rows.map((row) => row.batch_kind).sort();
  expect(kinds).toEqual(["FIRST_PASS", "FULL_RESTART_RETRY"]);
  expect(new Set(rows.map((row) => row.batch_id)).size).toBe(rows.length);

  writeFileSync(
    join(liveServer.caseDir, "retry-full-restart.json"),
    JSON.stringify(
      {
        campaign_id: campaignId,
        first_pass_batch_id: firstPassBatchId,
        fault: "cup_test_right_5cm moved out of reach via SO101_VALIDATION_POINTS",
        first_pass: {
          status: firstPass.status,
          points: (firstPass.points ?? []).map((point: any) => ({
            display_id: point.display_id,
            point_id: point.point_id,
            status: point.status,
            retry_eligible: point.retry_eligible,
          })),
        },
        retry_batch: retrySelection,
        retry_watermark: retryEvidence.watermark,
        retry_cleanup: retryEvidence.cleanup,
        after_retry: {
          status: afterRetry.status,
          retried_point_status: (afterRetry.points ?? []).find(
            (point: any) => point.point_id === target.point_id,
          )?.status,
        },
        store_batches: rows,
      },
      null,
      2,
    ) + "\n",
  );
});
