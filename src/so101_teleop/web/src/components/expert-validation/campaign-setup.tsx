import type {
  CampaignConfiguration,
  Capabilities,
  ExecutionMode,
  StartGuardStatus,
} from "@/api/expert-validation-types";
import { workerOption, type QualificationView } from "@/api/qualification-view";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type SetupState = {
  pointCount: number;
  executionMode: ExecutionMode;
  workerCount: number;
};

/**
 * The published capability document. The generated schema is the authority for it - including the
 * platform-bound `support_matrix`, `platform` and `start_guard_note` fields - so nothing here
 * restates that shape.
 */
export type PlatformCapabilities = Capabilities;

/**
 * One row of the platform-bound support matrix (`ExecutionProfileResponse`). The row is the whole
 * statement for this host: it carries no budget profile and no qualification hash, and the routing
 * key a request has to claim is `(profile, batch_kind)`.
 */
export type SupportMatrixRow = Capabilities["support_matrix"][number];

export type ExecutionBatchKind = SupportMatrixRow["batch_kind"];

/** The routing key a start or preflight request claims: never inferred, never half-filled. */
export type ExecutionClaim = {
  execution_profile: NonNullable<CampaignConfiguration["execution_profile"]>;
  batch_kind: NonNullable<CampaignConfiguration["batch_kind"]>;
};

/** The service's own note beside the guard policy, kept verbatim so the UI cannot soften it. */
export const START_GUARD_NOT_A_QUALIFICATION =
  "The StartGuard policy and status describe one bounded startup check only; they are not a "
  + "resource qualification proof and they do not certify macOS capacity.";

const HARD_GUARD_CHECK = /^(ram|gpu|mps)/;

const GUARD_CHECK_LABELS: Record<string, string> = {
  cpu_busy: "CPU busy",
  cpu_capacity: "CPU capacity",
  ram: "RAM",
  gpu: "GPU",
};

const guardCheckLabel = (name: string): string =>
  GUARD_CHECK_LABELS[name] ?? (name.startsWith("mps") ? "MPS" : name);

/**
 * What the server's startup check means for an operator. A RAM/GPU/MPS FAIL is a hard refusal:
 * that is the resource the physical run needs. A busy CPU is a warning and never blocks a start.
 * Neither is a qualification, which is what the scope line beside it says.
 */
export function startGuardAdmission(guard: StartGuardStatus | null | undefined): string {
  if (!guard) return "Start guard: unknown (not checked yet)";
  const checks = Object.entries(guard.checks ?? {});
  const failed = checks.filter(([, check]) => check.status === "FAIL").map(([name]) => name);
  const warned = checks.filter(([, check]) => check.status === "WARN").map(([name]) => name);
  if (guard.status === "FAIL") {
    const hard = failed.filter((name) => HARD_GUARD_CHECK.test(name));
    const blocking = (hard.length > 0 ? hard : failed).map(guardCheckLabel);
    return `Start guard: FAIL — hard refusal on ${blocking.join(", ") || "an unavailable resource"};`
      + " the campaign cannot start on this host";
  }
  if (guard.status === "WARN") {
    if (checks.some(([name]) => name === "cpu_busy")) {
      return "Start guard: WARN — CPU busy above the cutoff; a warning does not block the start";
    }
    return `Start guard: WARN — ${warned.map(guardCheckLabel).join(", ") || "see checks"};`
      + " a warning does not block the start";
  }
  return "Start guard: PASS";
}

/** The platform-bound matrix the service publishes, or nothing on a host without one. */
export function platformSupportMatrix(
  capabilities?: PlatformCapabilities,
): SupportMatrixRow[] {
  return capabilities?.support_matrix ?? [];
}

/**
 * The execution modes this host may select. The support matrix bounds the set; when the service
 * also declares an order, that order is kept so the selector matches the advertised document.
 */
export function matrixExecutionModes(capabilities?: PlatformCapabilities): ExecutionMode[] {
  const offered = new Set<ExecutionMode>(
    platformSupportMatrix(capabilities)
      .filter((row) => row.selectable !== false)
      .map((row) => row.execution_mode),
  );
  const declared = (capabilities?.execution_modes ?? []).filter((mode) => offered.has(mode));
  return declared.length > 0 ? declared : [...offered];
}

/**
 * The exact matrix row for one selection, or nothing. This is the only place a profile is
 * resolved: a selection the matrix does not carry has no profile, and no point count, budget
 * view or qualification takes part in the answer.
 */
export function matrixRowFor(
  capabilities: PlatformCapabilities | undefined,
  state: Pick<SetupState, "executionMode" | "workerCount">,
  batchKind: ExecutionBatchKind = "FIRST_PASS",
): SupportMatrixRow | undefined {
  return platformSupportMatrix(capabilities).find(
    (row) =>
      row.selectable !== false
      && row.batch_kind === batchKind
      && row.execution_mode === state.executionMode
      && row.worker_count === state.workerCount,
  );
}

