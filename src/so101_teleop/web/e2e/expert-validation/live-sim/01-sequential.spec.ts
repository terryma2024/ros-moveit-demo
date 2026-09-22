import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { liveSimTest as test, expect, recordGate } from "../fixtures/live-sim";
import { readJournalEvents } from "../assertions/journal";
import {
  assertCleanupComplete,
  assertPhysicalEvidenceSet,
  assertProjectedPointEvidence,
  assertSelectedOnlyAttempts,
  assertSequenceAndWatermark,
  campaignJournalRoot,
  committedAttempts,
  readCampaignBatchEvidence,
  readSealedAttempt,
  type CampaignBatchExpectation,
} from "../assertions/live-evidence";
import {
  ExpertValidationPage,
  releaseAcquiredLeases,
} from "../pages/expert-validation-page";

/**
 * R01: four-point SEQUENTIAL live MuJoCo smoke through real Chrome and the
 * production entry.  Page success is flow evidence only; per-point robot
 * qualification is reported from sealed artifacts, never from the page.
 */

// The exclusive lease belongs to the deployed service, not to this spec: hand it back
// even when the test fails, or the next spec is refused with 409 Conflict.
test.afterEach(async ({ request }) => {
  await releaseAcquiredLeases(request);
});

test("R01 four-point sequential live smoke @live-sim", async ({ page, liveServer }) => {
  test.setTimeout(1_800_000);
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(4);
  await app.configureSequential();
  // The receipt is this spec's own routing claim: which matrix row the console asked for.
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
  // The campaign id comes from this spec's own start response: the campaign list also holds the
  // campaigns of every spec that ran before it.
  const campaignId = await app.startValidation();

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
  const batchRoot = join(liveServer.stateDir, "campaigns", campaignId, projection.batch_id);
  const batchEvidence = readCampaignBatchEvidence(batchRoot);
  for (const point of projection.points) {
    expect(["PASSED", "FAILED"]).toContain(point.status);
  }
  const expectation: CampaignBatchExpectation = {
    batchKind: "FIRST_PASS",
    executionProfile: String(receipt.execution_profile ?? ""),
    schemaVersion: Number(receipt.execution_schema_version ?? 0),
    workerCount: 1,
    selectedPointIds: projection.points.map((point: any) => point.point_id),
    projection,
  };
  // Per-point evidence is what this batch's own layout produces: the projection's registered
  // artifacts on the Linux/fixed layout, the committed point result on the macOS composed one.
  assertProjectedPointEvidence(batchEvidence, projection);

  // Evidence-level, per layout.  The Linux/fixed layout keeps its coordinator journal, its cleanup
  // gates and its sealed attempt trees; the macOS composed layout is verified from its own bytes by
  // the shared reader (selection, watermark, physical evidence, cleanup), never by Linux paths.
  const perPoint: Array<Record<string, unknown>> = [];
  if (batchEvidence.layout === "LINUX_FIXED") {
    // Journal-level: one coordinator epoch, four committed results, cleanup.
    const events = readJournalEvents(join(batchRoot, "coordinator"));
    expect(events.filter((event) => event.type === "BATCH_STARTED")).toHaveLength(1);
    expect(events.filter((event) => event.type === "RESULT_COMMITTED")).toHaveLength(4);
    expect(events.some((event) => event.type === "BATCH_CLEANUP_COMPLETE")).toBe(true);
    expect(existsSync(join(batchRoot, "cleanup-gates.json"))).toBe(true);

    // Every point has a verifiable sealed attempt on disk.
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
  } else {
    // The composed layout: selected-only execution, the durable watermark, the physical evidence
    // set and the completed cleanup, each recomputed from the batch's own documents.
    assertSelectedOnlyAttempts(batchEvidence, expectation);
    assertSequenceAndWatermark(batchEvidence);
    assertPhysicalEvidenceSet(batchEvidence);
    assertCleanupComplete(batchEvidence, projection);
    const commits = readJournalEvents(campaignJournalRoot(batchRoot))
      .filter((event) => event.type === "RESULT_COMMITTED");
    expect(commits).toHaveLength(4);
    const byPoint = new Map(projection.points.map((point: any) => [point.point_id, point]));
    for (const attempt of committedAttempts(batchEvidence)) {
      const point = byPoint.get(attempt.pointId) as any;
      expect(point, `${attempt.pointId} is a selected point`).toBeTruthy();
      perPoint.push({
        point_id: attempt.pointId,
        status: point.status,
        evidence_stage: "composed",
        sealed: attempt.sealedDir,
      });
    }
    expect(perPoint).toHaveLength(4);
  }

  // Runtime identity evidence: ROS domain claim, no Gazebo partition.
  const identity = {
    ros_domain_id: process.env.SO101_LIVE_ROS_DOMAIN_ID ?? "179",
    gz_partition: "not_applicable",
    source_commit: liveServer.preconditions.sourceCommit,
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

  // Only a fully clean run opens the R02 gate, and the receipt binds the run identity
  // that later suites must re-check instead of trusting the filename.
  const receiptIdentity = await (
    await fetch(`${liveServer.baseURL}/expert-validation/campaigns/${campaignId}`)
  ).json();
  const batch = receiptIdentity.batches?.[0] ?? {};
  recordGate(process.env.SO101_E2E_EVIDENCE_ROOT!, "R01", {
    campaign_id: campaignId,
    status: projection.status,
    points: perPoint,
    producer: "producer01",
    evidence_root: process.env.SO101_E2E_EVIDENCE_ROOT,
    execution_identity_sha256: batch.execution_identity_sha256 ?? null,
    profile_sha256: batch.profile_sha256 ?? null,
    qualification_sha256: batch.qualification_sha256 ?? null,
    manifest_sha256: batch.manifest_sha256 ?? null,
    cleanup_complete: projection.batch_cleanup_complete === true,
    run_id: `${campaignId}:${batch.batch_id ?? ""}`,
  });
});
