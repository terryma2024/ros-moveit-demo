import { contractTest as test, expect } from "../fixtures/contract";
import { ExpertValidationPage } from "../pages/expert-validation-page";

test("C01 independent expert validation page", async ({ page, scriptedServer, consoleErrors }) => {
  const app = new ExpertValidationPage(page);
  await app.goto();
  await expect(app.pointCountInput()).toHaveValue("20");
  await expect(page.getByLabel("Catalog seed")).toHaveValue("20260911");
  await expect(page.getByRole("button", { name: "Generate points" })).toBeEnabled();
  const tasksResponse = await page.request.get("/tasks");
  expect(tasksResponse.status()).toBe(503);
  expect((await tasksResponse.json()).code).toBe("VALIDATION_TASKS_DISABLED");
  expect(scriptedServer.scenarioId).toBe("baseline-sequential-4");
  expect(consoleErrors).toEqual([]);
});
