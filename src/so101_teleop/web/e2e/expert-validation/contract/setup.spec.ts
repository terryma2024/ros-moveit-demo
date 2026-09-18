import { contractTest as test, expect } from "../fixtures/contract";
import { ExpertValidationPage } from "../pages/expert-validation-page";

test("C02 four-point manifest matches the server response", async ({ page, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  const responsePromise = page.waitForResponse(
    (response) =>
      response.url().includes("/expert-validation/manifests")
      && response.request().method() === "POST",
  );
  await app.generateManifest(4);
  const manifest = await (await responsePromise).json();
  expect(manifest.point_count).toBe(4);
  expect(manifest.catalog_seed).toBe(20260911);
  const ids = manifest.points.map((point: { id: string }) => point.id);
  expect(ids).toEqual([
    "task_start",
    "cup_test_forward_5cm",
    "cup_test_left_5cm",
    "cup_test_right_5cm",
  ]);
  await expect(page.locator("[data-point-id]")).toHaveCount(4);
  for (const point of manifest.top_view.points) {
    await expect(app.mapPointById(point.id)).toHaveAttribute(
      "transform",
      `translate(${point.projected_px[0]} ${point.projected_px[1]})`,
    );
  }
  await app.expectEqualPointRadius(ids);
  expect(consoleErrors).toEqual([]);
});

test("C03 point counts 5 10 20 and out-of-range rejection", async ({ page, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  for (const count of [5, 10, 20]) {
    await app.generateManifest(count);
    await expect(page.locator("[data-point-id]")).toHaveCount(count);
    for (const anchor of [
      "task_start",
      "cup_test_forward_5cm",
      "cup_test_left_5cm",
      "cup_test_right_5cm",
    ]) {
      await expect(app.mapPointById(anchor)).toBeVisible();
    }
  }
  await app.setPointCount(3);
  await expect(page.getByRole("button", { name: "Generate points" })).toBeDisabled();
  await app.setPointCount(21);
  await expect(page.getByRole("button", { name: "Generate points" })).toBeDisabled();
  const rejected = await page.request.post("/expert-validation/manifests", {
    data: { total_points: 3 },
  });
  expect(rejected.status()).toBe(422);
  expect(consoleErrors).toEqual([]);
});

test("C04 config changes invalidate credentials precisely", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();

  const firstManifest = page.waitForResponse(
    (response) =>
      response.url().includes("/expert-validation/manifests")
      && response.request().method() === "POST",
  );
  await app.generateManifest(4);
  const manifestA = await (await firstManifest).json();

  await app.setPointCount(5);
  await expect(page.locator("[data-point-id]")).toHaveCount(0);

  const secondManifest = page.waitForResponse(
    (response) =>
      response.url().includes("/expert-validation/manifests")
      && response.request().method() === "POST",
  );
  await app.generateManifest();
  const manifestB = await (await secondManifest).json();
  expect(manifestB.manifest_id).not.toBe(manifestA.manifest_id);
  await expect(page.locator("[data-point-id]")).toHaveCount(5);

  await app.configureParallel(2);
  await expect(page.locator("[data-point-id]")).toHaveCount(5);

  await app.runPreflight();
  await expect(app.notice("Parallel admission passed")).toBeVisible();

  await page.getByLabel("Worker count").selectOption("3");
  await app.startValidation();

  const commands = await scriptedServer.control.commands();
  const preflights = commands.filter((command) => command.operation === "preflight");
  const starts = commands.filter((command) => command.operation === "start_campaign");
  expect(preflights.length).toBe(2);
  expect(starts.length).toBe(1);
  expect(preflights[0].body.worker_count).toBe(2);
  expect(preflights[1].body.worker_count).toBe(3);
});

test("C05 sequential request shape", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(4);
  await app.configureSequential();
  await expect(page.getByLabel("Worker count")).toBeDisabled();
  await expect(page.getByText(/W8 ->/)).toHaveCount(0);
  await app.runPreflight();
  await app.startValidation();
  const commands = await scriptedServer.control.commands();
  const preflight = commands.find((command) => command.operation === "preflight");
  expect(preflight.body.execution_mode).toBe("SEQUENTIAL");
  expect(preflight.body.worker_count).toBe(1);
  expect(preflight.body).not.toHaveProperty("preferred_worker_count");
  expect(preflight.body).not.toHaveProperty("fallback_worker_counts");
});

