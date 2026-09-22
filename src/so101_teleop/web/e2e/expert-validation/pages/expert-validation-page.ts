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
 *
 * Every mutation also carries the console's own instance authority headers
 * (`X-SO101-Instance-ID/-Proof/-Channel-Revision/-Execution-Generation`).  The unified service
 * refuses a lease mutation without them by design (`409 CONTROLLER_INSTANCE_REQUIRED`), so a
 * release that only sends the body leaves the exclusive controller binding held and poisons every
 * following spec with `CONTROLLER_ALREADY_BOUND`.  The headers are captured from the console's own
 * successful mutations and handed back with the release.
 */
type LeaseMutation = { service_session_id: string; generation: number };
type LeaseRecord = { mutation: LeaseMutation; authority: Record<string, string> };
const acquiredLeases = new Map<string, LeaseRecord>();

/** The authority headers of a request the console itself sent; Playwright lower-cases header names. */
function authorityHeadersOf(headers: Record<string, string>): Record<string, string> {
  const authority: Record<string, string> = {};
  for (const [name, value] of Object.entries(headers)) {
    if (name.toLowerCase().startsWith("x-so101-")) authority[name.toLowerCase()] = value;
  }
  return authority;
}

/** Seed a record for a lease whose mutation this module did not observe (test seam). */
export function rememberLeaseAuthority(
  leaseId: string,
  mutation: LeaseMutation,
  headers: Record<string, string>,
): void {
  acquiredLeases.set(leaseId, { mutation, authority: authorityHeadersOf(headers) });
}

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
    const authority = authorityHeadersOf(request.headers());
    void response
      .json()
      .then((payload: { lease_id?: string; service_session_id?: string; generation?: number }) => {
        if (!payload?.lease_id || !payload.service_session_id || !payload.generation) return;
        acquiredLeases.set(payload.lease_id, {
          mutation: {
            service_session_id: payload.service_session_id,
            generation: payload.generation,
          },
          authority,
        });
      })
      .catch(() => undefined);
  });
}

/**
 * The structured refusal code of a lease mutation, read from its JSON body - `code` or `detail.code`,
 * the two shapes the service uses.  A non-JSON body is only accepted as a bare `ACTIVE_CAMPAIGN`
 * token, never as a loose substring of a longer message, so a tolerance can never widen by accident.
 */
export function refusalCode(body: string): string {
  try {
    const parsed = JSON.parse(body) as { code?: unknown; detail?: { code?: unknown } };
    const code = parsed?.code ?? parsed?.detail?.code;
    return typeof code === "string" ? code : "";
  } catch {
    return /(^|[^A-Z_])ACTIVE_CAMPAIGN([^A-Z_]|$)/.test(body) ? "ACTIVE_CAMPAIGN" : "";
  }
}

export async function releaseAcquiredLeases(request: APIRequestContext): Promise<void> {
  for (const [leaseId, record] of [...acquiredLeases]) {
    const response = await request.delete(`/expert-validation/lease/${leaseId}`, {
      headers: record.authority,
      data: record.mutation as unknown as Record<string, unknown>,
    });
    // A lease the service already dropped is not a leak: only a refusal that leaves it held is.
    if (response.status() === 404) {
      acquiredLeases.delete(leaseId);
      continue;
    }
    const body = response.ok() ? "" : await response.text();
    if (!response.ok() && refusalCode(body) === "ACTIVE_CAMPAIGN") {
      // A lease held by design, not a leak.  The product refuses to release while a campaign is
      // unresolved - a point may still be retried - by raising `LeaseConflict("ACTIVE_CAMPAIGN")`
      // (expert_validation/lease.py:113-117), pinned by
      // test_expert_validation_lease.py::test_active_campaign_rejects_release.  A spec whose body
      // passed must not be reported red for it.  It cannot leak here: this window protocol stops
      // the service at the end of every case, so a held lease never crosses a service.
      console.warn(`LEASE_HELD_BY_DESIGN: ACTIVE_CAMPAIGN ${leaseId}`);
      acquiredLeases.delete(leaseId);
      continue;
    }
    expect(
      response.ok(),
      `release lease failed: ${response.status()} ${body}`,
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
    rememberLeaseAuthority(
      payload.lease_id,
      { service_session_id: payload.service_session_id, generation: payload.generation },
      response.request().headers(),
    );
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

  /**
   * The worker-count control.
   *
   * The macOS console renders both the `Worker count` select and an `Unavailable worker counts`
   * list, so a non-exact label query resolves to two elements and Playwright's strict mode refuses
   * it. The exact label names the one control this page object can select from.
   */
  workerCountSelect(): Locator {
    return this.page.getByLabel("Worker count", { exact: true });
  }

  async configureParallel(workerCount: number): Promise<void> {
    await this.page.getByLabel("Execution mode").selectOption("PARALLEL");
    await this.workerCountSelect().selectOption(String(workerCount));
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
