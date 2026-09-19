import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { liveSimTest as test, expect } from "../fixtures/live-sim";
import {
  ExpertValidationPage,
  releaseAcquiredLeases,
} from "../pages/expert-validation-page";

/**
 * Real per-option execution.
 *
 * `05-functional-manifest.spec.ts` asks the deployed service what it advertises; this file runs
 * the workloads those options describe, one campaign per manifest case, through the same console
 * the operator uses.  A capability check is not an execution result, and an aggregate `PASSED`
 * is not per-point evidence, so each case asserts its own requested/actual worker count, all N
 * worker slots, every point's terminal state and the cleanup that closes the batch.
 */

type FunctionalCase = {
  id: string;
  mode: "SEQUENTIAL" | "PARALLEL" | "ADAPTIVE";
  worker_count: number;
  point_count: number;
  lifecycle: string;
  maximum_attempts: number;
  batch_timeout_s: number;
};

type FunctionalManifest = { cases: FunctionalCase[]; stability: FunctionalCase };

function loadManifest(): FunctionalManifest {
  const path = process.env.SO101_FUNCTIONAL_MANIFEST ?? "";
  if (!path) throw new Error("FUNCTIONAL_MANIFEST_REQUIRED");
  return JSON.parse(readFileSync(path, "utf8")) as FunctionalManifest;
}

// `FULL_RESTART_RETRY` is a single-point retry through the failure workflow, not a first-pass
// execution; it is driven by the retry case and deliberately not claimed here.
const executions = loadManifest().cases.filter((entry) => entry.lifecycle === "FIRST_PASS");

test.afterEach(async ({ request }) => {
  await releaseAcquiredLeases(request);
});

for (const entry of executions) {
  test(`R06 ${entry.id} executes ${entry.worker_count}×${entry.point_count} for real @live-sim`, async ({
    page,
    liveServer,
  }) => {
    test.setTimeout(entry.batch_timeout_s * 1000);
    const app = new ExpertValidationPage(page);
    await app.goto();
    await app.acquireLease();
    await app.generateManifest(entry.point_count);
    if (entry.mode === "PARALLEL") {
      await app.configureParallel(entry.worker_count);
    } else if (entry.mode === "SEQUENTIAL") {
      await app.configureSequential();
    } else {
      await app.configureAdaptive();
    }
    await app.runPreflight();
    const campaignId = await app.startValidation();

    // Bounded polling: every check is short, the deadline is the manifest's batch timeout.
    const deadline = Date.now() + entry.batch_timeout_s * 1000;
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
    await page.screenshot({ path: join(liveServer.caseDir, "final.png") });

    const batchRoot = join(liveServer.stateDir, "campaigns", campaignId, projection.batch_id);
    const evidence = {
      case: entry,
      campaign_id: campaignId,
      batch_id: projection.batch_id,
      status: projection.status,
      execution_mode: projection.execution_mode,
      requested: projection.requested,
      evaluated: projection.evaluated,
      execution_started: projection.execution_started,
      cleanup_complete: projection.batch_cleanup_complete,
      workers: (projection.workers ?? []).map((worker: any) => ({
        worker_id: worker.worker_id,
        state: worker.state,
        lease_count: worker.lease_count,
      })),
      points: (projection.points ?? []).map((point: any) => ({
        display_id: point.display_id,
        point_id: point.point_id,
        status: point.status,
        artifacts: point.artifacts?.length ?? 0,
        attempts: point.attempts?.length ?? 0,
      })),
    };
    writeFileSync(
      join(liveServer.caseDir, `execution-${entry.id}.json`),
      JSON.stringify(evidence, null, 2) + "\n",
    );

    // The campaign reached a terminal state with its batch cleaned up.
    expect(["COMPLETED", "COMPLETED_WITH_FAILURES"]).toContain(projection.status);
    expect(projection.batch_cleanup_complete).toBe(true);
    expect(projection.execution_mode).toBe(entry.mode);

    // The requested workload is the executed workload: exact N slots, every point run.
    expect(projection.requested).toBe(entry.point_count);
    expect(projection.evaluated).toBe(entry.point_count);
    expect(projection.points).toHaveLength(entry.point_count);
    if (entry.mode === "PARALLEL") {
      // Fixed mode creates all N slots even when the campaign has fewer points than N.
      expect(projection.workers).toHaveLength(entry.worker_count);
    }
    for (const point of projection.points) {
      expect(["PASSED", "FAILED"], `${point.display_id} terminal`).toContain(point.status);
    }
    if (entry.mode === "ADAPTIVE") {
      // Adaptive results are imported from the pool's workers, so a point's evidence lives in the
      // pool's per-worker attempt directories rather than in the campaign projection's artifact
      // list — the plan's own `03-adaptive` spec reads the same shape.  Every point must still
      // have its own attempt directory: an aggregate `PASSED` is not per-point evidence.
      const poolRoot = join(batchRoot, "r", projection.batch_id, "p");
      const generations = readdirSync(poolRoot).filter((name) => !name.endsWith(".json"));
      expect(generations.length, "one pool generation").toBeGreaterThan(0);
      const attempts = new Set<string>();
      for (const generation of generations) {
        const workersRoot = join(poolRoot, generation, "workers");
        for (const workerId of readdirSync(workersRoot)) {
          const workerAttempts = join(workersRoot, workerId, "attempts");
          if (!existsSync(workerAttempts)) continue;
          for (const pointId of readdirSync(workerAttempts)) attempts.add(pointId);
        }
      }
      expect([...attempts].sort(), "every adaptive point has an attempt on disk").toEqual(
        projection.points.map((point: any) => point.point_id).sort(),
      );
    } else {
      for (const point of projection.points) {
        expect(point.artifacts.length, `${point.display_id} artifacts`).toBeGreaterThan(0);
      }
    }

    // The batch on disk knows the same identity and finished its own cleanup.
    expect(projection.batch_id).toBeTruthy();
    expect(readFileSync(join(batchRoot, "cleanup-gates.json"), "utf8")).toContain(
      "batch_cleanup_complete",
    );
  });
}
