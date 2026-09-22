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
 * The single-point failure retry, driven through the real console.
 *
 * A retry is only reachable when a point genuinely fails, so this case selects the fifteen points
 * that contain the catalog's own marginal pose: `sample_05_near_center` declares a cup position
 * the perception threshold rejects (44 < 50 orange points), so the product commits it FAILED
 * through its own code path, with no infrastructure code.  Nothing is injected and nothing is
 * faked; the retry then runs that point again as its own `FULL_RESTART_RETRY` batch.
 *
 * The fault-injection-catalog route this case was first written for does not exist in the product:
 * both the service (`expert_validation/catalog.py`) and the campaign CLI
 * (`cli/mujoco_parallel_batch.py`) pin the catalog's digest, and the service additionally
 * cross-checks the manifest identity hash against that pinned selection, so
 * `SO101_VALIDATION_POINTS` can never carry a different catalog.  Measured offline and read-only in
 * `task12/fault-injection-route-refused/demonstration.txt`: a catalog copy differing only in
 * `cup_test_right_5cm`'s `cup_position_world_m` is refused `POINT_CATALOG_HASH_MISMATCH` by both
 * loaders.  `selection-allocation.txt` in the same directory carries the selection arithmetic -
 * fifteen points is the smallest selection that contains `sample_05_near_center`.
 *
 * Because the failure is the host's own behaviour rather than an injection, this case fails closed:
 * with no genuine business failure in the first pass there is no retry to prove, and the assertion
 * names that reason instead of skipping.
 *
 * On macOS the first pass is the W1 route (schema v6, SEQUENTIAL, one worker) and the retry is the
 * v5 single-point FULL_RESTART route.  Both batches have to prove selected-only execution, the
 * durability watermark, the sealed physical evidence set and their own cleanup.
 */

/** The catalog point whose declared pose the product's own perception threshold rejects. */
const EXPECTED_NATURAL_FAILURE = "sample_05_near_center";
/** 4..20 is the product's range; fifteen is the smallest selection containing that point. */
const NATURAL_FAILURE_SELECTION = 15;

test.afterEach(async ({ request }) => {
  await releaseAcquiredLeases(request);
});

