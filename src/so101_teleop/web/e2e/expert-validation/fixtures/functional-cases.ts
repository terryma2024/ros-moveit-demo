/**
 * Functional-acceptance case selection, derived from the deployed capabilities document.
 *
 * `build-functional-manifest.ts` registers the cases the live Playwright projects run, and a host
 * can answer in two ways:
 *
 * - Platform-bound (macOS): the capabilities document carries a closed support matrix - W2 on v4
 *   (PARALLEL/N2, FIRST_PASS), W1 retry on v5 (SEQUENTIAL/N1, FULL_RESTART_RETRY) and W1 first-pass
 *   on v6 (SEQUENTIAL/N1, FIRST_PASS) - and no ADAPTIVE route at all. The sweep is derived from
 *   those rows: a case exists only where the matrix carries that exact (mode, worker count, batch
 *   kind), and every other shape is recorded as skipped with its own reason instead of being
 *   downgraded to something the host does run.
 * - Legacy (Linux): per-N availability plus the ADAPTIVE ladder. A host that advertises ADAPTIVE
 *   and N>2 keeps exactly the cases it has always had; the matrix rules do not apply because there
 *   is no matrix to be outside of.
 *
 * Nothing here is a resource qualification: a case is "run this mode at this worker count with
 * this many points". A requested case the host does not advertise is refused with the reason.
 */

export type FunctionalCaseMode = "SEQUENTIAL" | "PARALLEL" | "ADAPTIVE";
export type FunctionalBatchKind = "FIRST_PASS" | "FULL_RESTART_RETRY";

export type FunctionalCase = {
  id: string;
  mode: FunctionalCaseMode;
  worker_count: number;
  point_count: number;
  lifecycle: FunctionalBatchKind;
  maximum_attempts: number;
  batch_timeout_s: number;
};

export type SupportMatrixRow = {
  profile: string;
  schema_version: number;
  execution_mode: "SEQUENTIAL" | "PARALLEL";
  worker_count: number;
  batch_kind: FunctionalBatchKind;
  accelerator?: string;
  selector?: string;
  selectable?: boolean;
  status?: string;
  reason_codes?: string[];
};

export type WorkerCountAvailability = {
  worker_count: number;
  selectable: boolean;
  status?: string;
  reason_codes?: string[];
};

/** The published capabilities document, as far as case selection reads it. */
export type CapabilitiesDocument = {
  available?: boolean;
  platform?: string | null;
  execution_modes?: string[];
  default_execution_mode?: string;
  minimum_points?: number;
  maximum_points?: number;
  fixed_worker_counts?: number[];
  adaptive_default_ladder?: number[];
  worker_count_availability?: WorkerCountAvailability[];
  support_matrix?: SupportMatrixRow[];
  start_guard_policy?: { timeout_s?: number } | null;
  start_guard_note?: string | null;
};

export type SkippedCase = {
  id: string;
  mode: FunctionalCaseMode;
  worker_count: number;
  point_count: number;
  lifecycle: FunctionalBatchKind;
  reason: string;
};

export type FunctionalCaseRoute = {
  execution_profile: string;
  schema_version: number;
  batch_kind: FunctionalBatchKind;
};

export type FunctionalSelection = {
  /** True when the host answered with a platform-bound support matrix. */
  platformBound: boolean;
  cases: FunctionalCase[];
  /** Every shape this host does not carry, with the reason it cannot run. */
  skipped: SkippedCase[];
  workerCounts: number[];
  executionModes: string[];
  /** The matrix row each registered case claims, keyed by case id. */
  caseRoutes: Record<string, FunctionalCaseRoute>;
};

export const CASE_BATCH_TIMEOUT_S = 5400;
export const CASE_POINT_COUNTS = [4, 20] as const;
/** The modes a legacy host has to advertise; a platform-bound host is answered by its matrix. */
export const LEGACY_REQUIRED_MODES = ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"] as const;
const MAXIMUM_ATTEMPTS = 1;
const ADAPTIVE_CASE_ID = "adaptive-ladder-p20";
const RETRY_CASE_POINT_COUNT = 1;

