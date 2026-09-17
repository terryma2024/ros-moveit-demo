import { existsSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { contractTest as test, expect } from "../fixtures/contract";

test("responsive map and point results keep projection and evidence selection scenario:terminal-20-layout", async ({ page, scriptedServer, consoleErrors }, testInfo) => {
  test.setTimeout(300_000);
  await page.goto("/expert-validation");
  const map = page.getByRole("img", { name: "Expert validation top view" });
  await expect(map.locator("[data-point-id]")).toHaveCount(20);
  const progress = page.getByRole("region", { name: "Campaign progress" });
  const geometry = () => map.evaluate(svg => Array.from(svg.querySelectorAll("[data-geometry], [data-point-id]"))
    .map(node => Array.from(node.attributes).filter(attribute => attribute.name !== "data-selected")
      .map(attribute => [attribute.name, attribute.value])));
  const originalGeometry = await geometry();
  const metrics = [];
  for (const width of [1920, 1280, 390]) {
    await page.setViewportSize({ width, height: 1080 });
    await expect(map).toBeVisible();
    await expect.poll(async () => page.evaluate(() => window.innerWidth)).toBe(width);
    const measured = await page.evaluate(() => {
      const bounds = (selector: string) => {
        const node = document.querySelector(selector);
        if (!node) return null;
        const { x, y, width, height } = node.getBoundingClientRect();
        return { x, y, width, height };
      };
      const grid = document.querySelector('[aria-label="Point execution results"]');
      return {
        viewport: window.innerWidth, main: bounds("main"),
        map: bounds('[aria-label="Expert validation top view"]'),
        progress: bounds('[aria-label="Campaign progress"]'),
        grid: bounds('[aria-label="Point execution results"]'),
        columns: grid ? getComputedStyle(grid).gridTemplateColumns.split(" ").length : 0,
        overflow: document.documentElement.scrollWidth > window.innerWidth,
      };
    });
    metrics.push(measured);
    await testInfo.attach(`layout-${width}`, { body: JSON.stringify(measured), contentType: "application/json" });
    await page.screenshot({ path: join(scriptedServer.evidenceDir, `layout-${width}.png`), fullPage: true });
    const phase = process.env.SO101_LAYOUT_NATIVE_CAPTURE;
    if (phase) {
      const root = process.env.SO101_E2E_EVIDENCE_ROOT!;
      await page.evaluate(title => { document.title = title; }, `SO-101 Layout ${phase} ${width}`);
      writeFileSync(join(root, `native-ready-${width}.json`), JSON.stringify({ width, title: await page.title(), url: page.url() }));
      const receipt = join(root, `native-captured-${width}.receipt`);
      const deadline = Date.now() + 120_000;
      while (!existsSync(receipt)) {
        if (Date.now() > deadline) throw new Error(`NATIVE_CAPTURE_TIMEOUT_${width}`);
        await new Promise(resolve => setTimeout(resolve, 200));
      }
    }
    expect(await geometry()).toEqual(originalGeometry);
    // Collect every viewport's baseline before asserting the approved change.
    if (width === 390) writeFileSync(join(scriptedServer.evidenceDir, "layout-metrics.json"), JSON.stringify(metrics, null, 2));
  }
  for (const measured of metrics) {
    expect(measured.overflow).toBe(false);
    expect(measured.columns).toBe(measured.viewport === 1920 ? 3 : measured.viewport === 1280 ? 2 : 1);
    if (measured.viewport >= 1024) {
      expect(measured.main!.width).toBeGreaterThan(measured.viewport * 0.92);
      expect(measured.map!.width / (measured.map!.width + measured.progress!.width)).toBeCloseTo(0.6, 1);
      expect(measured.map!.y).toBeCloseTo(measured.progress!.y, 0);
    } else expect(measured.progress!.y).toBeGreaterThanOrEqual(measured.map!.y + measured.map!.height);
  }
  // Keep the viewport wide while varying only the sidebar's available width.
  await page.setViewportSize({ width: 1920, height: 1080 });
  const columnsInContainer = () => page.getByRole("group", { name: "Point execution results" })
    .evaluate(grid => getComputedStyle(grid).gridTemplateColumns.split(" ").length);
  await progress.evaluate(section => { section.style.width = "360px"; });
  await expect.poll(columnsInContainer).toBe(1);
  await progress.evaluate(section => { section.style.width = "520px"; });
  await expect.poll(columnsInContainer).toBe(2);
  await progress.evaluate(section => { section.style.removeProperty("width"); });
  await expect.poll(columnsInContainer).toBe(3);
  await page.setViewportSize({ width: 390, height: 1080 });
  const results = page.getByRole("group", { name: "Point execution results" });
  await expect(results.getByRole("button")).toHaveCount(20);
  expect(await results.getByRole("button").evaluateAll(buttons => buttons.map(button => button.getAttribute("aria-label"))))
    .toEqual(Array.from({ length: 20 }, (_, index) => `Point P${String(index + 1).padStart(2, "0")}`));
  const stats = await progress.getByText("First pass 8 / 14 valid").textContent();
  await results.getByRole("button", { name: "Point P03", exact: true }).click();
  await expect(page.getByRole("region", { name: "Evidence for P03" })).toBeVisible();
  await expect(map.locator('[data-point-id="cup_test_left_5cm"]')).toHaveAttribute("data-selected", "true");
  await expect(results.getByRole("button", { name: "Point P03", exact: true })).toHaveAttribute("aria-pressed", "true");
  const evidence = page.getByRole("region", { name: "Evidence for P03" });
  await expect(evidence.getByText("First-pass attempt 1: FAILED")).toBeVisible();
  await expect(evidence.getByRole("link", { name: "Download physical-evidence" })).toHaveAttribute("href", "/expert-validation/artifacts/numeric-opaque-p03");
  if (process.env.SO101_LAYOUT_NATIVE_CAPTURE) {
    await evidence.scrollIntoViewIfNeeded();
    const root = process.env.SO101_E2E_EVIDENCE_ROOT!;
    writeFileSync(join(root, "native-ready-evidence-390.json"), JSON.stringify({ title: await page.title(), url: page.url() }));
    const deadline = Date.now() + 120_000;
    while (!existsSync(join(root, "native-captured-evidence-390.receipt"))) {
      if (Date.now() > deadline) throw new Error("NATIVE_EVIDENCE_CAPTURE_TIMEOUT");
      await new Promise(resolve => setTimeout(resolve, 200));
    }
  }
  await results.getByRole("button", { name: "Point P02", exact: true }).focus();
  await page.keyboard.press("Space");
  await expect(page.getByRole("region", { name: "Evidence for P02" })).toBeVisible();
  await results.getByRole("button", { name: "Point P06", exact: true }).click();
  await expect(page.getByRole("region", { name: "Evidence for P06" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)).toBe(false);
  await map.locator('[data-point-id="task_start"]').focus();
  await page.keyboard.press("Enter");
  await expect(results.getByRole("button", { name: "Point P01", exact: true })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByLabel("Retry P03", { exact: true })).toBeEnabled();
  await expect(page.getByLabel("Retry P01", { exact: true })).toBeDisabled();
  await expect(page.getByLabel("Retry P04", { exact: true })).toBeDisabled();
  expect(await progress.getByText("First pass 8 / 14 valid").textContent()).toBe(stats);
  expect(consoleErrors).toEqual([]);
});
