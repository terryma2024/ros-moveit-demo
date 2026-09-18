import { writeFileSync } from "node:fs";
import { join } from "node:path";

import { liveSimTest as test, expect, recordGate, requireGate } from "../fixtures/live-sim";
import {
  ExpertValidationPage,
  releaseAcquiredLeases,
} from "../pages/expert-validation-page";

/**
 * R03: 20-point ADAPTIVE live run on the Web default ladder (W8).  R05 is
 * embedded: only a safe terminal first pass with eligible business FAILED
 * points proceeds to real per-point FULL_RESTART retries.
 */

// The exclusive lease belongs to the deployed service, not to this spec: hand it back
// even when the test fails, or the next spec is refused with 409 Conflict.
test.afterEach(async ({ request }) => {
  await releaseAcquiredLeases(request);
});

test("R03 twenty-point adaptive live run @live-sim", async ({ page, liveServer }) => {
  test.setTimeout(3_600_000);
  requireGate(process.env.SO101_E2E_EVIDENCE_ROOT!, "R02");

  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(20);
  await app.configureAdaptive();
  await app.runPreflight();
  await app.startValidation();

  const campaigns = await (
    await fetch(`${liveServer.baseURL}/expert-validation/campaigns`)
  ).json();
  expect(campaigns).toHaveLength(1);
  const campaignId = campaigns[0].campaign_id;

  const deadline = Date.now() + 3_300_000;
  let projection: any = null;
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
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 10_000));
  }
  expect(projection?.batch_cleanup_complete).toBe(true);
  expect(projection?.status).not.toBe("INFRA_FAILED");
  expect(["COMPLETED", "COMPLETED_WITH_FAILURES"]).toContain(projection?.status);
  expect(projection.points).toHaveLength(20);

  writeFileSync(
    join(liveServer.caseDir, "adaptive-projection.json"),
    JSON.stringify(
      {
        status: projection.status,
        levels_used: projection.levels_used ?? [],
        fallback_history: projection.fallback_history ?? [],
        current_generation: projection.current_generation ?? null,
        infra_attempts: projection.infra_attempts ?? 0,
        requested: projection.requested,
        valid_succeeded: projection.valid_succeeded,
        valid_failed: projection.valid_failed,
        indeterminate: projection.indeterminate,
      },
      null,
      2,
    ) + "\n",
  );
  await page.screenshot({ path: join(liveServer.caseDir, "final.png") });

  recordGate(process.env.SO101_E2E_EVIDENCE_ROOT!, "R03", {
    campaign_id: campaignId,
    status: projection.status,
  });

  // R05: conditional real retry of eligible business failures.
  const eligible = projection.points.filter(
    (point: any) => point.status === "FAILED" && point.retry_eligible === true,
  );
  const unsafe = projection.points.filter(
    (point: any) => !["PASSED", "FAILED"].includes(point.status),
  );
  if (unsafe.length > 0) {
    throw new Error(
      `R05_PRECONDITION_FAILED: non-final points ${unsafe.map((p: any) => p.point_id).join(",")}`,
    );
  }
  if (eligible.length === 0) {
    const verdict = "LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED";
    writeFileSync(
      join(liveServer.caseDir, "r05-verdict.json"),
      JSON.stringify({ verdict }, null, 2) + "\n",
    );
    recordGate(process.env.SO101_E2E_EVIDENCE_ROOT!, "R05", { verdict });
    return;
  }

  const firstPassStats = {
    requested: projection.requested,
    valid_succeeded: projection.valid_succeeded,
    valid_failed: projection.valid_failed,
  };
  for (const point of eligible) {
    await app.selectPoint(point.display_id);
    await app.retryFailedPoints([point.display_id]);
    const after = await (
      await fetch(`${liveServer.baseURL}/expert-validation/campaigns/${campaignId}`)
    ).json();
    expect(after.requested).toBe(firstPassStats.requested);
    expect(after.valid_succeeded).toBe(firstPassStats.valid_succeeded);
    expect(after.valid_failed).toBe(firstPassStats.valid_failed);
  }
  recordGate(process.env.SO101_E2E_EVIDENCE_ROOT!, "R05", {
    verdict: "RETRIED",
    points: eligible.map((point: any) => point.point_id),
  });
});
