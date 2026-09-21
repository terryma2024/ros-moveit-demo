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

/** The published macOS document: three matrix rows, N1/N2 selectable, no ADAPTIVE route. */
const MACOS: CapabilitiesDocument = {
  available: true,
  platform: "macos",
  execution_modes: ["SEQUENTIAL", "PARALLEL"],
  default_execution_mode: "PARALLEL",
  minimum_points: 4,
  maximum_points: 20,
  fixed_worker_counts: [1, 2, 3, 4, 5, 6, 7, 8],
  adaptive_default_ladder: [],
  worker_count_availability: [
    { worker_count: 1, selectable: true, status: "SUPPORTED", reason_codes: [] },
    { worker_count: 2, selectable: true, status: "SUPPORTED", reason_codes: [] },
    ...[3, 4, 5, 6, 7, 8].map((worker_count) => ({
      worker_count,
      selectable: false,
      status: "UNSUPPORTED_ON_MACOS",
      reason_codes: ["UNSUPPORTED_ON_MACOS"],
    })),
  ],
  support_matrix: [
    {
      profile: "MPS_W2_FIRST_PASS",
      schema_version: 4,
      execution_mode: "PARALLEL",
      worker_count: 2,
      batch_kind: "FIRST_PASS",
      accelerator: "mps",
      selector: "MPS:default",
      selectable: true,
      status: "SUPPORTED",
      reason_codes: [],
    },
    {
      profile: "MPS_W1_FULL_RESTART_RETRY",
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
      profile: "MPS_W1_FIRST_PASS",
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

/** The legacy Linux document: per-N availability and the ADAPTIVE ladder. */
const LEGACY: CapabilitiesDocument = {
  available: true,
  execution_modes: ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"],
  default_execution_mode: "SEQUENTIAL",
  minimum_points: 4,
  maximum_points: 20,
  fixed_worker_counts: [1, 2, 3, 4, 5, 6, 7, 8],
  adaptive_default_ladder: [8, 6, 4, 2, 1],
  worker_count_availability: [2, 3, 4, 5, 6, 7, 8].map((worker_count) => ({
    worker_count,
    selectable: true,
    status: "CONFIGURED",
    reason_codes: [],
  })),
  start_guard_policy: { timeout_s: 2 },
};

const ids = (cases: Array<{ id: string }>): string[] => cases.map((entry) => entry.id);

describe("selectFunctionalCases on a macOS W1/W2 host", () => {
  test("derives the sweep from the support matrix and never demands ADAPTIVE", () => {
    const selection = selectFunctionalCases(MACOS);
    expect(ids(selection.cases)).toEqual([
      "fixed-n2-p4",
      "fixed-n2-p20",
      "sequential-n1-p4",
      "sequential-n1-p20",
      "n1-full-restart-single-point",
    ]);
    // Each first-pass case claims the matrix row it will run under: never a point-count guess.
    expect(selection.caseRoutes["fixed-n2-p4"]).toEqual({
      execution_profile: "MPS_W2_FIRST_PASS", schema_version: 4, batch_kind: "FIRST_PASS",
    });
    expect(selection.caseRoutes["sequential-n1-p20"]).toEqual({
      execution_profile: "MPS_W1_FIRST_PASS", schema_version: 6, batch_kind: "FIRST_PASS",
    });
    expect(selection.caseRoutes["n1-full-restart-single-point"]).toEqual({
      execution_profile: "MPS_W1_FULL_RESTART_RETRY", schema_version: 5,
      batch_kind: "FULL_RESTART_RETRY",
    });
    expect(selection.platformBound).toBe(true);
  });

  test("never registers a PARALLEL case for a worker count the matrix does not carry", () => {
    const selection = selectFunctionalCases(MACOS);
    const parallel = selection.cases.filter((entry) => entry.mode === "PARALLEL");
    expect(parallel.map((entry) => entry.worker_count)).toEqual([2, 2]);
    expect(ids(selection.cases)).not.toContain("fixed-n1-p4");
    for (const entry of selection.cases) {
      expect(entry.mode === "PARALLEL" ? entry.worker_count === 2 : true).toBe(true);
    }
  });

  test("records every unadvertised shape as skipped with its own reason", () => {
    const selection = selectFunctionalCases(MACOS);
    const skipped = new Map(selection.skipped.map((entry) => [entry.id, entry.reason]));
    // `Array#sort` is lexicographic, so the twenty-point ids come before the four-point ones.
    expect([...skipped.keys()].sort()).toEqual([
      "adaptive-ladder-p20",
      "fixed-n1-p20",
      "fixed-n1-p4",
      "sequential-n2-p20",
      "sequential-n2-p4",
    ]);
    expect(skipped.get("fixed-n1-p4"))
      .toBe("EXECUTION_ROUTE_NOT_IN_SUPPORT_MATRIX: PARALLEL/N1/FIRST_PASS");
    expect(skipped.get("sequential-n2-p20"))
      .toBe("EXECUTION_ROUTE_NOT_IN_SUPPORT_MATRIX: SEQUENTIAL/N2/FIRST_PASS");
    expect(skipped.get("adaptive-ladder-p20")).toBe("MODE_NOT_ADVERTISED: ADAPTIVE");
  });

  test("an explicitly requested case outside the matrix is refused with its reason", () => {
    expect(() => selectFunctionalCases(MACOS, { requestedIds: ["fixed-n1-p4"] }))
      .toThrow(/FUNCTIONAL_CASE_NOT_IN_SUPPORT_MATRIX: fixed-n1-p4 \(PARALLEL\/N1\/FIRST_PASS\): EXECUTION_ROUTE_NOT_IN_SUPPORT_MATRIX: PARALLEL\/N1\/FIRST_PASS/);
    expect(() => selectFunctionalCases(MACOS, { requestedIds: ["adaptive-ladder-p20"] }))
      .toThrow(/FUNCTIONAL_CASE_NOT_IN_SUPPORT_MATRIX: adaptive-ladder-p20 .*MODE_NOT_ADVERTISED: ADAPTIVE/);
    // A refused request never silently falls back to a case the host does carry.
    expect(() => selectFunctionalCases(MACOS, { requestedIds: ["fixed-n2-p4", "fixed-n1-p4"] }))
      .toThrow(/FUNCTIONAL_CASE_NOT_IN_SUPPORT_MATRIX/);
  });

  test("an explicit request for a runnable case selects only that case", () => {
    const selection = selectFunctionalCases(MACOS, { requestedIds: ["sequential-n1-p20"] });
    expect(ids(selection.cases)).toEqual(["sequential-n1-p20"]);
  });

  test("an unknown requested case is refused", () => {
    expect(() => selectFunctionalCases(MACOS, { requestedIds: ["fixed-n9-p4"] }))
      .toThrow(/FUNCTIONAL_CASE_UNKNOWN: fixed-n9-p4/);
  });

  test("a host whose matrix offers nothing runnable fails loudly", () => {
    const empty: CapabilitiesDocument = {
      ...MACOS,
      support_matrix: MACOS.support_matrix?.map((row) => ({ ...row, selectable: false })),
    };
    expect(() => selectFunctionalCases(empty))
      .toThrow(/NO_RUNNABLE_FUNCTIONAL_CASE: .*EXECUTION_ROUTE_NOT_IN_SUPPORT_MATRIX/);
  });

  test("stays loud when the guard policy is missing", () => {
    expect(() => selectFunctionalCases({ ...MACOS, start_guard_policy: null }))
      .toThrow(/START_GUARD_POLICY_MISSING/);
    expect(() => selectFunctionalCases({ ...MACOS, worker_count_availability: [] }))
      .toThrow(/NO_SELECTABLE_WORKER_OPTION/);
  });
});

describe("selectFunctionalCases on a legacy host", () => {
  test("keeps today's cases for a host that advertises ADAPTIVE and N>2", () => {
    const selection = selectFunctionalCases(LEGACY);
    const expected: string[] = [];
    for (const workerCount of [2, 3, 4, 5, 6, 7, 8]) {
      expected.push(`fixed-n${workerCount}-p4`, `fixed-n${workerCount}-p20`);
    }
    expected.push("sequential-n1-p4", "adaptive-ladder-p20", "n1-full-restart-single-point");
    expect(ids(selection.cases)).toEqual(expected);
    expect(selection.skipped).toEqual([]);
    expect(selection.platformBound).toBe(false);
    expect(selection.cases.find((entry) => entry.id === "adaptive-ladder-p20")?.worker_count)
      .toBe(8);
  });

  test("still requires the three legacy modes", () => {
    expect(() => selectFunctionalCases({
      ...LEGACY, execution_modes: ["SEQUENTIAL", "PARALLEL"],
    })).toThrow(/MODE_NOT_ADVERTISED: ADAPTIVE/);
  });

  test("an explicit legacy request filters the sweep", () => {
    const selection = selectFunctionalCases(LEGACY, { requestedIds: ["fixed-n8-p20"] });
    expect(ids(selection.cases)).toEqual(["fixed-n8-p20"]);
  });
});
