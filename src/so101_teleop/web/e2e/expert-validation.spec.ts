import { expect, test, type Page } from "@playwright/test";
import golden from "../src/fixtures/top_view_projection_v1.json" with { type: "json" };

const baseCampaign = {
  campaign_id: "campaign-adaptive",
  manifest_id: "manifest-e2e-20",
  sequence: 4,
  execution_mode: "ADAPTIVE",
  owner_kind: "ADAPTIVE_WRAPPER",
  batch_id: "adaptive-first-pass",
  status: "RUNNING",
  points: [{
    point_id: "sample_05_near_center",
    display_id: "P09",
    status: "INFRA_INTERRUPTED_REQUEUEABLE",
    retry_eligible: false,
    active_worker_id: "worker-2",
    reason: "BROKER_PAUSED",
    attempts: [{ generation: 1, kind: "FIRST_PASS", status: "INDETERMINATE", reason: "BROKER_PAUSED" }],
    artifact_ids: [],
    artifacts: [],
  }],
  workers: [
    { worker_id: "worker-1", generation: 2, state: "READY", lease_count: 2 },
    { worker_id: "worker-2", generation: 2, state: "EXECUTING", current_point_id: "sample_05_near_center", lease_count: 2 },
  ],
  broker: { available: false, reason: "RECOVERING" },
  requested: 20,
  evaluated: 8,
  execution_started: 8,
  valid_succeeded: 7,
  valid_failed: 0,
  indeterminate: 1,
  not_executed: 12,
  evaluation_coverage: 0.4,
  execution_coverage: 0.4,
  batch_cleanup_complete: false,
  levels_used: [8, 6],
  fallback_history: [{ from_count: 8, to_count: 6, reason: "WORKER_START_FAILED" }],
  current_generation: 2,
  infra_attempts: 1,
  resource_observations: { memory_pressure: "HIGH" },
};

const terminalCampaign = {
  ...baseCampaign,
  sequence: 7,
  status: "COMPLETED_WITH_FAILURES",
  points: [{
    ...baseCampaign.points[0],
    status: "FAILED",
    retry_eligible: true,
    active_worker_id: null,
    reason: "TARGET_TOLERANCE_EXCEEDED",
  }],
  broker: { available: true, reason: null },
  evaluated: 20,
  execution_started: 20,
  valid_succeeded: 19,
  valid_failed: 1,
  indeterminate: 0,
  not_executed: 0,
  evaluation_coverage: 1,
  execution_coverage: 1,
  batch_cleanup_complete: true,
};

async function installFakeRunner(page: Page) {
  const state: { lastRetryBody?: Record<string, unknown>; campaignGets: number } = {
    campaignGets: 0,
  };
  await page.addInitScript(() => {
    class FakeRunnerSocket extends EventTarget {
      static readonly OPEN = 1;
      readyState = FakeRunnerSocket.OPEN;

      constructor(_url: string) {
        super();
        setTimeout(() => {
          this.dispatchEvent(new MessageEvent("message", {
            data: JSON.stringify({ campaign_id: "campaign-adaptive", sequence: 5 }),
          }));
          this.dispatchEvent(new MessageEvent("message", {
            data: JSON.stringify({ campaign_id: "campaign-adaptive", sequence: 7 }),
          }));
        }, 25);
      }

      close() { this.readyState = 3; }
    }
    Object.defineProperty(window, "WebSocket", { configurable: true, value: FakeRunnerSocket });
  });
  await page.route("**/expert-validation/capabilities", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      available: true,
      execution_modes: ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"],
      default_execution_mode: "SEQUENTIAL",
      minimum_points: 4,
      maximum_points: 20,
      fixed_worker_counts: [1, 2, 3],
      fixed_max_points_per_worker: 20,
      adaptive_default_ladder: [8, 6, 4, 2, 1],
      lease_duration_s: 30,
      lease_renewal_margin_s: 10,
    }),
  }));
  await page.route("**/expert-validation/manifests/manifest-e2e-20", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      manifest_id: "manifest-e2e-20", point_count: 20, stale: false,
      points: golden.points.map((point, index) => ({ ...point, label: point.id,
        source: index < 4 ? "anchor" : "generated", stratum: index < 4 ? "anchor" : point.id.split("_").slice(2).join("/"),
      })),
      top_view: { ...golden, geometry: { ...golden.geometry, candidate_bounds: [-0.045, 0.08, -0.34, -0.24] } },
    }),
  }));
  await page.route("**/expert-validation/lease", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      lease_id: "lease-e2e",
      service_session_id: route.request().postDataJSON().service_session_id,
      generation: 1,
      expires_monotonic_ns: 9_999_999_999_999_999,
    }),
  }));
  await page.route("**/expert-validation/campaigns", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify([baseCampaign]),
  }));
  await page.route("**/expert-validation/campaigns/campaign-adaptive", (route) => {
    state.campaignGets += 1;
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(terminalCampaign) });
  });
  await page.route("**/expert-validation/campaigns/campaign-adaptive/full-restart-retries", async (route) => {
    state.lastRetryBody = route.request().postDataJSON();
    const retryCampaign = {
      ...terminalCampaign,
      sequence: 8,
      points: [{
        ...terminalCampaign.points[0],
        status: "PASSED",
        retry_eligible: false,
        reason: null,
        attempts: [
          ...terminalCampaign.points[0].attempts,
          { generation: 2, kind: "FULL_RESTART_RETRY", status: "PASSED", reason: null },
        ],
      }],
    };
    return route.fulfill({ contentType: "application/json", body: JSON.stringify(retryCampaign) });
  });
  return state;
}

