import { createHash } from "node:crypto";

import { contractTest as test, expect } from "../fixtures/contract";
import { ExpertValidationPage } from "../pages/expert-validation-page";

test("C09 top-view status colours, selection and evidence linkage scenario:terminal-4-with-failure", async ({ page, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await expect(page.locator("[data-point-id]")).toHaveCount(4);

  await app.expectPointColor("task_start", "green");
  await app.expectPointColor("cup_test_forward_5cm", "green");
  await app.expectPointColor("cup_test_left_5cm", "red");
  await app.expectPointColor("cup_test_right_5cm", "red");
  await app.expectPointLabel("cup_test_left_5cm", "P03 FAILED TARGET_TOLERANCE_EXCEEDED");
  await app.expectEqualPointRadius([
    "task_start",
    "cup_test_forward_5cm",
    "cup_test_left_5cm",
    "cup_test_right_5cm",
  ]);

  await app.mapPointById("cup_test_forward_5cm").focus();
  await page.keyboard.press("Enter");
  await expect(app.evidenceSection("P02")).toBeVisible();

  await app.selectPoint("P03");
  await expect(app.evidenceSection("P03")).toBeVisible();
  await expect(app.evidenceSection("P03").getByText("FAILED · TARGET_TOLERANCE_EXCEEDED")).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("C10 concurrent worker progress keeps generation and point states scenario:running-two-workers", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await expect(page.locator("[data-point-id]")).toHaveCount(4);
  await expect(app.workerCard("worker-01")).toContainText("READY");
  await expect(app.workerCard("worker-02")).toContainText("READY");

  await scriptedServer.control.emit();
  await expect(app.workerCard("worker-01")).toContainText("EXECUTING · task_start", { timeout: 10_000 });
  await expect(app.workerCard("worker-02")).toContainText("EXECUTING · cup_test_forward_5cm");
  await app.expectPointColor("task_start", "blue");
  await app.expectPointColor("cup_test_forward_5cm", "blue");
  const activeMarker = page.locator("[data-point-id='task_start'] > circle[r='10']");
  await expect(activeMarker).toHaveAttribute("stroke-width", "5");
  await app.expectEqualPointRadius([
    "task_start",
    "cup_test_forward_5cm",
    "cup_test_left_5cm",
    "cup_test_right_5cm",
  ]);

  await scriptedServer.control.emitAll();
  await expect(app.workerCard("worker-01")).toContainText("STOPPED", { timeout: 10_000 });
  const progress = page.getByRole("region", { name: "Campaign progress" });
  await expect(progress.getByText(/PARALLEL · COMPLETED/)).toBeVisible();
  await app.expectPointColor("task_start", "green");
  await app.expectPointColor("cup_test_right_5cm", "green");
  await expect(page.getByText("First pass 4 / 4 valid")).toBeVisible();
});

test("C11 broker pause and recovery stay infrastructure scenario:running-two-workers", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await scriptedServer.control.emit();

  await scriptedServer.control.emit();
  await expect(page.getByText("Broker degraded: BROKER_PAUSED"),).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("First pass 0 / 0 valid")).toBeVisible();
  await expect(page.getByText("Failed 0")).toBeVisible();
  await app.expectPointColor("cup_test_left_5cm", "blue");

  await scriptedServer.control.emit();
  await scriptedServer.control.emit();
  await expect(page.getByText("Broker healthy")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("region", { name: "Campaign progress" }).locator("header").getByText(/RUNNING/)).toBeVisible();

  await scriptedServer.control.emitAll();
  await expect(page.getByText("First pass 4 / 4 valid")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Failed 0")).toBeVisible();
});

test("C12 adaptive fallback and stale generation projection scenario:adaptive-fallback", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await expect(page.locator("[data-point-id]")).toHaveCount(20);
  await expect(page.getByText("Levels used W8")).toBeVisible();

  await scriptedServer.control.emit();
  await expect(page.getByText("Broker degraded: RECOVERING")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Infra attempts 1")).toBeVisible();

  await scriptedServer.control.emit();
  await expect(page.getByText("W8 -> W6: WORKER_START_FAILED")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Levels used W8 -> W6")).toBeVisible();
  await expect(app.workerCard("worker-06-01")).toContainText("generation 2");
  await expect(page.getByText("Broker healthy")).toBeVisible();
  await expect(page.getByText(/memory_pressure=HIGH/)).toBeVisible();

  await scriptedServer.control.emit();
  await expect(app.workerCard("worker-06-01")).toContainText("EXECUTING · task_start", { timeout: 10_000 });
  await app.expectPointColor("task_start", "blue");
  await expect(page.getByText("Levels used W8 -> W6")).toBeVisible();
});

test("C15 terminal statistics stay separated scenario:terminal-4-with-failure", async ({ page }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await expect(page.getByText("Requested 4")).toBeVisible();
  await expect(page.getByText("Evaluated 4")).toBeVisible();
  await expect(page.getByText("Execution started 4")).toBeVisible();
  await expect(page.getByText("First pass 2 / 4 valid")).toBeVisible();
  await expect(page.getByText("Failed 1")).toBeVisible();
  await expect(page.getByText("Indeterminate 1")).toBeVisible();
  await expect(page.getByText("Unrun 0")).toBeVisible();
  await app.expectPointColor("cup_test_left_5cm", "red");
  await app.expectPointColor("cup_test_right_5cm", "red");
});

test("C16 evidence panel previews and downloads registered artifacts scenario:terminal-4-with-failure", async ({ page }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.selectPoint("P03");
  const evidence = app.evidenceSection("P03");
  await expect(evidence).toBeVisible();
  await expect(evidence.getByText("First-pass attempt 1: FAILED")).toBeVisible();

  const preview = evidence.getByAltText("task-rgb-before");
  await expect(preview).toBeVisible();
  await expect.poll(() => preview.evaluate((element: HTMLImageElement) => element.naturalWidth)).toBe(1);

  const download = evidence.getByRole("link", { name: "Download physical-evidence" });
  await expect(download).toHaveAttribute(
    "href",
    "/expert-validation/artifacts/numeric-opaque-p03",
  );
  const response = await page.request.get("/expert-validation/artifacts/numeric-opaque-p03");
  expect(response.status()).toBe(200);
  const body = await response.body();
  expect(createHash("sha256").update(body).digest("hex")).toBe(
    "f76459e7a85fe6fc9c7b04dc7b53297e6b0298f7fb1ccc08cce2448289c87a01",
  );

  const unknown = await page.request.get("/expert-validation/artifacts/not-registered");
  expect(unknown.status()).toBe(404);
});
