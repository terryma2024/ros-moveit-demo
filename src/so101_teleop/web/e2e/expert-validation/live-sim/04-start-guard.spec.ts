import { liveSimTest as test, expect, requireGateDetail } from "../fixtures/live-sim";

/**
 * R04: the deployed macOS service advertises the W1/W2 support matrix and the lightweight start
 * guard is what decides a start.
 *
 * macOS supports exactly three routes (W2 first-pass on v4, W1 retry on v5, W1 first-pass on v6).
 * Everything else is refused with the stable `UNSUPPORTED_ON_MACOS` reason and carries no budget
 * profile and no qualification hash: the retired per-N budget takes no part in this host's answer.
 * The guard is a bounded startup check, and the document says so itself.
 */

/** The three approved combinations, exactly as design section 6 fixes them. */
const ROUTES = [
  {
    profile: "MPS_W2_FIRST_PASS",
    schema_version: 4,
    execution_mode: "PARALLEL",
    worker_count: 2,
    batch_kind: "FIRST_PASS",
  },
  {
    profile: "MPS_W1_FULL_RESTART_RETRY",
    schema_version: 5,
    execution_mode: "SEQUENTIAL",
    worker_count: 1,
    batch_kind: "FULL_RESTART_RETRY",
  },
  {
    profile: "MPS_W1_FIRST_PASS",
    schema_version: 6,
    execution_mode: "SEQUENTIAL",
    worker_count: 1,
    batch_kind: "FIRST_PASS",
  },
] as const;

const MACOS_WORKER_COUNTS = [1, 2] as const;
const UNSUPPORTED_WORKER_COUNTS = [3, 4, 5, 6, 7, 8] as const;

test("R04 the macOS matrix is W1/W2 only and every other N is UNSUPPORTED_ON_MACOS @live-sim", async ({ liveServer }) => {
  test.setTimeout(300_000);
  requireGateDetail(process.env.SO101_E2E_EVIDENCE_ROOT!, "R01", {
    evidenceRoot: process.env.SO101_E2E_EVIDENCE_ROOT,
  });
  const response = await fetch(`${liveServer.baseURL}/expert-validation/capabilities`);
  expect(response.ok).toBe(true);
  const capabilities = await response.json();

  // The platform-bound document replaces the budget provider: nothing per-N is consulted.
  expect(capabilities.platform).toBe("macos");
  expect(capabilities.execution_modes).toEqual(["SEQUENTIAL", "PARALLEL"]);
  expect(capabilities.adaptive_default_ladder ?? []).toEqual([]);
  expect(capabilities.worker_qualifications ?? []).toEqual([]);

  // Exactly the three approved routes, with the routing key each request has to claim.
  const rows = capabilities.support_matrix ?? [];
  expect(rows).toHaveLength(ROUTES.length);
  const byProfile = new Map<string, any>(rows.map((row: any) => [row.profile, row]));
  for (const route of ROUTES) {
    const row = byProfile.get(route.profile);
    expect(row, `${route.profile} is missing`).toBeTruthy();
    expect(row.schema_version).toBe(route.schema_version);
    expect(row.execution_mode).toBe(route.execution_mode);
    expect(row.worker_count).toBe(route.worker_count);
    expect(row.batch_kind).toBe(route.batch_kind);
    expect(row.selectable).toBe(true);
    expect(row.status).toBe("SUPPORTED");
    expect(row.reason_codes).toEqual([]);
  }

  // N1 and N2 are the only worker counts this host may run, and they need no hash to be selected.
  const byCount = new Map<number, any>(
    (capabilities.worker_count_availability ?? []).map((entry: any) => [entry.worker_count, entry]),
  );
  for (const workerCount of MACOS_WORKER_COUNTS) {
    const availability = byCount.get(workerCount);
    expect(availability, `N${workerCount} availability missing`).toBeTruthy();
    expect(availability.selectable, `N${workerCount} must be selectable`).toBe(true);
    expect(availability.status).toBe("SUPPORTED");
    expect(availability.reason_codes).toEqual([]);
    expect(availability.profile_sha256 ?? null).toBeNull();
    expect(availability.qualification_sha256 ?? null).toBeNull();
  }
  for (const workerCount of UNSUPPORTED_WORKER_COUNTS) {
    const availability = byCount.get(workerCount);
    expect(availability, `N${workerCount} availability missing`).toBeTruthy();
    expect(availability.selectable, `N${workerCount} must not be selectable`).toBe(false);
    expect(availability.status).toBe("UNSUPPORTED_ON_MACOS");
    expect(availability.reason_codes).toEqual(["UNSUPPORTED_ON_MACOS"]);
    // An unavailable count carries no profile and no qualification hash, so no client can present
    // one as a qualification for a start it is not allowed to make.
    expect(availability.profile_sha256 ?? null).toBeNull();
    expect(availability.qualification_sha256 ?? null).toBeNull();
  }

  // The guard's own policy: the RAM/MPS floors a refusal is judged against, and the CPU busy
  // cutoff that is only ever a warning.
  const policy = capabilities.start_guard_policy;
  expect(policy, "start_guard_policy missing").toBeTruthy();
  expect(policy.timeout_s).toBe(2.0);
  expect(policy.ram_minimum_bytes).toBe(1 << 30);
  expect(policy.ram_minimum_fraction).toBeCloseTo(0.05, 5);
  expect(policy.cpu_busy_warn_fraction).toBeCloseTo(0.9, 5);
  expect(policy.mps_minimum_headroom_bytes).toBe(1 << 30);
  expect(capabilities.start_guard?.status ?? "UNKNOWN").toMatch(/^(PASS|WARN|FAIL|UNKNOWN)$/);

  // A start guard is start protection, not a qualification proof, and the document says so.
  expect(capabilities.start_guard_note).toContain("not a resource qualification proof");
  expect(capabilities.start_guard_note).toContain("one bounded startup check only");
  expect(JSON.stringify(capabilities)).not.toContain("BUDGET_PROFILE_UNAVAILABLE");
});
