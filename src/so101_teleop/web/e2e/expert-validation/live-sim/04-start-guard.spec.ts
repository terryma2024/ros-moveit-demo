import { liveSimTest as test, expect, requireGateDetail } from "../fixtures/live-sim";

/**
 * R04: the deployed macOS service advertises the single-worker support matrix and the lightweight
 * start guard is what decides a start.
 *
 * macOS supports exactly two routes (W1 retry on v5, W1 first pass on v6): a native campaign is one
 * worker and multi-worker collection exists only as container shards. The rows carry no budget
 * profile and no qualification hash: the retired per-N budget takes no part in this host's answer.
 * The guard is a bounded startup check, and the document says so itself.
 */

/** The two approved combinations. */
const ROUTES = [
  {
    profile: "MPS_SINGLE_WORKER_FULL_RESTART_RETRY",
    schema_version: 5,
    execution_mode: "SEQUENTIAL",
    worker_count: 1,
    batch_kind: "FULL_RESTART_RETRY",
  },
  {
    profile: "MPS_SINGLE_WORKER_FIRST_PASS",
    schema_version: 6,
    execution_mode: "SEQUENTIAL",
    worker_count: 1,
    batch_kind: "FIRST_PASS",
  },
] as const;

test("R04 the macOS matrix is single-worker only @live-sim", async ({ liveServer }) => {
  test.setTimeout(300_000);
  requireGateDetail(process.env.SO101_E2E_EVIDENCE_ROOT!, "R01", {
    evidenceRoot: process.env.SO101_E2E_EVIDENCE_ROOT,
  });
  const response = await fetch(`${liveServer.baseURL}/expert-validation/capabilities`);
  expect(response.ok).toBe(true);
  const capabilities = await response.json();

  // The platform-bound document replaces the budget provider: nothing per-N is consulted.
  expect(capabilities.platform).toBe("macos");
  expect(capabilities.execution_modes).toEqual(["SEQUENTIAL"]);
  expect(capabilities.fixed_worker_counts).toEqual([1]);
  expect(capabilities.adaptive_default_ladder ?? []).toEqual([]);
  expect(capabilities.worker_qualifications ?? []).toEqual([]);

  // Exactly the two approved routes, with the routing key each request has to claim.
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

  // No per-N availability is published at all: there is exactly one worker count.
  expect(capabilities.worker_count_availability ?? []).toEqual([]);

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