/** The routing key a request for this selection must claim, or `null` when it cannot. */
export function executionClaim(
  capabilities: PlatformCapabilities | undefined,
  state: Pick<SetupState, "executionMode" | "workerCount">,
  batchKind: ExecutionBatchKind = "FIRST_PASS",
): ExecutionClaim | null {
  const row = matrixRowFor(capabilities, state, batchKind);
  if (!row) return null;
  // `ExecutionProfileResponse.profile` is a plain string in the generated schema while the request
  // field is the closed profile union: the value is the server's own matrix row (the console never
  // invents one), and a name the request contract does not define is refused 422 by the service.
  return {
    execution_profile: row.profile as ExecutionClaim["execution_profile"],
    batch_kind: row.batch_kind,
  };
}

type Props = {
  capabilities?: PlatformCapabilities;
  /**
   * The read-only per-N qualification view, consulted only for a host that publishes no support
   * matrix. A platform-bound host (macOS W1/W2) is answered by the matrix alone: a qualification
   * view can neither enable nor disable one of its options.
   */
  qualifications?: QualificationView[];
  state: SetupState;
  leaseHeld: boolean;
  leaseRenewing?: boolean;
  manifestReady: boolean;
  preflightMessage?: string;
  startGuardSummary?: string;
  /** The structured guard result: it decides whether the copy reads as a refusal or a warning. */
  startGuard?: StartGuardStatus | null;
  /** The service's own note about what the guard is not. */
  startGuardNote?: string | null;
  onChange: (state: SetupState, field: keyof SetupState) => void;
  onAcquireLease: () => void;
  onGenerate: () => void;
  onPreflight: () => void;
  onStart: () => void;
};

