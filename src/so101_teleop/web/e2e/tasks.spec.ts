import { expect, test } from "@playwright/test";

const artifacts = [
  { artifact_id: "a".repeat(24), name: "rgb.png", media_type: "image/png", byte_size: 8, sha256: "1".repeat(64) },
  { artifact_id: "b".repeat(24), name: "full-cloud.ply", media_type: "application/octet-stream", byte_size: 16, sha256: "2".repeat(64) },
];
const run = {
  run_id: "run-e2e",
  status: "FAILED",
  simulation_session_id: "e2e-session",
  first_shared_failure: null,
  points: [
    { id: "failed-first", status: "FAILED", failure_code: "PERCEPTION_TIMEOUT", reachability_status: "REACHABLE", reset_epoch: 11, artifact_ids: artifacts.map((item) => item.artifact_id), artifacts },
    { id: "unreachable", status: "SKIPPED_UNREACHABLE", failure_code: "UNREACHABLE", reachability_status: "UNREACHABLE", reset_epoch: null, artifact_ids: [], artifacts: [] },
    { id: "success-after", status: "SUCCEEDED", failure_code: null, reachability_status: "REACHABLE", reset_epoch: 12, artifact_ids: [], artifacts: [] },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/snapshot", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ simulation_session_id: "e2e-session" }),
  }));
  await page.route("**/tasks/presets", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ schema_version: 1, points: [] }),
  }));
  await page.route("**/tasks/runs", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify([run]) }));
  await page.route("**/tasks/runs/run-e2e", (route) => route.fulfill({ contentType: "application/json", body: JSON.stringify(run) }));
});

test("task page remains isolated and restores progress and registered evidence after refresh", async ({ page }) => {
  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "Perception Pick & Place Tasks" })).toBeVisible();
  await expect(page.getByLabel("Task point builder")).toBeVisible();
  await expect(page.getByText("Live RGB-D evidence")).toBeVisible();
  await expect(page.getByText("Runs & Evidence")).toBeVisible();
  await expect(page.getByText("failed-first — FAILED")).toBeVisible();
  await expect(page.getByText("unreachable — SKIPPED_UNREACHABLE")).toBeVisible();
  await expect(page.getByText("success-after — SUCCEEDED")).toBeVisible();
  await expect(page.getByRole("link", { name: "RGB PNG" })).toHaveAttribute("href", `/tasks/artifacts/${"a".repeat(24)}`);
  await expect(page.getByRole("link", { name: "Open Teleop" })).toHaveAttribute("href", "/");

  await page.reload();
  await expect(page.getByText("success-after — SUCCEEDED")).toBeVisible();
  await expect(page.getByText("Runs & Evidence")).toBeVisible();
});