type Candidate = FunctionalCase & { reason: string | null; route?: FunctionalCaseRoute };

const caseOf = (
  id: string,
  mode: FunctionalCaseMode,
  workerCount: number,
  pointCount: number,
  lifecycle: FunctionalBatchKind,
): FunctionalCase => ({
  id,
  mode,
  worker_count: workerCount,
  point_count: pointCount,
  lifecycle,
  maximum_attempts: MAXIMUM_ATTEMPTS,
  batch_timeout_s: CASE_BATCH_TIMEOUT_S,
});

const toCase = (candidate: Candidate): FunctionalCase => caseOf(
  candidate.id, candidate.mode, candidate.worker_count, candidate.point_count, candidate.lifecycle,
);

const toSkipped = (candidate: Candidate): SkippedCase => ({
  id: candidate.id,
  mode: candidate.mode,
  worker_count: candidate.worker_count,
  point_count: candidate.point_count,
  lifecycle: candidate.lifecycle,
  reason: candidate.reason as string,
});

/**
 * The cases this host may run, plus every shape it may not and why.
 *
 * `requestedIds` restricts the sweep to exactly those case ids. A requested id the host does not
 * advertise is refused with the stable reason - it is never replaced by a case the host does run.
 */
export function selectFunctionalCases(
  capabilities: CapabilitiesDocument,
  options: { requestedIds?: string[] } = {},
): FunctionalSelection {
  const modes = capabilities.execution_modes ?? [];
  const selectable = (capabilities.worker_count_availability ?? [])
    .filter((entry) => entry.selectable === true)
    .map((entry) => entry.worker_count)
    .sort((first, second) => first - second);
  if (selectable.length === 0) throw new Error("NO_SELECTABLE_WORKER_OPTION");
  if (!capabilities.start_guard_policy?.timeout_s) throw new Error("START_GUARD_POLICY_MISSING");

  const matrix = (capabilities.support_matrix ?? []).filter((row) => row.selectable !== false);
  const platformBound = (capabilities.support_matrix ?? []).length > 0;
  const route = (
    mode: "SEQUENTIAL" | "PARALLEL",
    workerCount: number,
    batchKind: FunctionalBatchKind,
  ): SupportMatrixRow | undefined => matrix.find(
    (row) =>
      row.execution_mode === mode
      && row.worker_count === workerCount
      && row.batch_kind === batchKind,
  );

  const fixedCandidate = (
    id: string,
    mode: FunctionalCaseMode,
    workerCount: number,
    pointCount: number,
    lifecycle: FunctionalBatchKind,
    row: SupportMatrixRow | undefined,
  ): Candidate => ({
    ...caseOf(id, mode, workerCount, pointCount, lifecycle),
    reason: platformBound && row === undefined
      ? `EXECUTION_ROUTE_NOT_IN_SUPPORT_MATRIX: ${mode}/N${workerCount}/${lifecycle}`
      : null,
    ...(row === undefined ? {} : {
      route: {
        execution_profile: row.profile,
        schema_version: row.schema_version,
        batch_kind: row.batch_kind,
      },
    }),
  });

  const adaptiveCandidate = (): Candidate => ({
    ...caseOf(
      ADAPTIVE_CASE_ID, "ADAPTIVE", capabilities.adaptive_default_ladder?.[0] ?? 8, 20, "FIRST_PASS",
    ),
    reason: modes.includes("ADAPTIVE") ? null : "MODE_NOT_ADVERTISED: ADAPTIVE",
  });

  const candidates: Candidate[] = [];
  if (platformBound) {
    // Every selectable count is a candidate for both fixed modes, so a request for a pair the
    // matrix does not carry is answered with that pair's reason instead of disappearing.
    const fixedCounts = [...new Set([
      ...selectable,
      ...matrix.map((row) => row.worker_count),
    ])].sort((first, second) => first - second);
    for (const workerCount of fixedCounts) {
      for (const pointCount of CASE_POINT_COUNTS) {
        candidates.push(fixedCandidate(
          `fixed-n${workerCount}-p${pointCount}`, "PARALLEL", workerCount, pointCount,
          "FIRST_PASS", route("PARALLEL", workerCount, "FIRST_PASS"),
        ));
      }
    }
    for (const workerCount of fixedCounts) {
      for (const pointCount of CASE_POINT_COUNTS) {
        candidates.push(fixedCandidate(
          `sequential-n${workerCount}-p${pointCount}`, "SEQUENTIAL", workerCount, pointCount,
          "FIRST_PASS", route("SEQUENTIAL", workerCount, "FIRST_PASS"),
        ));
      }
    }
    const retryRow = matrix.find((row) => row.batch_kind === "FULL_RESTART_RETRY");
    if (retryRow !== undefined && (retryRow.execution_mode !== "SEQUENTIAL" || retryRow.worker_count !== 1)) {
      // The plan freezes the five-consecutive stability record at SEQUENTIAL/N1 FULL_RESTART:
      // a matrix that moved the retry route has to be resolved by a human, not by a rewritten case.
      throw new Error(
        "STABILITY_ROUTE_MISMATCH: FULL_RESTART_RETRY is "
        + `${retryRow.execution_mode}/N${retryRow.worker_count}, the frozen record is SEQUENTIAL/N1`,
      );
    }
    candidates.push(fixedCandidate(
      `n${retryRow?.worker_count ?? 1}-full-restart-single-point`,
      retryRow?.execution_mode ?? "SEQUENTIAL",
      retryRow?.worker_count ?? 1,
      RETRY_CASE_POINT_COUNT,
      "FULL_RESTART_RETRY",
      retryRow,
    ));
    candidates.push(adaptiveCandidate());
  } else {
    for (const required of LEGACY_REQUIRED_MODES) {
      if (!modes.includes(required)) throw new Error(`MODE_NOT_ADVERTISED: ${required}`);
    }
    for (const workerCount of selectable) {
      for (const pointCount of CASE_POINT_COUNTS) {
        candidates.push(fixedCandidate(
          `fixed-n${workerCount}-p${pointCount}`, "PARALLEL", workerCount, pointCount,
          "FIRST_PASS", undefined,
        ));
      }
    }
    candidates.push(fixedCandidate(
      "sequential-n1-p4", "SEQUENTIAL", 1, 4, "FIRST_PASS", undefined,
    ));
    candidates.push(adaptiveCandidate());
    candidates.push(fixedCandidate(
      "n1-full-restart-single-point", "SEQUENTIAL", 1, RETRY_CASE_POINT_COUNT,
      "FULL_RESTART_RETRY", undefined,
    ));
  }

  const runnable = candidates.filter((candidate) => candidate.reason === null);
  if (runnable.length === 0) {
    throw new Error(
      `NO_RUNNABLE_FUNCTIONAL_CASE: ${candidates.map((c) => `${c.id} (${c.reason})`).join("; ")}`,
    );
  }

  const requested = (options.requestedIds ?? []).map((id) => id.trim()).filter(Boolean);
  let selected = runnable;
  if (requested.length > 0) {
    const byId = new Map(candidates.map((candidate) => [candidate.id, candidate]));
    selected = requested.map((id) => {
      const candidate = byId.get(id);
      if (candidate === undefined) throw new Error(`FUNCTIONAL_CASE_UNKNOWN: ${id}`);
      if (candidate.reason !== null) {
        throw new Error(
          "FUNCTIONAL_CASE_NOT_IN_SUPPORT_MATRIX: "
          + `${id} (${candidate.mode}/N${candidate.worker_count}/${candidate.lifecycle}): `
          + candidate.reason,
        );
      }
      return candidate;
    });
  }

  const caseRoutes: Record<string, FunctionalCaseRoute> = {};
  for (const candidate of selected) {
    if (candidate.route !== undefined) caseRoutes[candidate.id] = candidate.route;
  }
  return {
    platformBound,
    cases: selected.map(toCase),
    skipped: candidates.filter((candidate) => candidate.reason !== null).map(toSkipped),
    workerCounts: selectable,
    executionModes: modes,
    caseRoutes,
  };
}
