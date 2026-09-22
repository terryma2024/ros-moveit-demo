import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { type Page } from "@playwright/test";

import { liveSimTest as test, expect } from "../fixtures/live-sim";
import { readJournalEvents } from "../assertions/journal";
import {
  assertCampaignBatchEvidence,
  assertProjectedPointEvidence,
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
 * Real per-option execution, restricted to what macOS actually runs.
 *
 * `05-functional-manifest.spec.ts` asks the deployed service what it advertises; this file takes
 * the same manifest and, for every case, either executes it through the console or proves the
 * console cannot offer it. On macOS the execution contract is W1/W2 only: PARALLEL N=2 is the W2
 * route (schema v4) and SEQUENTIAL N=1 is the W1 first-pass route (schema v6). PARALLEL N=1,
 * N=3..N8 and ADAPTIVE are not routes, so the console has to refuse them and say why.
 *
 * A capability check is not an execution result, so each executed case asserts its own claimed
 * profile, worker count, selected-only evidence, seam of sealed physical evidence, watermark and
 * cleanup.
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

type MatrixRoute = {
  profile: string;
  schema_version: number;
  execution_mode: string;
  worker_count: number;
  batch_kind: string;
};

function loadManifest(): FunctionalManifest {
  const path = process.env.SO101_FUNCTIONAL_MANIFEST ?? "";
  if (!path) throw new Error("FUNCTIONAL_MANIFEST_REQUIRED");
  return JSON.parse(readFileSync(path, "utf8")) as FunctionalManifest;
}

/** The first-pass routes this host actually carries, keyed by `MODE/worker_count`. */
async function deployedFirstPassRoutes(baseURL: string): Promise<Map<string, MatrixRoute>> {
  const response = await fetch(`${baseURL}/expert-validation/capabilities`);
  expect(response.ok, "capabilities").toBe(true);
  const capabilities = (await response.json()) as {
    platform?: string;
    support_matrix?: MatrixRoute[];
  };
  expect(capabilities.platform).toBe("macos");
  const routes = new Map<string, MatrixRoute>();
  for (const row of capabilities.support_matrix ?? []) {
    if (row.batch_kind !== "FIRST_PASS") continue;
    routes.set(`${row.execution_mode}/${row.worker_count}`, row);
  }
  return routes;
}

/** A case the matrix does not carry must be unavailable in the console, with its own reason. */
async function expectRefusedInConsole(page: Page, entry: FunctionalCase): Promise<void> {
  const modeSelect = page.getByLabel("Execution mode");
  const modes = await modeSelect.locator("option").allTextContents();
  expect(modes, "advertised execution modes").toEqual(["SEQUENTIAL", "PARALLEL"]);
  expect(modes, `${entry.id} must not offer an adaptive route`).not.toContain("ADAPTIVE");
  if (entry.mode === "ADAPTIVE") return;

  await modeSelect.selectOption(entry.mode);
  const option = page.getByLabel("Worker count").locator(`option[value="${entry.worker_count}"]`);
  await expect(option, `${entry.id} option`).toBeDisabled();
  if (entry.mode === "PARALLEL" && entry.worker_count === 1) {
    // One worker is the sequential route, never a parallel one.
    await expect(option).toContainText("SEQUENTIAL");
  } else {
    await expect(option).toContainText("UNSUPPORTED_ON_MACOS");
    await expect(
      page.getByText(`N${entry.worker_count} unavailable · UNSUPPORTED_ON_MACOS`),
    ).toBeVisible();
  }
  await expect(
    page.getByRole("button", { name: "Start validation" }),
    `${entry.id} must not be startable`,
  ).toBeDisabled();
}

// `FULL_RESTART_RETRY` is a single-point retry through the failure workflow, not a first-pass
// execution; it is driven by the retry spec and deliberately not claimed here.
const executions = loadManifest().cases.filter((entry) => entry.lifecycle === "FIRST_PASS");

// The claimed profile per route, so two point counts under the same route compare against each
// other rather than against a value from the capabilities document.
const claimedProfiles = new Map<string, string>();

test.afterEach(async ({ request }) => {
  await releaseAcquiredLeases(request);
});

for (const entry of executions) {
  test(`R06 ${entry.id} executes ${entry.worker_count}×${entry.point_count} or is refused @live-sim`, async ({
    page,
    liveServer,
  }) => {
    test.setTimeout(entry.batch_timeout_s * 1000);
    const routes = await deployedFirstPassRoutes(liveServer.baseURL);
    const route = routes.get(`${entry.mode}/${entry.worker_count}`);
    const app = new ExpertValidationPage(page);
    await app.goto();

    if (!route) {
      await expectRefusedInConsole(page, entry);
      writeFileSync(
        join(liveServer.caseDir, `refused-${entry.id}.json`),
        JSON.stringify({ case: entry, reason: "NOT_IN_THE_MACOS_SUPPORT_MATRIX" }, null, 2) + "\n",
      );
      return;
    }

    await app.acquireLease();
    const [manifestResponse] = await Promise.all([
      page.waitForResponse(
        (candidate) =>
          candidate.url().endsWith("/expert-validation/manifests")
          && candidate.request().method() === "POST",
      ),
      app.generateManifest(entry.point_count),
    ]);
    const generated = (await manifestResponse.json()) as { points?: Array<{ id: string }> };
    const selectedPointIds = (generated.points ?? []).map((point) => point.id);
    expect(selectedPointIds).toHaveLength(entry.point_count);
    const expectation: CampaignBatchExpectation = {
      batchKind: "FIRST_PASS",
      executionProfile: route.profile,
      schemaVersion: route.schema_version,
      workerCount: entry.worker_count,
      selectedPointIds,
    };

    if (entry.mode === "PARALLEL") await app.configureParallel(entry.worker_count);
    else await app.configureSequential();

    const [preflightResponse] = await Promise.all([
      page.waitForResponse(
        (candidate) =>
          candidate.url().endsWith("/expert-validation/campaigns/preflight")
          && candidate.request().method() === "POST",
      ),
      app.runPreflight(),
    ]);
    if (preflightResponse.status() !== 200) {
      throw new Error(
        `PREFLIGHT_REFUSED: ${preflightResponse.status()} ${await preflightResponse.text()}`);
    }
    const receipt = (await preflightResponse.json()) as Record<string, unknown>;
    assertRoutingClaim(receipt, expectation);
    // The point count never selects the profile: this route's other point count claimed the same
    // row, and the receipt's own bytes are what says so.
    const previous = claimedProfiles.get(`${entry.mode}/${entry.worker_count}`);
    if (previous) expect(receipt.execution_profile).toBe(previous);
    claimedProfiles.set(`${entry.mode}/${entry.worker_count}`, String(receipt.execution_profile));

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
      route,
      campaign_id: campaignId,
      batch_id: projection.batch_id,
      status: projection.status,
      execution_mode: projection.execution_mode,
      requested: projection.requested,
      evaluated: projection.evaluated,
      execution_started: projection.execution_started,
      cleanup_complete: projection.batch_cleanup_complete,
      claim: {
        execution_profile: receipt.execution_profile,
        execution_schema_version: receipt.execution_schema_version,
        execution_batch_kind: receipt.execution_batch_kind,
      },
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
    expect(projection.workers).toHaveLength(entry.worker_count);
    // The batch on disk proves the same four claims from its own bytes: the selection, the
    // committed watermark, the sealed physical evidence and the completed cleanup.
    const batchEvidence = readCampaignBatchEvidence(batchRoot);
    for (const point of projection.points) {
      expect(["PASSED", "FAILED"], `${point.display_id} terminal`).toContain(point.status);
      // Selected-only and first-pass: one attempt per point, and never a retry attempt here.
      expect((point.attempts ?? []).map((attempt: any) => attempt.kind), `${point.display_id}`)
        .toEqual(["FIRST_PASS"]);
    }
    // Per-point evidence is the evidence *this batch's layout* produces: the projection's
    // registered artifacts on the Linux/fixed layout, the committed point result on the macOS
    // composed one. Missing or tampered evidence refuses on both.
    assertProjectedPointEvidence(batchEvidence, projection);
    assertCampaignBatchEvidence(batchEvidence, { ...expectation, projection });
    const commits = readJournalEvents(campaignJournalRoot(batchRoot))
      .filter((event) => event.type === "RESULT_COMMITTED");
    expect(commits).toHaveLength(entry.point_count);
    if (batchEvidence.layout === "LINUX_FIXED") {
      expect(readFileSync(join(batchRoot, "cleanup-gates.json"), "utf8")).toContain(
        "batch_cleanup_complete",
      );
    } else {
      // The composed campaign closes in its own verdict document, not in the fixed coordinator's
      // cleanup gates file.
      const verdict = JSON.parse(
        readFileSync(join(batchRoot, "campaign-result.json"), "utf8"),
      ) as { cleanup?: { complete?: boolean }; points?: { complete?: boolean } };
      expect(verdict.cleanup?.complete, "campaign cleanup").toBe(true);
      expect(verdict.points?.complete, "campaign points").toBe(true);
    }
    writeFileSync(
      join(liveServer.caseDir, `execution-${entry.id}-evidence.json`),
      JSON.stringify({
        expectation,
        manifest: batchEvidence.manifest,
        watermark: batchEvidence.watermark,
        commits: commits.map((event) => event.payload),
      }, null, 2) + "\n",
    );
  });
}
