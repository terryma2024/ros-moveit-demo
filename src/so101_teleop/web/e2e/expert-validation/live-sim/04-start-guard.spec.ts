import { liveSimTest as test, expect, requireGateDetail } from "../fixtures/live-sim";

/**
 * R04: the deployed service advertises every configured fixed N and the lightweight start
 * guard is what decides a start.
 *
 * The retired per-N budget is gone: no profile, no qualification document and no acceptance
 * aggregate is required, and a resource state never marks a worker count unqualified. The
 * server runs one bounded CPU/RAM/GPU check per epoch (the browser flow that displays it is
 * covered by the preflight and campaign specs); this case pins the deployed contract.
 */

const WORKER_COUNTS = [2, 3, 4, 5, 6, 7, 8] as const;

test("R04 every configured fixed N is selectable without any budget profile @live-sim", async ({ liveServer }) => {
  test.setTimeout(300_000);
  requireGateDetail(process.env.SO101_E2E_EVIDENCE_ROOT!, "R01", {
    evidenceRoot: process.env.SO101_E2E_EVIDENCE_ROOT,
  });
  const response = await fetch(`${liveServer.baseURL}/expert-validation/capabilities`);
  expect(response.ok).toBe(true);
  const capabilities = await response.json();
  const byCount = new Map<number, any>(
    (capabilities.worker_count_availability ?? []).map((entry: any) => [entry.worker_count, entry]),
  );

  for (const workerCount of WORKER_COUNTS) {
    const availability = byCount.get(workerCount);
    expect(availability, `N${workerCount} availability missing`).toBeTruthy();
    expect(availability.selectable, `N${workerCount} must be selectable`).toBe(true);
    expect(availability.status).toBe("CONFIGURED");
    expect(availability.reason_codes).toEqual([]);
    expect(availability.profile_sha256 ?? null).toBeNull();
    expect(availability.qualification_sha256 ?? null).toBeNull();
  }

  const policy = capabilities.start_guard_policy;
  expect(policy, "start_guard_policy missing").toBeTruthy();
  expect(policy.timeout_s).toBe(2.0);
  expect(policy.ram_minimum_bytes).toBe(1 << 30);
  expect(policy.gpu_minimum_bytes).toBe(1 << 30);
  expect(policy.ram_minimum_fraction).toBeCloseTo(0.05, 5);
  expect(policy.cpu_busy_warn_fraction).toBeCloseTo(0.9, 5);
  expect(JSON.stringify(capabilities)).not.toContain("BUDGET_PROFILE_UNAVAILABLE");
});
