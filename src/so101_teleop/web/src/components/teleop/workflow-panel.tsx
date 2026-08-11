import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { ConfirmAction } from "./confirm-action";

const operationLabels: Record<string, string> = {
  start: "Start",
  step: "Next Step",
  run: "Run",
  stop: "Stop",
  resume: "Resume",
  reset: "Reset workflow",
  "force-continue": "Force Continue",
};

const pendingLabels: Record<string, string> = {
  start: "Starting…",
  step: "Stepping…",
  run: "Running…",
  stop: "Stopping…",
  resume: "Resuming…",
  reset: "Resetting workflow…",
  "force-continue": "Force Continuing…",
};

type WorkflowCapabilities = {
  workflow_start: boolean;
  workflow_run: boolean;
  workflow_resume: boolean;
};

const supportedWorkflow: WorkflowCapabilities = {
  workflow_start: true,
  workflow_run: true,
  workflow_resume: true,
};

export function WorkflowPanel({ snapshot, leaseHeld, command, capabilities = supportedWorkflow }: { snapshot?: any; leaseHeld: boolean; command: (operation: string, body?: Record<string, unknown>) => Promise<unknown>; capabilities?: WorkflowCapabilities }) {
  const [pendingOperation, setPendingOperation] = useState<string>();
  const validationFailed = snapshot?.current_state === "VALIDATION_FAILED";
  const pending = pendingOperation !== undefined;
  const hasWorkflow = Boolean(snapshot?.run_id);
  const done = snapshot?.current_state === "DONE";
  const canStart = capabilities.workflow_start && leaseHeld && !hasWorkflow && !pending;
  const canRun = capabilities.workflow_run && leaseHeld && !hasWorkflow && !pending;
  const canContinue = capabilities.workflow_resume && leaseHeld && hasWorkflow && !done && !pending;
  const canReset = capabilities.workflow_resume && leaseHeld && hasWorkflow && !pending;
  const execute = async (operation: string, body?: Record<string, unknown>) => {
    if (pending) return;
    setPendingOperation(operation);
    try {
      await (body === undefined ? command(operation) : command(operation, body));
    } finally {
      setPendingOperation(undefined);
    }
  };
  const label = (operation: string) => pendingOperation === operation ? pendingLabels[operation] : operationLabels[operation];

  return <Card>
    <CardTitle>Checkpointed pick-place workflow</CardTitle>
    <p className="my-3">{snapshot?.current_state ?? "IDLE"} → {snapshot?.next_state ?? "—"}; browser never selects a state.</p>
    {pendingOperation && <p role="status" aria-live="polite" className="mb-3 text-sm text-sky-200">Executing {operationLabels[pendingOperation]}…</p>}
    <div className="flex flex-wrap gap-2">
      <Button disabled={!canStart} onClick={() => void execute("start")}>{label("start")}</Button>
      <Button disabled={!canContinue} onClick={() => void execute("step", { snapshot_revision: snapshot?.snapshot_revision })}>{label("step")}</Button>
      <Button disabled={!canRun} onClick={() => void execute("run")}>{label("run")}</Button>
      <Button disabled={!canContinue} variant="outline" onClick={() => void execute("stop")}>{label("stop")}</Button>
      <Button disabled={!canContinue} onClick={() => void execute("resume")}>{label("resume")}</Button>
      <ConfirmAction label="Reset workflow" disabled={!canReset} onConfirm={() => void execute("reset")}/>
      {validationFailed && <ConfirmAction label="Force Continue" disabled={!leaseHeld || pending} evidence={JSON.stringify(snapshot.validation ?? {}, null, 2)} typedConfirmation="FORCE CONTINUE" onConfirm={() => void execute("force-continue", { snapshot_revision: snapshot?.snapshot_revision, operator_confirmation: "FORCE CONTINUE" })}/>}
    </div>
    <p className="mt-3 text-sm text-slate-400">Force Continue is single-use and audited server-side only for a fresh physical-grasp post-validation failure. Lease, readiness, session, stale-checkpoint, action and controller failures cannot be bypassed.</p>
    {snapshot?.trace && <pre className="mt-3 text-xs">{JSON.stringify(snapshot.trace, null, 2)}</pre>}
  </Card>;
}