test("reload restores exactly four server-projected markers, including fixed indeterminate red", async ({ page }) => {
  await installFakeRunner(page);
  const selected = golden.points.slice(0, 4).map((point, index) => ({ ...point,
    projected_px: index === 0 ? [640.2, 597.4] : point.projected_px,
    position_world_m: index === 0 ? [0.03, -0.31, 0.165] : point.position_world_m,
  }));
  const campaign = { ...baseCampaign, campaign_id: "campaign-four", manifest_id: "manifest-four",
    execution_mode: "SEQUENTIAL", status: "RUNNING", requested: 4,
    points: selected.map((point, index) => ({ point_id: point.id, display_id: point.display_id,
      status: index === 0 ? "INDETERMINATE" : "UNRUN", retry_eligible: false,
      attempts: [], artifact_ids: [], artifacts: [],
    })),
  };
  await page.route("**/expert-validation/campaigns", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify([campaign]),
  }));
  await page.route("**/expert-validation/campaigns/campaign-four", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify(campaign),
  }));
  await page.route("**/expert-validation/manifests/manifest-four", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify({
      manifest_id: "manifest-four", point_count: 4, stale: false,
      points: selected.map(point => ({ ...point, label: point.id, source: "anchor", stratum: "anchor" })),
      top_view: { ...golden, points: selected,
        geometry: { ...golden.geometry, candidate_bounds: [-0.045, 0.08, -0.34, -0.24] } },
    }),
  }));
  await page.goto("/expert-validation");
  await expect(page.locator("[data-point-id]")).toHaveCount(4);
  await expect(page.getByRole("button", { name: "P01 INDETERMINATE" }))
    .toHaveAttribute("transform", "translate(640.2 597.4)");
  await expect(page.getByRole("button", { name: "P01 INDETERMINATE" }))
    .toHaveAttribute("data-color", "red");
  await page.reload();
  await expect(page.locator("[data-point-id]")).toHaveCount(4);
  await expect(page.getByRole("button", { name: "P01 INDETERMINATE" }))
    .toHaveAttribute("transform", "translate(640.2 597.4)");
});

test("restores an adaptive campaign and retries a business-failed point", async ({ page }) => {
  const fake = await installFakeRunner(page);
  await page.goto("/expert-validation");

  await expect(page.getByLabel("P09 FAILED TARGET_TOLERANCE_EXCEEDED")).toBeVisible();
  await expect(page.getByLabel("Worker worker-1")).toBeVisible();
  await expect(page.getByLabel("Worker worker-2")).toBeVisible();
  await expect(page.getByText("W8 -> W6: WORKER_START_FAILED")).toBeVisible();
  await expect(page.getByText("Broker healthy")).toBeVisible();
  expect(fake.campaignGets).toBeGreaterThan(0);

  await page.getByRole("button", { name: "Acquire lease" }).click();
  await page.getByLabel("P09 FAILED TARGET_TOLERANCE_EXCEEDED").click();
  await page.getByLabel("Retry P09").check();
  await page.getByRole("button", { name: "Retry selected with FULL_RESTART" }).click();
  await page.getByLabel("Confirmation").fill("CONFIRM FULL_RESTART RETRIES");
  await page.getByRole("button", { name: "Confirm retry" }).click();

  expect(fake.lastRetryBody?.point_ids).toEqual(["sample_05_near_center"]);
  await expect(page.getByText("FULL_RESTART attempt 2: PASSED")).toBeVisible();
});

test("selected committed point loads inline RGB and opaque numeric evidence", async ({ page }) => {
  await installFakeRunner(page);
  const image = {
    artifact_id: "rgb-opaque", campaign_id: "campaign-adaptive", batch_id: "adaptive-first-pass",
    worker_id: "worker-2", worker_generation: 2, attempt_id: "attempt-a",
    role: "task-rgb-before", media_type: "image/png", size_bytes: 68, sha256: "a".repeat(64),
  };
  const numeric = { ...image, artifact_id: "numeric-opaque", role: "physical-evidence", media_type: "application/json" };
  await page.route("**/expert-validation/campaigns/campaign-adaptive", route => route.fulfill({
    contentType: "application/json", body: JSON.stringify({ ...terminalCampaign, points: [{
      ...terminalCampaign.points[0], artifact_ids: [image.artifact_id, numeric.artifact_id],
      artifacts: [image, numeric],
    }] }),
  }));
  await page.route("**/expert-validation/artifacts/rgb-opaque", route => route.fulfill({
    contentType: "image/png", body: Buffer.from(
      "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII=", "base64",
    ),
  }));
  await page.goto("/expert-validation");
  await page.getByLabel("P09 FAILED TARGET_TOLERANCE_EXCEEDED").click();
  const preview = page.getByAltText("task-rgb-before");
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBe(1);
  await expect(page.getByRole("link", { name: "Download physical-evidence" }))
    .toHaveAttribute("href", "/expert-validation/artifacts/numeric-opaque");
});