test("C06 fixed parallel admission is explicit scenario:parallel-unavailable", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(20);

  await app.configureParallel(2);
  await expect(page.getByText("共享队列 · 每 worker 一次一任务")).toBeVisible();
  await expect(page.getByText(/NOT_MEASURED · BUDGET_PROFILE_UNAVAILABLE/)).toBeVisible();
  await expect(app.startButton()).toBeDisabled();
  await expect(page.getByLabel("Max points per worker")).toHaveCount(0);
  await expect(page.getByText(/^Capacity/)).toHaveCount(0);

  await app.runPreflight();
  await expect(app.notice("PARALLEL_NOT_QUALIFIED")).toBeVisible();
  const commands = await scriptedServer.control.commands();
  expect(commands.filter((command) => command.operation === "start_campaign")).toEqual([]);
});

test("C07 adaptive request shape and defaults", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(20);
  await app.configureAdaptive();
  await expect(page.getByText("W8 -> W6 -> W4 -> W2 -> W1")).toBeVisible();
  await expect(page.getByText("Resource observations only")).toBeVisible();
  await expect(page.getByLabel("Max points per worker")).toHaveCount(0);
  await expect(page.getByText(/Capacity \d+ \//)).toHaveCount(0);
  await app.runPreflight();
  await app.startValidation();
  const commands = await scriptedServer.control.commands();
  const preflight = commands.find((command) => command.operation === "preflight");
  expect(preflight.body.contract_version).toBe(2);
  expect(preflight.body.execution_mode).toBe("ADAPTIVE");
  expect(preflight.body.preferred_worker_count).toBe(8);
  expect(preflight.body.fallback_worker_counts).toEqual([6, 4, 2, 1]);
  expect(preflight.body.initial_points_per_worker).toBe(3);
  expect(preflight.body.worker_start_timeout_s).toBe(120);
  expect(preflight.body.max_infra_attempts_per_point).toBe(5);
  expect(preflight.body.yolo_executor_count).toBe(2);
  expect(preflight.body).not.toHaveProperty("max_points_per_worker");
  expect(preflight.body).not.toHaveProperty("worker_count");
});

test("C08 lease and preflight gates block start scenario:preflight-rejected", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await expect(app.startButton()).toBeDisabled();
  await expect(page.getByRole("button", { name: "Check resources" })).toBeDisabled();

  const unauthenticated = await page.request.post("/expert-validation/campaigns/preflight", {
    data: {
      service_session_id: "forged",
      contract_version: 2,
      lease_id: "lease-forged",
      lease_generation: 1,
      manifest_id: "manifest-none",
      execution_mode: "SEQUENTIAL",
      worker_count: 1,
    },
  });
  expect(unauthenticated.status()).toBe(409);
  expect((await unauthenticated.json()).code).toBe("LEASE_NOT_ACTIVE");

  await app.acquireLease();
  await app.generateManifest(4);
  await app.runPreflight();
  await expect(app.notice("Preflight rejected: GPU_HEADROOM")).toBeVisible();

  await app.startButton().click();
  const forgedStart = await page.request.post("/expert-validation/campaigns", {
    data: {
      service_session_id: "forged",
      contract_version: 2,
      lease_id: "lease-forged",
      lease_generation: 1,
      command_id: "forged-start",
      manifest_id: "manifest-none",
      contract_version: 2,
      execution_mode: "SEQUENTIAL",
      worker_count: 1,
      preflight_receipt_id: "receipt-forged",
    },
  });
  expect(forgedStart.status()).toBe(409);
  expect((await forgedStart.json()).code).toBe("PREFLIGHT_RECEIPT_MISMATCH");

  const commands = await scriptedServer.control.commands();
  expect(commands.filter((command) => command.operation === "start_campaign")).toEqual([]);
});

