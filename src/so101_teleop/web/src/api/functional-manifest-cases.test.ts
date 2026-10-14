/**
 * The functional-manifest case selection for a platform-bound (macOS W1/W2) host and for the
 * legacy Linux capability document.
 *
 * Vitest collects `src/**` only, so this test for the e2e manifest fixture lives here, beside
 * `campaign-live-evidence.test.ts` which covers the other e2e module.
 */
import { describe, expect, test } from "vitest";

import {
  selectFunctionalCases,
  type CapabilitiesDocument,
} from "../../e2e/expert-validation/fixtures/functional-cases";

/** The published macOS document: two single-worker matrix rows (no multi-worker route is advertised). */
const MACOS: CapabilitiesDocument = {
  available: true,
  platform: "macos",
  execution_modes: ["SEQUENTIAL"],
  default_execution_mode: "SEQUENTIAL",
  minimum_points: 4,
  maximum_points: 20,
  fixed_worker_counts: [1],
  adaptive_default_ladder: [],
  worker_count_availability: [],
  support_matrix: [
    {
      profile: "MPS_SINGLE_WORKER_FULL_RESTART_RETRY",
      schema_version: 5,
      execution_mode: "SEQUENTIAL",
      worker_count: 1,
      batch_kind: "FULL_RESTART_RETRY",
      accelerator: "mps",
      selector: "MPS:default",
      selectable: true,
      status: "SUPPORTED",
      reason_codes: [],
    },
    {
      profile: "MPS_SINGLE_WORKER_FIRST_PASS",
      schema_version: 6,
      execution_mode: "SEQUENTIAL",
      worker_count: 1,
      batch_kind: "FIRST_PASS",
      accelerator: "mps",
      selector: "MPS:default",
      selectable: true,
      status: "SUPPORTED",
      reason_codes: [],
    },
  ],
  start_guard_policy: { timeout_s: 2 },
  start_guard_note: "not a resource qualification proof",
};

/** The legacy Linux document: SEQUENTIAL only, one worker, no support matrix. */
const LEGACY: CapabilitiesDocument = {
  available: true,
  execution_modes: ["SEQUENTIAL"],
  default_execution_mode: "SEQUENTIAL",
  minimum_points: 4,
  maximum_points: 20,
  fixed_worker_counts: [1],
  adaptive_default_ladder: [],
  worker_count_availability: [],
  start_guard_policy: { timeout_s: 2 },
};

const ids = (cases: Array<{ id: string }>): string[] => cases.map((entry) => entry.id);

