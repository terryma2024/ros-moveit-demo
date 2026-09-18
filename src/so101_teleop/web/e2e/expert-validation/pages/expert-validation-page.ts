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
 *
 * Release and renew both carry the *current* generation, and every renewal increments it, so the
 * console's own renew responses are what keep this record current.
 */
type LeaseMutation = { service_session_id: string; generation: number };
const acquiredLeases = new Map<string, LeaseMutation>();

/** Record every successful lease mutation the console performs, including its background renewals. */
export function trackConsoleLeases(page: Page): void {
  page.on("response", (response) => {
    const request = response.request();
    if (
      !response.url().includes("/expert-validation/lease") ||
      !["POST", "PUT"].includes(request.method()) ||
      response.status() !== 200
    ) {
      return;
    }
    void response
      .json()
      .then((payload: { lease_id?: string; service_session_id?: string; generation?: number }) => {
        if (!payload?.lease_id || !payload.service_session_id || !payload.generation) return;
        acquiredLeases.set(payload.lease_id, {
          service_session_id: payload.service_session_id,
          generation: payload.generation,
        });
      })
      .catch(() => undefined);
  });
}

export async function releaseAcquiredLeases(request: APIRequestContext): Promise<void> {
  for (const [leaseId, mutation] of [...acquiredLeases]) {
    const response = await request.delete(`/expert-validation/lease/${leaseId}`, {
      data: mutation as unknown as Record<string, unknown>,
    });
    // A lease the service already dropped is not a leak: only a refusal that leaves it held is.
    if (response.status() === 404) {
      acquiredLeases.delete(leaseId);
      continue;
    }
    expect(
      response.ok(),
      `release lease failed: ${response.status()} ${await response.text()}`,
    ).toBe(true);
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
    trackConsoleLeases(this.page);
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
    const payload = (await response.json()) as {
      lease_id: string;
      service_session_id: string;
      generation: number;
    };
    acquiredLeases.set(payload.lease_id, {
      service_session_id: payload.service_session_id,
      generation: payload.generation,
    });
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

  async startValidation(): Promise<string> {
    const [response] = await Promise.all([
      this.page.waitForResponse(
        (candidate) =>
          candidate.url().endsWith("/expert-validation/campaigns") &&
          candidate.request().method() === "POST",
      ),
      this.startButton().click(),
    ]);
    // The heading appears from the console's own state, so reading the campaign list right after
    // the click can return the *previous* campaign: the id has to come from this response.
    expect(
      response.status(),
      `start validation refused: ${response.status()} ${await response.text()}`,
    ).toBe(200);
    const payload = (await response.json()) as { campaign_id?: string };
    expect(payload.campaign_id, "campaign id missing from the start response").toBeTruthy();
    const campaignId = payload.campaign_id as string;
    await expect(
      this.page.getByRole("heading", { name: new RegExp(`^Campaign ${campaignId}`) }),
    ).toBeVisible();
    return campaignId;
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
