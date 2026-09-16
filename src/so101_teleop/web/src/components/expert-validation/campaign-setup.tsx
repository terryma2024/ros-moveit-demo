import type { Capabilities, ExecutionMode } from "@/api/expert-validation-types";
import { Button } from "@/components/ui/button";

export type SetupState = {
  pointCount: number;
  executionMode: ExecutionMode;
  workerCount: number;
  maxPointsPerWorker: number;
};

type Props = {
  capabilities?: Capabilities;
  state: SetupState;
  leaseHeld: boolean;
  leaseRenewing?: boolean;
  manifestReady: boolean;
  preflightMessage?: string;
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
  onChange,
  onAcquireLease,
  onGenerate,
  onPreflight,
  onStart,
}: Props) {
  const validCount = state.pointCount >= 4 && state.pointCount <= 20;
  const capacity = state.workerCount * state.maxPointsPerWorker;
  const adaptive = state.executionMode === "ADAPTIVE";
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
              maxPointsPerWorker: executionMode === "SEQUENTIAL" ? state.pointCount : 10,
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
              disabled={state.executionMode === "SEQUENTIAL"}
              onChange={(event) => onChange({ ...state, workerCount: Number(event.target.value) }, "workerCount")}
              className="ml-2 bg-slate-800 px-2"
            >
              {[1, 2, 3].map((count) => <option key={count} value={count}>{count}</option>)}
            </select>
          </label>
          <label className="block">Max points per worker
            <input
              aria-label="Max points per worker"
              type="number"
              value={state.maxPointsPerWorker}
              onChange={(event) => onChange({ ...state, maxPointsPerWorker: Number(event.target.value) }, "maxPointsPerWorker")}
              className="ml-2 w-20 bg-slate-800 px-2"
            />
          </label>
          <p>Capacity {capacity} / {state.pointCount}</p>
        </>
      ) : (
        <div className="space-y-1">
          <p>W8 -&gt; W6 -&gt; W4 -&gt; W2 -&gt; W1</p>
          <p>Initial affinity 3 · startup 120 s · infrastructure attempts 5</p>
          <p className="text-amber-300">Resource observations only</p>
        </div>
      )}
      {preflightMessage ? <p aria-live="polite">{preflightMessage}</p> : null}
      <div className="flex flex-wrap gap-2">
        <Button onClick={onAcquireLease} disabled={leaseHeld || leaseRenewing}>Acquire lease</Button>
        <Button onClick={onGenerate} disabled={!validCount}>Generate points</Button>
        <Button onClick={onPreflight} disabled={!leaseHeld || leaseRenewing || !manifestReady}>Check resources</Button>
        <Button onClick={onStart} disabled={!leaseHeld || leaseRenewing || !manifestReady || capacity < state.pointCount && !adaptive}>Start validation</Button>
      </div>
    </section>
  );
}