test("C22 renewed lease invalidates the preflight receipt scenario:short-lease", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();

  const manifestResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/expert-validation/manifests")
      && response.request().method() === "POST",
  );
  await app.generateManifest(4);
  const manifest = await (await manifestResponse).json();

  const preflightResponse = page.waitForResponse(
    (response) => response.url().includes("/expert-validation/campaigns/preflight"),
  );
  await app.runPreflight();
  const receipt = await (await preflightResponse).json();
  expect(receipt.admitted).toBe(true);

  await expect(app.notice("Lease renewed; check resources again")).toBeVisible({ timeout: 10_000 });

  const stale = await page.request.post("/expert-validation/campaigns", {
    data: {
      service_session_id: "stale-session",
      contract_version: 2,
      lease_id: "lease-stale",
      lease_generation: 1,
      command_id: "stale-start",
      manifest_id: manifest.manifest_id,
      execution_mode: "SEQUENTIAL",
      worker_count: 1,
      preflight_receipt_id: receipt.receipt_id,
    },
  });
  expect(stale.status()).toBe(409);

  const commandsBefore = await scriptedServer.control.commands();
  expect(commandsBefore.filter((command) => command.operation === "start_campaign")).toEqual([]);

  await app.startValidation();
  const commands = await scriptedServer.control.commands();
  expect(commands.filter((command) => command.operation === "preflight").length).toBe(2);
  expect(commands.filter((command) => command.operation === "start_campaign").length).toBe(1);

  const reread = await page.request.get(`/expert-validation/manifests/${manifest.manifest_id}`);
  expect((await reread.json()).manifest_sha256).toBe(manifest.manifest_sha256);
});

test("N8 exact twenty-point fixed preview and rejected admission scenario:parallel-unavailable", async ({ page, scriptedServer, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(20);
  await page.getByLabel("Execution mode").selectOption("PARALLEL");
  const options = page.getByLabel("Worker count").locator("option");
  await expect(options).toHaveCount(8);
  expect(await options.evaluateAll(nodes => nodes.map(node => (node as HTMLOptionElement).value)))
    .toEqual(["1", "2", "3", "4", "5", "6", "7", "8"]);
  await expect(options.first()).toHaveJSProperty("disabled", true);
  await expect(options.first()).toHaveText("1 (SEQUENTIAL only)");
  await expect(page.getByText("共享队列 · 每 worker 一次一任务")).toBeVisible();
  await page.getByLabel("Worker count").selectOption("8");
  await expect(page.getByText(/NOT_MEASURED · BUDGET_PROFILE_UNAVAILABLE/)).toBeVisible();
  await expect(page.getByLabel("Max points per worker")).toHaveCount(0);
  const responsePromise = page.waitForResponse(response =>
    response.url().endsWith("/expert-validation/campaigns/preflight")
      && response.request().method() === "POST");
  await app.runPreflight();
  const response = await responsePromise;
  await expect(app.notice("PARALLEL_NOT_QUALIFIED")).toBeVisible();
  expect(response.status()).toBe(409);
  expect(await response.json()).toEqual({ code: "PARALLEL_NOT_QUALIFIED" });
  const request = response.request().postDataJSON();
  expect(request).toMatchObject({ contract_version: 2, execution_mode: "PARALLEL", worker_count: 8 });
  expect(request).not.toHaveProperty("max_points_per_worker");
  expect(request).not.toHaveProperty("preferred_worker_count");
  const commands = await scriptedServer.control.commands();
  expect(commands.filter(command => command.operation === "start_campaign")).toEqual([]);
  const expectedRejection = `Failed to load resource: the server responded with a status of 409 (Conflict) (${response.url()})`;
  expect(consoleErrors.filter(error => error !== expectedRejection)).toEqual([]);
});
