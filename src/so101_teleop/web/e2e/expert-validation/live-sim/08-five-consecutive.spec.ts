import { writeFileSync } from "node:fs";
import { join } from "node:path";

import { liveSimTest as test, expect } from "../fixtures/live-sim";
import {
  ExpertValidationPage,
  releaseAcquiredLeases,
} from "../pages/expert-validation-page";

/**
 * The plan's five consecutive valid physical batches, at ONE configuration.
 *
 * One N, one commit, one parameter set, one lifecycle: five independent twenty-point SEQUENTIAL
 * campaigns at N1, each in its own campaign with its own batch, journal, cleanup and statistics.
 * A batch that is not valid stops the series — the counter reports how many *consecutive* valid
 * batches there were, and an invalid one is never skipped over to reach five.
 */

const CONSECUTIVE_REQUIRED = 5;
const POINTS_PER_BATCH = 20;
const BATCH_TIMEOUT_S = 5400;

test.afterEach(async ({ request }) => {
  await releaseAcquiredLeases(request);
});

test("R08 five consecutive valid physical batches at N1 / 20 points @live-sim", async ({
  page,
  liveServer,
}) => {
  test.setTimeout(CONSECUTIVE_REQUIRED * BATCH_TIMEOUT_S * 1000);
  const app = new ExpertValidationPage(page);
  const recorded: Array<Record<string, unknown>> = [];
  let consecutive = 0;

  for (let batch = 1; batch <= CONSECUTIVE_REQUIRED; batch += 1) {
    await app.goto();
    await app.acquireLease();
    await app.generateManifest(POINTS_PER_BATCH);
    await app.configureSequential();
    await app.runPreflight();
    const campaignId = await app.startValidation();

    const deadline = Date.now() + BATCH_TIMEOUT_S * 1000;
    let projection: any = null;
    while (Date.now() < deadline) {
      const response = await fetch(
        `${liveServer.baseURL}/expert-validation/campaigns/${campaignId}`,
      );
      expect(response.status).toBe(200);
      projection = await response.json();
      if (
        ["COMPLETED", "COMPLETED_WITH_FAILURES", "INFRA_FAILED", "CANCELLED"].includes(
          projection.status,
        ) &&
        projection.batch_cleanup_complete === true
      ) {
        break;
      }
      await new Promise((resolvePromise) => setTimeout(resolvePromise, 15_000));
    }

    const valid =
      projection?.status === "COMPLETED" &&
      projection?.batch_cleanup_complete === true &&
      projection?.execution_mode === "SEQUENTIAL" &&
      projection?.requested === POINTS_PER_BATCH &&
      projection?.evaluated === POINTS_PER_BATCH &&
      projection?.infra_attempts === 0 &&
      (projection?.points ?? []).length === POINTS_PER_BATCH &&
      (projection?.points ?? []).every((point: any) => point.status === "PASSED");
    consecutive = valid ? consecutive + 1 : 0;
    recorded.push({
      consecutive_index: batch,
      campaign_id: campaignId,
      batch_id: projection?.batch_id,
      status: projection?.status,
      requested: projection?.requested,
      evaluated: projection?.evaluated,
      workers: (projection?.workers ?? []).length,
      infra_attempts: projection?.infra_attempts,
      cleanup_complete: projection?.batch_cleanup_complete,
      valid,
      consecutive_valid_so_far: consecutive,
      point_statuses: (projection?.points ?? []).map((point: any) => [
        point.display_id,
        point.status,
      ]),
    });
    writeFileSync(
      join(liveServer.caseDir, "five-consecutive.json"),
      JSON.stringify(
        {
          requirement: {
            consecutive: CONSECUTIVE_REQUIRED,
            points_per_batch: POINTS_PER_BATCH,
            mode: "SEQUENTIAL",
            worker_count: 1,
            lifecycle: "FULL_RESTART",
            batch_timeout_s: BATCH_TIMEOUT_S,
          },
          batches: recorded,
        },
        null,
        2,
      ) + "\n",
    );
    await releaseAcquiredLeases(page.request);
    if (!valid) break;
  }

  expect(
    consecutive,
    `five consecutive valid batches; recorded: ${JSON.stringify(
      recorded.map((row) => [row.consecutive_index, row.status, row.valid]),
    )}`,
  ).toBe(CONSECUTIVE_REQUIRED);
});
