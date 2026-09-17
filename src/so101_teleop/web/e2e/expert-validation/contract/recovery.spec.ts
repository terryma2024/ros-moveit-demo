import { contractTest as test, expect } from "../fixtures/contract";
import { ExpertValidationPage } from "../pages/expert-validation-page";

test("C13 websocket sequence consistency under duplicate, late and gap faults scenario:ws-gap", async ({ page, scriptedServer, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  const progress = page.getByRole("region", { name: "Campaign progress" });
  await expect(progress.getByText(/sequence 1$/)).toBeVisible();

  await scriptedServer.control.emit();
  await expect(progress.getByText(/sequence 2$/)).toBeVisible();
  await app.expectPointColor("task_start", "blue");
  await app.expectPointLabel("task_start", "P01 EXECUTING Worker worker-01 EXECUTING");

  await scriptedServer.control.emit();
  await expect(progress.getByText(/sequence 3$/)).toBeVisible();
  await app.expectPointLabel("task_start", "P01 PASSED");

  await scriptedServer.control.emit();
  await scriptedServer.control.emit();
  await expect(progress.getByText(/sequence 5$/)).toBeVisible();
  await app.expectPointLabel("cup_test_forward_5cm", "P02 PASSED");
  await app.expectPointLabel("cup_test_left_5cm", "P03 PASSED");
  await expect(page.getByText("First pass 3 / 3 valid")).toBeVisible();

  await scriptedServer.control.emit();
  await expect(progress.getByText(/COMPLETED · sequence 6/)).toBeVisible();
  await expect(page.getByText("First pass 4 / 4 valid")).toBeVisible();

  const commands = await scriptedServer.control.commands();
  const gets = commands.filter((command) => command.operation === "get_campaign");
  expect(gets.length).toBeGreaterThan(0);
  expect(consoleErrors).toEqual([]);
});

test("C14 page reload restores the running campaign without a duplicate start", async ({ page, scriptedServer, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await app.acquireLease();
  await app.generateManifest(4);
  await app.runPreflight();
  await app.startValidation();
  const progress = page.getByRole("region", { name: "Campaign progress" });
  await expect(progress.getByText(/RUNNING · sequence 1/)).toBeVisible();

  await scriptedServer.control.emit();
  await expect(app.workerCard("worker-01")).toContainText("EXECUTING · task_start", { timeout: 10_000 });

  await page.reload();
  await expect(progress.getByText(/RUNNING/)).toBeVisible();
  await expect(app.workerCard("worker-01")).toContainText("EXECUTING · task_start", { timeout: 10_000 });
  await app.expectPointColor("task_start", "blue");

  const commands = await scriptedServer.control.commands();
  const starts = commands.filter((command) => command.operation === "start_campaign");
  expect(starts.length).toBe(1);
  const firstStartIndex = commands.findIndex((command) => command.operation === "start_campaign");
  const reloadLists = commands
    .map((command, index) => ({ command, index }))
    .filter((entry) => entry.command.operation === "list_campaigns" && entry.index > firstStartIndex);
  expect(reloadLists.length).toBeGreaterThan(0);
  const reloadSubscribe = commands
    .map((command, index) => ({ command, index }))
    .filter((entry) => entry.command.operation === "subscribe_events" && entry.index > reloadLists[0].index);
  expect(reloadSubscribe.length).toBeGreaterThan(0);
  expect(consoleErrors).toEqual([]);
});
