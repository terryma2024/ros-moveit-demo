import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { liveSimTest as test, expect } from "../fixtures/live-sim";
import { storeQuery } from "../assertions/journal";
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
  await app.generateManifest(4);
  await app.configureSequential();
  await app.runPreflight();
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

  // The retry is an independent, fresh batch on disk: its own manifest, journal and cleanup.
  const campaignRoot = join(liveServer.stateDir, "campaigns", campaignId);
  const retryRoot = join(campaignRoot, "retry-001");
  expect(existsSync(retryRoot), `retry batch directory: ${retryRoot}`).toBe(true);
  const retryManifest = JSON.parse(
    readFileSync(join(retryRoot, "batch_manifest.json"), "utf8"),
  ) as { batch_id?: string; batch_kind?: string; selected_point_ids?: string[]; worker_count?: number };
  expect(retryManifest.batch_kind).toBe("FULL_RESTART_RETRY");
  expect(retryManifest.batch_id).not.toBe(firstPassBatchId);
  expect(retryManifest.selected_point_ids).toEqual([target.point_id]);
  expect(retryManifest.worker_count).toBe(1);
  expect(existsSync(join(retryRoot, "cleanup-gates.json"))).toBe(true);
  expect(existsSync(join(retryRoot, "coordinator", "events"))).toBe(true);

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
        retry_batch: retryManifest,
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
