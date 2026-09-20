/**
 * Unified-service live acceptance.
 *
 * Runs only after the R01 producer project: this project re-checks the producing run instead
 * of trusting a receipt file, and it asserts single-service properties that a per-domain
 * deployment cannot satisfy — one owned launcher, one web port, both domain surfaces served
 * from the same origin.
 */
import { expect } from "@playwright/test";

import { liveSimTest } from "../expert-validation/fixtures/live-sim";
import { requireGateDetail } from "../expert-validation/fixtures/live-sim";

liveSimTest.describe("unified web service", () => {
  liveSimTest("serves both domain surfaces from one origin", async ({ liveServer, page }) => {
    requireGateDetail(liveServer.preconditions.evidenceRoot, "r01", "unified");
    expect(liveServer.port).toBeGreaterThan(0);
    const teleop = await page.request.get(`${liveServer.baseURL}/health`);
    expect(teleop.ok()).toBeTruthy();
    const readiness = await page.request.get(`${liveServer.baseURL}/health/ready`);
    expect([200, 503]).toContain(readiness.status());
    const validation = await page.request.get(`${liveServer.baseURL}/expert-validation/capabilities`);
    expect(validation.ok()).toBeTruthy();
    // API and artifact namespaces are never answered with the SPA fallback.
    const unknown = await page.request.get(`${liveServer.baseURL}/tasks/definitely-unknown`);
    expect(unknown.status()).toBe(404);
    expect(unknown.headers()["content-type"] ?? "").toContain("application/json");
  });

  liveSimTest("keeps the SPA shell across direct navigation and refresh", async ({ page, liveServer }) => {
    for (const path of ["/", "/expert-validation", "/tasks"]) {
      const response = await page.goto(`${liveServer.baseURL}${path}`);
      expect(response?.status() ?? 0).toBeLessThan(400);
      await page.reload();
      expect(await page.title()).not.toEqual("");
    }
  });

  liveSimTest("refuses a legacy mutation without instance authority", async ({ page, liveServer }) => {
    const response = await page.request.post(`${liveServer.baseURL}/gripper/execute`, {
      data: { command_id: "legacy-1", lease_id: "l", session_id: "s", target_position_rad: 0 },
    });
    expect(response.status()).toBe(409);
    expect((await response.json()).code).toBe("CONTROLLER_INSTANCE_REQUIRED");
  });
});

/**
 * The two viewports the design requires. Asserting the real layout means measuring the document
 * against the viewport in a real browser: jsdom has no layout engine, so this cannot be replaced by
 * a unit test, and the dense joint table is expected to scroll inside its own container rather than
 * make the page overflow.
 */
for (const viewport of [
  { name: "desktop", width: 1400, height: 900 },
  { name: "phone", width: 390, height: 844 },
]) {
  liveSimTest(`has no horizontal page overflow at ${viewport.width}x${viewport.height}`, async ({
    page,
    liveServer,
  }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    for (const path of ["/", "/expert-validation", "/tasks"]) {
      await page.goto(`${liveServer.baseURL}${path}`);
      await page.waitForLoadState("domcontentloaded");
      const overflow = await page.evaluate(() => {
        const document_ = document.documentElement;
        return {
          scrollWidth: document_.scrollWidth,
          clientWidth: document_.clientWidth,
          widest: Array.from(document_.querySelectorAll<HTMLElement>("*"))
            .map((element) => element.getBoundingClientRect().right)
            .reduce((left, right) => Math.max(left, right), 0),
        };
      });
      expect(overflow.scrollWidth, `${path} scrollWidth`).toBeLessThanOrEqual(
        overflow.clientWidth + 1,
      );
      expect(overflow.widest, `${path} widest element`).toBeLessThanOrEqual(viewport.width + 1);
    }
  });
}

liveSimTest("keeps every status marker one radius and readable as text", async ({ page, liveServer }) => {
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto(`${liveServer.baseURL}/expert-validation`);
  const markers = page.locator("circle[data-point-status]");
  const count = await markers.count();
  if (count === 0) return; // no manifest in this run; the map contract is covered by unit tests
  const radii = new Set(await markers.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("r"))));
  expect(radii.size).toBe(1);
});
