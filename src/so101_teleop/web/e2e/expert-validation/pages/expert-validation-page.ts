import { expect, type APIRequestContext, type Locator, type Page } from "@playwright/test";

export type PointStatus =
  | "ELIGIBLE_UNRUN"
  | "LEASED"
  | "EXECUTING"
  | "INFRA_INTERRUPTED_REQUEUEABLE"
  | "PASSED"
  | "FAILED"
  | "INDETERMINATE"
  | "TERMINAL_UNRUN"
  | "INVALID_BLOCKED"
  | "INFRA_FAILED_REMAINDER";

/**
 * Leases acquired through the console, kept at module scope so a teardown can hand them back even
 * when the test itself failed half-way.  The console has no release control, and a suite that
 * acquires an exclusive lease without returning it can run exactly one spec per lease lifetime:
 * the next spec then sees `409 Conflict` on acquire.
 */
const acquiredLeases = new Map<string, string>();

export async function releaseAcquiredLeases(request: APIRequestContext): Promise<void> {
  for (const [leaseId, body] of [...acquiredLeases]) {
    const response = await request.delete(`/expert-validation/lease/${leaseId}`, {
      data: JSON.parse(body) as Record<string, unknown>,
    });
    expect(response.ok(), `release lease failed: ${response.status()}`).toBe(true);
    acquiredLeases.delete(leaseId);
  }
}

export class ExpertValidationPage {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  async goto(): Promise<void> {
    await this.page.goto("/expert-validation");
    await expect(
      this.page.getByRole("heading", { name: "SO-101 Expert Validation" }),
    ).toBeVisible();
  }

  pointCountInput(): Locator {
    return this.page.getByLabel("Final point count");
  }

  async acquireLease(): Promise<void> {
    const [response] = await Promise.all([
      this.page.waitForResponse(
        (candidate) =>
          candidate.url().endsWith("/expert-validation/lease") &&
          candidate.request().method() === "POST",
      ),
      this.page.getByRole("button", { name: "Acquire lease" }).click(),
    ]);
    // The lease is exclusive across the whole deployed service, so a refusal has to be reported
    // here: without this the button simply stays enabled and the failure surfaces as a timeout
    // five seconds later, with the real cause (`409 Conflict`) only visible in the service log.
    expect(
      response.status(),
      `acquire lease refused: ${response.status()} ${await response.text()}`,
    ).toBe(200);
    const payload = (await response.json()) as { lease_id: string };
    acquiredLeases.set(payload.lease_id, response.request().postData() ?? "{}");
    await expect(this.page.getByRole("button", { name: "Acquire lease" })).toBeDisabled();
  }

  async setPointCount(count: number): Promise<void> {
    const input = this.pointCountInput();
    await input.fill(String(count));
  }

  async generateManifest(pointCount?: number): Promise<void> {
    if (pointCount !== undefined) await this.setPointCount(pointCount);
    await this.page.getByRole("button", { name: "Generate points" }).click();
    await expect(this.page.getByRole("img", { name: "Expert validation top view" })).toBeVisible();
  }

  async configureSequential(): Promise<void> {
    await this.page.getByLabel("Execution mode").selectOption("SEQUENTIAL");
  }

  async configureParallel(workerCount: number): Promise<void> {
    await this.page.getByLabel("Execution mode").selectOption("PARALLEL");
    await this.page.getByLabel("Worker count").selectOption(String(workerCount));
  }

  async configureAdaptive(): Promise<void> {
    await this.page.getByLabel("Execution mode").selectOption("ADAPTIVE");
  }

  async runPreflight(): Promise<void> {
    await this.page.getByRole("button", { name: "Check resources" }).click();
  }

  startButton(): Locator {
    return this.page.getByRole("button", { name: "Start validation" });
  }

  async startValidation(): Promise<void> {
    await this.startButton().click();
    await expect(this.page.getByRole("heading", { name: /^Campaign campaign-/ })).toBeVisible();
  }

  notice(text: string | RegExp): Locator {
    return this.page.getByLabel("Campaign setup").getByText(text);
  }

  mapPoint(displayIdOrStatus: string): Locator {
    return this.page.getByRole("button", { name: new RegExp(`^${displayIdOrStatus}\\b`) });
  }

  mapPointById(pointId: string): Locator {
    return this.page.locator(`[data-point-id='${pointId}']`);
  }

  async selectPoint(displayId: string): Promise<void> {
    await this.page
      .getByRole("button", { name: new RegExp(`^${displayId} `) })
      .first()
      .click();
  }

  async expectPointColor(pointId: string, color: "blue" | "green" | "red"): Promise<void> {
    await expect(this.mapPointById(pointId)).toHaveAttribute("data-color", color);
  }

  async expectPointLabel(pointId: string, label: string): Promise<void> {
    await expect(this.mapPointById(pointId)).toHaveAttribute("aria-label", label);
  }

  async expectEqualPointRadius(pointIds: string[]): Promise<void> {
    const radii = new Set<string>();
    for (const pointId of pointIds) {
      radii.add(await this.mapPointById(pointId).getAttribute("data-radius") ?? "");
    }
    expect(radii.size).toBe(1);
  }

  workerCard(workerId: string): Locator {
    return this.page.getByRole("article", { name: `Worker ${workerId}` });
  }

  retryCheckbox(displayId: string): Locator {
    return this.page.getByLabel(`Retry ${displayId}`);
  }

  async retryFailedPoints(displayIds: string[]): Promise<void> {
    for (const displayId of displayIds) {
      await this.retryCheckbox(displayId).check();
    }
    await this.page.getByRole("button", { name: "Retry selected with FULL_RESTART" }).click();
    await this.page.getByLabel("Confirmation").fill("CONFIRM FULL_RESTART RETRIES");
    await this.page.getByRole("button", { name: "Confirm retry" }).click();
  }

  evidenceSection(displayId: string): Locator {
    return this.page.getByRole("region", { name: `Evidence for ${displayId}` });
  }
}
