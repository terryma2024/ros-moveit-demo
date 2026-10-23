import { expect, test } from "@playwright/test";

import { ExpertValidationPage } from "../pages/expert-validation-page";

/**
 * A native campaign is one worker, so the console has neither an `Execution mode` selector nor a
 * `Worker count` control nor an `Unavailable worker counts` list. The page object keeps
 * `configureSequential()` for existing call sites, and it must assert that absence rather than
 * try to select anything.
 *
 * The page below is the console's own markup for the setup section; no server is needed to prove
 * what the page object does with it.
 */
const SINGLE_WORKER_SETUP = `
  <section aria-label="Campaign setup">
    <label>Final point count <input aria-label="Final point count" type="number" value="4"></label>
    <p aria-label="Execution">One worker, one point at a time (SEQUENTIAL)</p>
  </section>`;

test("configureSequential asserts the single-worker statement and selects nothing", async ({ page }) => {
  await page.setContent(SINGLE_WORKER_SETUP);
  const app = new ExpertValidationPage(page);

  await app.configureSequential();

  await expect(page.getByLabel("Execution mode")).toHaveCount(0);
  await expect(page.getByLabel("Worker count")).toHaveCount(0);
  await expect(page.getByLabel("Unavailable worker counts")).toHaveCount(0);
});

test("configureSequential fails when a mode selector comes back", async ({ page }) => {
  await page.setContent(`${SINGLE_WORKER_SETUP}
    <label>Execution mode <select aria-label="Execution mode"><option>SEQUENTIAL</option></select></label>`);
  const app = new ExpertValidationPage(page);

  await expect(app.configureSequential()).rejects.toThrow();
});
