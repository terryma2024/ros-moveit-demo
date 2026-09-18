import { liveSimTest as test, expect, requireGateDetail } from "../fixtures/live-sim";
import { ExpertValidationPage } from "../pages/expert-validation-page";

/**
 * R04: exact-N resource availability for N2..8.  Every option must show its qualification
 * status and reason; an unqualified N cannot start and the server refuses it directly;
 * a qualified N starts with the exact requested runtime slots; N > points never downgrades
 * the requested count.  Physical qualification comes from the sealed evidence verifier.
 */

const WORKER_COUNTS = [2, 3, 4, 5, 6, 7, 8] as const;
const POINT_COUNTS = [4, 20] as const;

test("R04 availability is explicit for every fixed N @live-sim", async ({ page, liveServer }) => {
  test.setTimeout(600_000);
  requireGateDetail(process.env.SO101_E2E_EVIDENCE_ROOT!, "R01", {
    evidenceRoot: process.env.SO101_E2E_EVIDENCE_ROOT,
  });
  const app = new ExpertValidationPage(page);
  await app.goto();
  const capabilities = await (await fetch(`${liveServer.baseURL}/expert-validation/capabilities`)).json();
  const byCount = new Map<number, any>(
    (capabilities.worker_count_availability ?? []).map((entry: any) => [entry.worker_count, entry]),
  );

  for (const workerCount of WORKER_COUNTS) {
    const availability = byCount.get(workerCount);
    expect(availability, `N${workerCount} availability missing`).toBeTruthy();
    expect(typeof availability.status).toBe("string");
    expect(Array.isArray(availability.reason_codes)).toBe(true);
    if (!availability.selectable) {
      expect(availability.reason_codes.length).toBeGreaterThan(0);
    }
    await app.acquireLease();
    await app.generateManifest(20);
    await app.configureParallel(workerCount);
    await expect(page.getByText("共享队列 · 每 worker 一次一任务")).toBeVisible();
    await expect(page.getByLabel("Max points per worker")).toHaveCount(0);
    await expect(page.getByText(/^Capacity/)).toHaveCount(0);
    const selected = page.getByLabel("Worker count");
    await expect(selected).toHaveValue(String(workerCount));
    if (!availability.selectable) {
      await expect(app.startButton()).toBeDisabled();
    }
  }
});

for (const pointCount of POINT_COUNTS) {
  test(`R04 qualified exact N keeps its count with ${pointCount} points @live-sim`,
    async ({ page, liveServer }) => {
      test.setTimeout(1_800_000);
      const capabilities = await (
        await fetch(`${liveServer.baseURL}/expert-validation/capabilities`)
      ).json();
      const selectable = (capabilities.worker_count_availability ?? [])
        .filter((entry: any) => entry.selectable)
        .map((entry: any) => entry.worker_count as number)
        .sort((a: number, b: number) => a - b);
      test.skip(selectable.length === 0, "no exact N is qualified on this host");

      const workerCount = selectable[selectable.length - 1];
      const app = new ExpertValidationPage(page);
      await app.goto();
      await app.acquireLease();
      await app.generateManifest(pointCount);
      await app.configureParallel(workerCount);
      await app.runPreflight();
      await app.startValidation();

      const campaigns = await (
        await fetch(`${liveServer.baseURL}/expert-validation/campaigns`)
      ).json();
      expect(campaigns).toHaveLength(1);
      const campaignId = campaigns[0].campaign_id;
      const projection = await (
        await fetch(`${liveServer.baseURL}/expert-validation/campaigns/${campaignId}`)
      ).json();
      // The requested exact N is preserved even when points < workers.
      expect(projection.workers?.length ?? 0).toBe(workerCount);
      expect(projection.workers.map((worker: any) => worker.worker_id)).toEqual(
        Array.from({ length: workerCount }, (_, index) =>
          `worker-${String(index + 1).padStart(2, "0")}`),
      );
    });
}
