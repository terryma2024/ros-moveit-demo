import type { Capabilities, ExecutionMode } from "@/api/expert-validation-types";
import { Button } from "@/components/ui/button";

export type SetupState = {
  pointCount: number;
  executionMode: ExecutionMode;
  workerCount: number;
};

type Props = {
  capabilities?: Capabilities;
  state: SetupState;
  leaseHeld: boolean;
  leaseRenewing?: boolean;
  manifestReady: boolean;
  preflightMessage?: string;
  startGuardSummary?: string;
  onChange: (state: SetupState, field: keyof SetupState) => void;
  onAcquireLease: () => void;
  onGenerate: () => void;
  onPreflight: () => void;
  onStart: () => void;
};

export function CampaignSetup({
  capabilities,
  state,
  leaseHeld,
  leaseRenewing = false,
  manifestReady,
  preflightMessage,
  startGuardSummary,
  onChange,
  onAcquireLease,
  onGenerate,
  onPreflight,
  onStart,
}: Props) {
  const validCount = state.pointCount >= 4 && state.pointCount <= 20;
  const adaptive = state.executionMode === "ADAPTIVE";
  const availability = (capabilities?.worker_count_availability ?? []).find(
    (entry) => entry.worker_count === state.workerCount,
  );
  const fixedWorkerCounts = capabilities?.fixed_worker_counts ?? [];
  const validFixedWorkers = fixedWorkerCounts.includes(state.workerCount)
    && (state.executionMode === "SEQUENTIAL" ? state.workerCount === 1 : state.workerCount >= 2);
  const exactNSelectable = state.executionMode === "SEQUENTIAL"
    || (availability?.selectable ?? false);
  return (
    <section aria-label="Campaign setup" className="space-y-3 rounded-lg border border-slate-700 bg-slate-900 p-4">
      <h2 className="text-lg font-semibold">Campaign setup</h2>
      <label className="block">Catalog seed
        <input aria-label="Catalog seed" readOnly value="20260911" className="ml-2 bg-slate-800 px-2" />
      </label>
      <label className="block">Final point count
        <input
          aria-label="Final point count"
          type="number"
          min={capabilities?.minimum_points ?? 4}
          max={capabilities?.maximum_points ?? 20}
          value={state.pointCount}
          onChange={(event) => onChange({ ...state, pointCount: Number(event.target.value) }, "pointCount")}
          className="ml-2 w-20 bg-slate-800 px-2"
        />
      </label>
      <label className="block">Execution mode
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
          className="ml-2 bg-slate-800 px-2"
        >
          {(capabilities?.execution_modes ?? ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"]).map((mode) => (
            <option key={mode} value={mode}>{mode}</option>
          ))}
        </select>
      </label>
      {!adaptive ? (
        <>
          <label className="block">Worker count
            <select
              aria-label="Worker count"
              value={state.workerCount}
              disabled={!capabilities || state.executionMode === "SEQUENTIAL"}
              onChange={(event) => onChange({ ...state, workerCount: Number(event.target.value) }, "workerCount")}
              className="ml-2 bg-slate-800 px-2"
            >
              {fixedWorkerCounts.map((count) => (
                <option key={count} value={count} disabled={state.executionMode === "PARALLEL" && count === 1}>
                  {count === 1 && state.executionMode === "PARALLEL" ? "1 (SEQUENTIAL only)" : count}
                </option>
              ))}
            </select>
          </label>
          <p>共享队列 · 每 worker 一次一任务</p>
          <p aria-live="polite">
            {availability
              ? `${availability.status}${availability.selectable ? "" : ` · ${(availability.reason_codes ?? []).join(", ") || "EXACT_N_UNQUALIFIED"}`}`
              : "EXACT_N_UNQUALIFIED · BUDGET_PROFILE_UNAVAILABLE"}
          </p>
        </>
      ) : (
        <div className="space-y-1">
          <p>W8 -&gt; W6 -&gt; W4 -&gt; W2 -&gt; W1</p>
          <p>Initial affinity 3 · startup 120 s · infrastructure attempts 5</p>
          <p className="text-amber-300">Resource observations only</p>
        </div>
      )}
      {preflightMessage ? <p aria-live="polite">{preflightMessage}</p> : null}
      {startGuardSummary
        ? <p aria-live="polite" aria-label="Start guard">{startGuardSummary}</p>
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