test("R07 a genuinely failed point retries as its own SEQUENTIAL N1 FULL_RESTART batch @live-sim", async ({
  page,
  liveServer,
}) => {
  test.setTimeout(3_600_000);
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  const [manifestResponse] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.url().endsWith("/expert-validation/manifests")
        && candidate.request().method() === "POST",
    ),
    app.generateManifest(NATURAL_FAILURE_SELECTION),
  ]);
  const generated = (await manifestResponse.json()) as { points?: Array<{ id: string }> };
  const firstPassSelection = (generated.points ?? []).map((point) => point.id);
  expect(firstPassSelection).toHaveLength(NATURAL_FAILURE_SELECTION);
  expect(firstPassSelection).toContain(EXPECTED_NATURAL_FAILURE);
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

  // Fifteen points at the measured macOS W1 rate (about 90 s per point, 21.6 min for the recorded
  // fifteen-point leg) plus the single-point retry: the waits and the case timeout are sized for
  // that, not for the four-anchor case this spec used to run.
  const firstPass = await waitForTerminal(1_800_000);
  expect(firstPass?.batch_cleanup_complete).toBe(true);
  const firstPassBatchId = firstPass.batch_id as string;

  // The W1 first pass is a complete batch of its own: its selection, watermark, sealed physical
  // evidence and cleanup all come from its own bytes.
  const firstPassEvidence = readCampaignBatchEvidence(
    join(liveServer.stateDir, "campaigns", campaignId, firstPassBatchId),
  );
  assertCampaignBatchEvidence(firstPassEvidence, {
    ...firstPassExpectation,
    projection: firstPass,
  });

  // A genuine, valid failure is the precondition for the workflow -- never assumed, never faked.
  const statuses = JSON.stringify(
    (firstPass.points ?? []).map((point: any) => [point.point_id, point.status]),
  );
  const failed = (firstPass.points ?? []).filter((point: any) => point.status === "FAILED");
  expect(
    failed.length,
    `NO_GENUINE_FAILURE_IN_SELECTION: no retry can be proven without one; statuses: ${statuses}`,
  ).toBeGreaterThan(0);
  expect(
    failed.length,
    `exactly the catalog's marginal point fails; statuses: ${statuses}`,
  ).toBe(1);
  const target = failed[0];
  expect(
    target.point_id,
    `the failing point is the catalog's own marginal pose; statuses: ${statuses}`,
  ).toBe(EXPECTED_NATURAL_FAILURE);
  expect(target.retry_eligible, "a valid failure is retry eligible").toBe(true);
  expect(
    (target.attempts ?? []).map((attempt: any) => attempt.kind),
    "the first pass has one first-pass attempt for the failed point",
  ).toEqual(["FIRST_PASS"]);

  // The batch's own result document carries the attempt's classification: a business failure has
  // no infrastructure code, and the batch's result names the product's own failure code.
  const attempt = ((firstPassEvidence.cleanup.points?.attempts ?? []) as Array<Record<string, any>>)
    .find((entry) => entry.point_id === target.point_id);
  expect(attempt, "the failed point has its own committed attempt").toBeTruthy();
  expect(attempt!.state, "the failed point is committed").toBe("COMMITTED");
  expect(attempt!.outcome, "the failed point is a business failure").toBe("FAILED");
  expect(attempt!.infrastructure_code, "no infrastructure failure").toBeNull();
  expect(attempt!.failure_code, "the failure names the product's own code").toBeTruthy();

  // The real console workflow: select the failed point, confirm, retry. The campaign endpoint keeps
  // projecting the *first-pass* batch, which is already terminal and clean, so it is not a signal
  // for the retry: the retry endpoint's own response is, because it answers only after the retry's
  // cleanup is verified and names the batch it created.
  const [retryResponse] = await Promise.all([
    page.waitForResponse(
      (candidate) =>
        candidate.url().includes("/full-restart-retries")
        && candidate.request().method() === "POST",
      { timeout: 1_200_000 },
    ),
    app.retryFailedPoints([target.display_id]),
  ]);
  expect(retryResponse.status(), await retryResponse.text()).toBe(200);
  const retryBody = (await retryResponse.json()) as Record<string, unknown>;
  // The endpoint answers with the campaign projection, and that projection's own `batch_id` is still
  // the *first-pass* batch. The retry it admitted is named in the projection's retry history, which
  // is what the console's panel reads (measured: the recorded fast-case response carried
  // `batch_id: b1f44` for the first pass and `retry-001` in its retry history).
  const admitted = ((retryBody.retry_history ?? []) as Array<Record<string, unknown>>)
    .filter((entry) => entry.point_id === target.point_id);
  expect(admitted.length, "the accepted retry is in the campaign's retry history").toBe(1);
  expect(admitted[0].original_batch_id, "the retry names the batch it retries").toBe(firstPassBatchId);
  const admittedBatchId = String(admitted[0].batch_id ?? "");
  expect(admittedBatchId, "the admitted retry names its own batch").toMatch(/^retry-/);

  // The retry is an independent, fresh batch on disk: its own selection, journal and cleanup.
  const campaignRoot = join(liveServer.stateDir, "campaigns", campaignId);
  const retryRoot = join(campaignRoot, admittedBatchId);
  const resultDeadline = Date.now() + 600_000;
  while (Date.now() < resultDeadline && !existsSync(join(retryRoot, "campaign-result.json"))) {
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 5_000));
  }
  expect(existsSync(retryRoot), `retry batch directory: ${retryRoot}`).toBe(true);
  expect(
    existsSync(join(retryRoot, "campaign-result.json")),
    `retry batch result: ${join(retryRoot, "campaign-result.json")}`,
  ).toBe(true);
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

  // The console's own view after the retry: the campaign projection keeps the first-pass batch and
  // adds the admitted retry to its history - never rewriting the first pass's own counters.
  const afterRetry = await readCampaign();
  const retryHistory = (afterRetry.retry_history ?? []) as Array<Record<string, unknown>>;
  expect(
    retryHistory.filter((entry) => entry.point_id === target.point_id).length,
    "the retry appears once in the campaign's retry history",
  ).toBe(1);

  writeFileSync(
    join(liveServer.caseDir, "retry-full-restart.json"),
    JSON.stringify(
      {
        campaign_id: campaignId,
        first_pass_batch_id: firstPassBatchId,
        fault:
          "none: sample_05_near_center fails on its own (catalog marginal cup pose, "
          + `${NATURAL_FAILURE_SELECTION}-point selection; no catalog override, no injection)`,
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
          first_pass_batch_id: afterRetry.batch_id,
          retry_history: retryHistory,
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
