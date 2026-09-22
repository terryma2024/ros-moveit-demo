import { test, expect } from "@playwright/test";

import { ExpertValidationPage } from "../pages/expert-validation-page";

/**
 * The worker-count control has to be addressed deterministically.
 *
 * The macOS console renders the `Worker count` select *and* an `Unavailable worker counts` list, so
 * `getByLabel("Worker count")` resolves to two elements and Playwright's strict mode refuses the
 * call - which is exactly how the fixed-n sweep failed at `configureParallel(2)`, before it ever
 * reached a campaign.  The page object addresses the select by its exact label; this test renders
 * the console's own two controls and exercises the real accessor, so the ambiguity cannot come back
 * unnoticed.  Nothing about what the specs assert changes.
 */

/** The campaign-setup markup the console renders on a platform-bound host. */
const CAMPAIGN_SETUP = `
  <div aria-label="Campaign setup">
    <label>Execution mode
      <select aria-label="Execution mode">
        <option value="SEQUENTIAL">SEQUENTIAL</option>
        <option value="PARALLEL">PARALLEL</option>
      </select>
    </label>
    <label>Worker count
      <select aria-label="Worker count">
        <option value="1">1</option>
        <option value="2">2</option>
      </select>
    </label>
    <ul aria-label="Unavailable worker counts">
      <li>N4 unavailable · UNSUPPORTED_ON_MACOS</li>
    </ul>
  </div>
`;

test("configureParallel addresses the worker-count select deterministically", async ({ page }) => {
  await page.setContent(CAMPAIGN_SETUP);
  const app = new ExpertValidationPage(page);

  // The defect this pins: a non-exact label query matches the select *and* the unavailable list.
  await expect(page.getByLabel("Worker count")).toHaveCount(2);

  // configureParallel has to address one control; before the fix this is a strict-mode violation.
  await app.configureParallel(2);

  // The accessor the page object uses resolves that one control and selected from it.
  await expect(app.workerCountSelect()).toHaveCount(1);
  expect(await app.workerCountSelect().inputValue()).toBe("2");
  expect(await page.getByLabel("Execution mode").inputValue()).toBe("PARALLEL");
});