export function CampaignSetup({
  capabilities,
  qualifications,
  state,
  leaseHeld,
  leaseRenewing = false,
  manifestReady,
  preflightMessage,
  startGuardSummary,
  startGuard,
  startGuardNote,
  onChange,
  onAcquireLease,
  onGenerate,
  onPreflight,
  onStart,
}: Props) {
  const matrix = platformSupportMatrix(capabilities);
  const platformBound = matrix.length > 0;
  const validCount = state.pointCount >= 4 && state.pointCount <= 20;
  const adaptive = !platformBound && state.executionMode === "ADAPTIVE";
  const modes: ExecutionMode[] = platformBound
    ? matrixExecutionModes(capabilities)
    : capabilities?.execution_modes ?? ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"];
  const fixedWorkerCounts = capabilities?.fixed_worker_counts ?? [];
  const availabilityList = capabilities?.worker_count_availability ?? [];
  const availability = availabilityList.find((entry) => entry.worker_count === state.workerCount);

  // -- platform-bound (macOS W1/W2) rules -------------------------------------------------------
  const selectedRow = platformBound ? matrixRowFor(capabilities, state) : undefined;
  const firstPassCounts = new Set(
    matrix.filter((row) => row.batch_kind === "FIRST_PASS" && row.selectable !== false)
      .map((row) => row.worker_count),
  );
  const unavailableCounts = platformBound
    ? fixedWorkerCounts.filter((count) => !firstPassCounts.has(count))
    : [];
  const availabilityReason = (count: number): string => {
    const entry = availabilityList.find((candidate) => candidate.worker_count === count);
    return (entry?.reason_codes ?? []).join(", ") || entry?.status || "UNSUPPORTED_ON_MACOS";
  };

  // -- qualification rules (a host without a support matrix only) --------------------------------
  const qualification = platformBound
    ? undefined
    : qualifications?.find((view) => view.selected_n === state.workerCount);
  const qualificationOption = qualification ? workerOption(qualification) : null;
  const validFixedWorkers = platformBound
    ? Boolean(selectedRow)
    : fixedWorkerCounts.includes(state.workerCount)
      && (state.executionMode === "SEQUENTIAL" ? state.workerCount === 1 : state.workerCount >= 2);
  const exactNSelectable = platformBound
    ? Boolean(selectedRow)
    : state.executionMode === "SEQUENTIAL"
      || ((availability?.selectable ?? false) && !(qualificationOption?.disabled ?? false));
  const exactNReason = platformBound
    ? selectedRow
      ? null
      : availabilityReason(state.workerCount) || "UNSUPPORTED_ON_MACOS"
    : qualificationOption?.disabled
      ? qualificationOption.reason
      : availability && !availability.selectable
        ? (availability.reason_codes ?? []).join(", ") || "EXACT_N_UNQUALIFIED"
        : null;

  const optionDisabled = (count: number): boolean => platformBound
    ? !matrix.some(
      (row) =>
        row.batch_kind === "FIRST_PASS"
        && row.selectable !== false
        && row.execution_mode === state.executionMode
        && row.worker_count === count,
    )
    : (state.executionMode === "PARALLEL" && count === 1)
      || Boolean(
        qualifications?.some(
          (view) => view.selected_n === count && workerOption(view).disabled,
        ),
      );

  const optionLabel = (count: number): string => {
    if (count === 1 && state.executionMode === "PARALLEL") return "1 (SEQUENTIAL only)";
    if (platformBound && !firstPassCounts.has(count)) {
      return `${count} · ${availabilityReason(count)}`;
    }
    return String(count);
  };

  return (
    <section aria-label="Campaign setup" className="space-y-3 rounded-lg border border-border bg-card p-4 text-card-foreground">
      <h2 className="text-lg font-semibold">Campaign setup</h2>
      <Label className="block">Catalog seed
        <Input aria-label="Catalog seed" readOnly value="20260911" className="ml-2 w-auto" />
      </Label>
      <Label className="block">Final point count
        <Input
          aria-label="Final point count"
          type="number"
          min={capabilities?.minimum_points ?? 4}
          max={capabilities?.maximum_points ?? 20}
          value={state.pointCount}
          onChange={(event) => onChange({ ...state, pointCount: Number(event.target.value) }, "pointCount")}
          className="ml-2 w-20 bg-muted px-2"
        />
      </Label>
      <Label className="block">Execution mode
        <select
          aria-label="Execution mode"
          value={state.executionMode}
          onChange={(event) => {
            const executionMode = event.target.value as ExecutionMode;
            onChange({
              ...state,
              executionMode,
              workerCount: executionMode === "SEQUENTIAL" ? 1 : executionMode === "PARALLEL" ? 2 : 8,
            }, "executionMode");
          }}
          className="ml-2 bg-muted px-2"
        >
          {modes.map((mode) => (
            <option key={mode} value={mode}>{mode}</option>
          ))}
        </select>
      </Label>
      {!adaptive ? (
        <>
          <Label className="block">Worker count
            <select
              aria-label="Worker count"
              value={state.workerCount}
              disabled={!capabilities || state.executionMode === "SEQUENTIAL"}
              onChange={(event) => onChange({ ...state, workerCount: Number(event.target.value) }, "workerCount")}
              className="ml-2 bg-muted px-2"
            >
              {fixedWorkerCounts.map((count) => (
                <option key={count} value={count} disabled={optionDisabled(count)}>
                  {optionLabel(count)}
                </option>
              ))}
            </select>
          </Label>
          <p>共享队列 · 每 worker 一次一任务</p>
          {platformBound ? (
            <>
              <p aria-live="polite" aria-label="Execution profile">
                {selectedRow
                  ? `${selectedRow.status} · ${selectedRow.profile}`
                    + ` · schema v${selectedRow.schema_version} · ${selectedRow.batch_kind}`
                  : `${availability?.status ?? "UNSUPPORTED_ON_MACOS"}`
                    + ` · ${exactNReason ?? "UNSUPPORTED_ON_MACOS"}`}
              </p>
              {unavailableCounts.length > 0 ? (
                <ul aria-label="Unavailable worker counts">
                  {unavailableCounts.map((count) => (
                    <li key={count}>{`N${count} unavailable · ${availabilityReason(count)}`}</li>
                  ))}
                </ul>
              ) : null}
            </>
          ) : (
            <p aria-live="polite">
              {availability
                ? `${availability.status}${exactNReason ? ` · ${exactNReason}` : ""}`
                : `EXACT_N_UNQUALIFIED · ${exactNReason ?? "BUDGET_PROFILE_UNAVAILABLE"}`}
            </p>
          )}
        </>
      ) : (
        <div className="space-y-1">
          <p>W8 -&gt; W6 -&gt; W4 -&gt; W2 -&gt; W1</p>
          <p>Initial affinity 3 · startup 120 s · infrastructure attempts 5</p>
          <p className="text-warning">Resource observations only</p>
        </div>
      )}
      {preflightMessage ? <p aria-live="polite">{preflightMessage}</p> : null}
      {startGuardSummary
        ? <p aria-live="polite" aria-label="Start guard">{startGuardSummary}</p>
        : null}
      {startGuard
        ? <p aria-live="polite" aria-label="Start guard admission">{startGuardAdmission(startGuard)}</p>
        : null}
      {startGuard
        ? (
          <p aria-label="Start guard scope">
            {startGuardNote ?? START_GUARD_NOT_A_QUALIFICATION}
          </p>
        )
        : null}
      <div className="flex flex-wrap gap-2">
        <Button onClick={onAcquireLease} disabled={leaseHeld || leaseRenewing}>Acquire lease</Button>
        <Button onClick={onGenerate} disabled={!validCount}>Generate points</Button>
        <Button onClick={onPreflight} disabled={!leaseHeld || leaseRenewing || !manifestReady || !adaptive && !validFixedWorkers}>Check resources</Button>
        <Button onClick={onStart} disabled={!leaseHeld || leaseRenewing || !manifestReady || (!adaptive && (!validFixedWorkers || !exactNSelectable))}>Start validation</Button>
      </div>
    </section>
  );
}
