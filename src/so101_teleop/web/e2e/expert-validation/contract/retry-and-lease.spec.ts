import { contractTest as test, expect } from "../fixtures/contract";
import { ExpertValidationPage } from "../pages/expert-validation-page";

test("C17 legitimate FULL_RESTART retry of an eligible failed point scenario:terminal-4-with-failure", async ({ page, scriptedServer, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.selectPoint("P03");

  await expect(app.retryCheckbox("P03")).toBeEnabled();
  await app.retryFailedPoints(["P03"]);

  const evidence = app.evidenceSection("P03");
  await expect(evidence.getByText("FULL_RESTART attempt 2: PASSED")).toBeVisible();
  await expect(evidence.getByText("First-pass attempt 1: FAILED")).toBeVisible();

  const commands = await scriptedServer.control.commands();
  const retry = commands.find((command) => command.operation === "retry_campaign");
  expect(retry.point_ids).toEqual(["cup_test_left_5cm"]);
  expect(consoleErrors).toEqual([]);
});

test("C18 illegal retries stay unselectable scenario:terminal-4-with-failure", async ({ page }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await expect(app.retryCheckbox("P01")).toBeDisabled();
  await expect(app.retryCheckbox("P03")).toBeEnabled();
  await expect(app.retryCheckbox("P04")).toBeDisabled();

  await app.retryCheckbox("P03").check();
  await page.getByRole("button", { name: "Retry selected with FULL_RESTART" }).click();
  await app.page.getByLabel("Confirmation").fill("CONFIRM FULL_RESTART RETRY");
  await expect(page.getByRole("button", { name: "Confirm retry" })).toBeDisabled();
  await app.page.getByLabel("Confirmation").fill("CONFIRM FULL_RESTART RETRIES");
  await expect(page.getByRole("button", { name: "Confirm retry" })).toBeEnabled();
});

test("C18 illegal retries stay unselectable while recovery is pending scenario:recovery-blocked", async ({ page }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await expect(page.getByText(/NEEDS_OPERATOR_RECOVERY/)).toBeVisible();
  for (const displayId of ["P01", "P02", "P03", "P04"]) {
    await expect(app.retryCheckbox(displayId)).toBeDisabled();
  }
  await app.expectPointColor("cup_test_left_5cm", "red");
  await expect(page.getByText("Failed 0")).toBeVisible();
});

test("C19 retry results stay isolated from first-pass statistics scenario:terminal-4-with-failure", async ({ page }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await expect(page.getByText("First pass 2 / 4 valid")).toBeVisible();
  await expect(page.getByText("Failed 1")).toBeVisible();

  await app.selectPoint("P03");
  await app.retryFailedPoints(["P03"]);

  await expect(page.getByText("First pass 2 / 4 valid")).toBeVisible();
  await expect(page.getByText("Failed 1")).toBeVisible();
  await expect(page.getByText("Requested 4")).toBeVisible();
  const evidence = app.evidenceSection("P03");
  await expect(evidence.getByText("First-pass attempt 1: FAILED")).toBeVisible();
  await expect(evidence.getByText("FULL_RESTART attempt 2: PASSED")).toBeVisible();
  await expect(app.retryCheckbox("P03")).toBeDisabled();
});

test("C20 dual Chrome contexts contend for one lease", async ({ page, browser, scriptedServer, consoleErrors }) => {
  const appA = new ExpertValidationPage(page);
  await appA.goto();
  await appA.acquireLease();

  const contextB = await browser.newContext();
  const pageB = await contextB.newPage();
  const appB = new ExpertValidationPage(pageB);
  try {
    await appB.goto();
    await pageB.getByRole("button", { name: "Acquire lease" }).click();
    await expect(pageB.getByText("LEASE_HELD")).toBeVisible();
    await expect(appB.startButton()).toBeDisabled();
    await expect(appB.pointCountInput()).toBeVisible();

    await page.reload();
    await expect(appA.page.getByRole("heading", { name: "SO-101 Expert Validation" })).toBeVisible();

    const state = await scriptedServer.control.state();
    const lease = state.lease as { state: string } | undefined;
    expect(lease?.state).toBe("ACTIVE");

    await pageB.getByRole("button", { name: "Acquire lease" }).click();
    await expect(pageB.getByText("LEASE_HELD")).toBeVisible();

    const forgedCancel = await pageB.request.post("/expert-validation/campaigns/campaign-none/cancel", {
      data: {
        service_session_id: "session-b",
        lease_id: "lease-b",
        lease_generation: 1,
        command_id: "cancel-b",
      },
    });
    expect(forgedCancel.status()).toBe(409);
  } finally {
    await contextB.close();
  }
  expect(consoleErrors).toEqual([]);
});

test("C21 lease lifecycle projection scenario:short-lease", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await expect(app.notice("Lease renewed; check resources again")).toBeVisible({ timeout: 15_000 });

  const state = await scriptedServer.control.state();
  const lease = state.lease as {
    lease_id: string;
    service_session_id: string;
    generation: number;
  };
  expect(lease.generation).toBeGreaterThan(1);

  const staleRenew = await page.request.put(
    `/expert-validation/lease/${lease.lease_id}`,
    {
      data: {
        service_session_id: lease.service_session_id,
        generation: 1,
      },
    },
  );
  expect(staleRenew.status()).toBe(409);
  expect((await staleRenew.json()).code).toBe("STALE_LEASE_GENERATION");
});

test("C21 failed renewal drops page authority scenario:renew-fails", async ({ page, scriptedServer }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await expect(app.notice("LEASE_EXPIRED")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Acquire lease" })).toBeEnabled();
  await expect(app.startButton()).toBeDisabled();

  await expect
    .poll(async () => {
      const state = await scriptedServer.control.state();
      return (state.lease as { state: string } | undefined)?.state;
    }, { timeout: 15_000 })
    .toBe("EXPIRED");
});
