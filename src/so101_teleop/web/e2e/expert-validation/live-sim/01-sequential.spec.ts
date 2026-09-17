import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { liveSimTest as test, expect, recordGate, validateLiveSimPreconditions } from "../fixtures/live-sim";
import { readJournalEvents } from "../assertions/journal";
import { readSealedAttempt } from "../assertions/live-evidence";
import { ExpertValidationPage } from "../pages/expert-validation-page";

/**
 * R01: four-point SEQUENTIAL live MuJoCo smoke through real Chrome and the
 * production entry.  Page success is flow evidence only; per-point robot
 * qualification is reported from sealed artifacts, never from the page.
 */

test("R01 four-point sequential live smoke @live-sim", async ({ page, liveServer }) => {
  test.setTimeout(1_800_000);
  // Provenance is proven at startup; MuJoCo runtime logs dirty the tree mid-run.
  const preconditions = validateLiveSimPreconditions();
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(4);
  await app.configureSequential();
  await app.runPreflight();
  await app.startValidation();

  const campaignsResponse = await fetch(`${liveServer.baseURL}/expert-validation/campaigns`);
  const campaigns = await campaignsResponse.json();
  expect(campaigns).toHaveLength(1);
  const campaignId = campaigns[0].campaign_id;

  // Wait for a safe terminal state with full cleanup.
  const deadline = Date.now() + 1_500_000;
  let projection: any = null;
  let midCaptured = false;
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
    if (!midCaptured && projection.status === "RUNNING") {
      await page.screenshot({ path: join(liveServer.caseDir, "mid-run.png") }).catch(() => {});
      midCaptured = true;
    }
    await new Promise((resolvePromise) => setTimeout(resolvePromise, 5_000));
  }
  expect(projection?.batch_cleanup_complete).toBe(true);
  expect(["COMPLETED", "COMPLETED_WITH_FAILURES"]).toContain(projection?.status);

  // Flow-level: every point reached a definite verdict.
  expect(projection.points).toHaveLength(4);
  for (const point of projection.points) {
    expect(["PASSED", "FAILED"]).toContain(point.status);
    expect(point.artifacts.length).toBeGreaterThan(0);
  }

  // Journal-level: one coordinator epoch, four committed results, cleanup.
  const batchRoot = join(liveServer.stateDir, "campaigns", campaignId, projection.batch_id);
  const events = readJournalEvents(join(batchRoot, "coordinator"));
  expect(events.filter((event) => event.type === "BATCH_STARTED")).toHaveLength(1);
  expect(events.filter((event) => event.type === "RESULT_COMMITTED")).toHaveLength(4);
  expect(events.some((event) => event.type === "BATCH_CLEANUP_COMPLETE")).toBe(true);
  expect(existsSync(join(batchRoot, "cleanup-gates.json"))).toBe(true);

  // Evidence-level: every point has a verifiable sealed attempt on disk.
  const perPoint: Array<Record<string, unknown>> = [];
  for (const point of projection.points) {
    const attemptsRoot = join(batchRoot, "workers");
    const sealed = readdirSync(attemptsRoot).flatMap((workerId) => {
      const pointDir = join(attemptsRoot, workerId, "attempts", point.point_id);
      if (!existsSync(pointDir)) return [];
      return readdirSync(pointDir).map((attemptId) => join(pointDir, attemptId, "sealed"));
    }).filter((dir) => existsSync(join(dir, "attempt_result_manifest.json")));
    expect(sealed.length).toBeGreaterThan(0);
    const { manifest, files } = readSealedAttempt(sealed[sealed.length - 1]);
    expect(files.has("initial-rgb.png")).toBe(true);
    expect(files.has("attempt-result.json")).toBe(true);
    perPoint.push({
      point_id: point.point_id,
      status: point.status,
      evidence_stage: manifest.evidence_stage ?? null,
      sealed: sealed[sealed.length - 1],
    });
  }

  // Runtime identity evidence: ROS domain claim, no Gazebo partition.
  const identity = {
    ros_domain_id: process.env.SO101_LIVE_ROS_DOMAIN_ID ?? "179",
    gz_partition: "not_applicable",
    source_commit: preconditions.sourceCommit,
    install_prefix: process.env.SO101_E2E_INSTALL_PREFIX,
    server_pid: null as null,
  };
  writeFileSync(
    join(liveServer.caseDir, "runtime-identity.json"),
    JSON.stringify(identity, null, 2) + "\n",
  );
  writeFileSync(
    join(liveServer.caseDir, "per-point-qualification.json"),
    JSON.stringify(perPoint, null, 2) + "\n",
  );
  await page.screenshot({ path: join(liveServer.caseDir, "final.png") });

  // Only a fully clean run opens the R02 gate.
  recordGate(process.env.SO101_E2E_EVIDENCE_ROOT!, "R01", {
    campaign_id: campaignId,
    status: projection.status,
    points: perPoint,
  });
});