describe("selectFunctionalCases on a macOS single-worker host", () => {
  test("derives the sweep from the support matrix", () => {
    const selection = selectFunctionalCases(MACOS);
    expect(ids(selection.cases)).toEqual([
      "sequential-n1-p4",
      "sequential-n1-p20",
      "n1-full-restart-single-point",
    ]);
    // Each first-pass case claims the matrix row it will run under: never a point-count guess.
    expect(selection.caseRoutes["sequential-n1-p20"]).toEqual({
      execution_profile: "MPS_SINGLE_WORKER_FIRST_PASS", schema_version: 6, batch_kind: "FIRST_PASS",
    });
    expect(selection.caseRoutes["n1-full-restart-single-point"]).toEqual({
      execution_profile: "MPS_SINGLE_WORKER_FULL_RESTART_RETRY", schema_version: 5,
      batch_kind: "FULL_RESTART_RETRY",
    });
    expect(selection.platformBound).toBe(true);
    expect(selection.skipped).toEqual([]);
  });

  test("never registers a multi-worker or adaptive case", () => {
    const selection = selectFunctionalCases(MACOS);
    for (const entry of selection.cases) {
      expect(entry.mode).toBe("SEQUENTIAL");
      expect(entry.worker_count).toBe(1);
    }
    expect(ids(selection.cases).some((id) => /^fixed-n|adaptive/.test(id))).toBe(false);
  });

  test("a first-pass shape the matrix does not carry is skipped with its own reason", () => {
    const retryOnly: CapabilitiesDocument = {
      ...MACOS,
      support_matrix: MACOS.support_matrix?.filter((row) => row.batch_kind === "FULL_RESTART_RETRY"),
    };
    const selection = selectFunctionalCases(retryOnly);
    expect(ids(selection.cases)).toEqual(["n1-full-restart-single-point"]);
    const skipped = new Map(selection.skipped.map((entry) => [entry.id, entry.reason]));
    expect([...skipped.keys()].sort()).toEqual(["sequential-n1-p20", "sequential-n1-p4"]);
    expect(skipped.get("sequential-n1-p4"))
      .toBe("EXECUTION_ROUTE_NOT_IN_SUPPORT_MATRIX: SEQUENTIAL/N1/FIRST_PASS");
  });

  test("an explicitly requested case outside the matrix is refused with its reason", () => {
    const retryOnly: CapabilitiesDocument = {
      ...MACOS,
      support_matrix: MACOS.support_matrix?.filter((row) => row.batch_kind === "FULL_RESTART_RETRY"),
    };
    expect(() => selectFunctionalCases(retryOnly, { requestedIds: ["sequential-n1-p4"] }))
      .toThrow(/FUNCTIONAL_CASE_NOT_IN_SUPPORT_MATRIX: sequential-n1-p4 \(SEQUENTIAL\/N1\/FIRST_PASS\): EXECUTION_ROUTE_NOT_IN_SUPPORT_MATRIX: SEQUENTIAL\/N1\/FIRST_PASS/);
    // A refused request never silently falls back to a case the host does carry.
    expect(() => selectFunctionalCases(retryOnly, {
      requestedIds: ["n1-full-restart-single-point", "sequential-n1-p4"],
    })).toThrow(/FUNCTIONAL_CASE_NOT_IN_SUPPORT_MATRIX/);
  });

  test("an explicit request for a runnable case selects only that case", () => {
    const selection = selectFunctionalCases(MACOS, { requestedIds: ["sequential-n1-p20"] });
    expect(ids(selection.cases)).toEqual(["sequential-n1-p20"]);
  });

  test("a removed multi-worker case id is unknown", () => {
    expect(() => selectFunctionalCases(MACOS, { requestedIds: ["fixed-n2-p4"] }))
      .toThrow(/FUNCTIONAL_CASE_UNKNOWN: fixed-n2-p4/);
    expect(() => selectFunctionalCases(MACOS, { requestedIds: ["adaptive-ladder-p20"] }))
      .toThrow(/FUNCTIONAL_CASE_UNKNOWN: adaptive-ladder-p20/);
  });

  test("a host whose matrix offers nothing runnable fails loudly", () => {
    const empty: CapabilitiesDocument = {
      ...MACOS,
      support_matrix: MACOS.support_matrix?.map((row) => ({ ...row, selectable: false })),
    };
    expect(() => selectFunctionalCases(empty))
      .toThrow(/NO_RUNNABLE_FUNCTIONAL_CASE: .*EXECUTION_ROUTE_NOT_IN_SUPPORT_MATRIX/);
  });

  test("stays loud when the guard policy or the worker count is missing", () => {
    expect(() => selectFunctionalCases({ ...MACOS, start_guard_policy: null }))
      .toThrow(/START_GUARD_POLICY_MISSING/);
    expect(() => selectFunctionalCases({ ...MACOS, fixed_worker_counts: [] }))
      .toThrow(/NO_SELECTABLE_WORKER_OPTION/);
  });
});

describe("selectFunctionalCases on a legacy host", () => {
  test("registers the sequential cases and the single-point retry only", () => {
    const selection = selectFunctionalCases(LEGACY);
    expect(ids(selection.cases)).toEqual([
      "sequential-n1-p4", "sequential-n1-p20", "n1-full-restart-single-point",
    ]);
    expect(selection.skipped).toEqual([]);
    expect(selection.platformBound).toBe(false);
    expect(selection.workerCounts).toEqual([1]);
  });

  test("still requires SEQUENTIAL to be advertised", () => {
    expect(() => selectFunctionalCases({ ...LEGACY, execution_modes: [] }))
      .toThrow(/MODE_NOT_ADVERTISED: SEQUENTIAL/);
  });

  test("an explicit legacy request filters the sweep", () => {
    const selection = selectFunctionalCases(LEGACY, { requestedIds: ["sequential-n1-p20"] });
    expect(ids(selection.cases)).toEqual(["sequential-n1-p20"]);
  });
});
