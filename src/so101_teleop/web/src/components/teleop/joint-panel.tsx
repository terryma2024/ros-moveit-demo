import type { JointSample } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { clampJointTarget, safeJointBounds } from "@/lib/joint-limits";
import { degreesToRadians, radiansToDegrees } from "@/lib/units";

type Props = {
  joints: Record<string, JointSample>;
  targets: Record<string, number>;
  leaseHeld: boolean;
  plan: { id?: string; executable: boolean; staleCode?: string };
  onEdit: (joint: string, value: number) => void;
  onClampNotice?: (message: string) => void;
  onPlan: () => void;
  onExecute: () => void;
  onExecuteGripper: () => void;
  onExecuteAll: () => void;
  onCancel: () => void;
};

export function JointPanel({ joints, targets, leaseHeld, plan, onEdit, onClampNotice, onPlan, onExecute, onExecuteGripper, onExecuteAll, onCancel }: Props) {
  const names = ["1", "2", "3", "4", "5", "6"];
  const blocked = !leaseHeld;
  const applyTarget = (joint: string, value: number) => {
    const result = clampJointTarget(joint, value, joints[joint]);
    if (result.unavailable) return;
    onEdit(joint, result.value);
    if (result.message) onClampNotice?.(result.message);
  };
  return <Card>
    <CardTitle>Joint actual / target</CardTitle>
    <p className="mb-3 text-sm text-slate-400">Axes 1–5 are MoveIt arm joints. Axis 6 uses the gripper controller.</p>
    <div className="overflow-x-auto"><table><thead><tr><th>Joint</th><th>Actual °</th><th>Velocity °/s</th><th>Target °</th><th>Safe range</th><th>Trim</th></tr></thead><tbody>
      {names.map((joint) => {
        const bounds = safeJointBounds(joints[joint]);
        const limitsUnavailable = bounds === undefined;
        return <tr key={joint}><td>{joint}{joint === "6" ? " (gripper)" : ""}</td><td>{radiansToDegrees(joints[joint]?.position_rad ?? 0).toFixed(2)}</td><td>{radiansToDegrees(joints[joint]?.velocity_rad_s ?? 0).toFixed(2)}</td><td><input aria-label={`joint ${joint} target`} type="number" min={bounds ? radiansToDegrees(bounds.lowerRad) : undefined} max={bounds ? radiansToDegrees(bounds.upperRad) : undefined} disabled={limitsUnavailable} value={radiansToDegrees(targets[joint] ?? 0)} onChange={(event) => applyTarget(joint, degreesToRadians(Number(event.target.value)))}/></td><td>{bounds ? `Safe ${radiansToDegrees(bounds.lowerRad).toFixed(2).replace("-", "−")}° to ${radiansToDegrees(bounds.upperRad).toFixed(2)}°` : "Safe limits unavailable"}</td><td><Button disabled={limitsUnavailable} size="sm" variant="secondary" onClick={() => applyTarget(joint, (targets[joint] ?? 0) - degreesToRadians(1))}>−1°</Button> <Button disabled={limitsUnavailable} size="sm" variant="secondary" onClick={() => applyTarget(joint, (targets[joint] ?? 0) + degreesToRadians(1))}>+1°</Button></td></tr>;
      })}
    </tbody></table></div>
    {blocked && <p className="mt-3 text-amber-300">Acquire a control lease before planning.</p>}
    {plan.staleCode && <p className="mt-3 text-amber-300">{plan.staleCode}: Target changed after planning.</p>}
    <div className="mt-4 flex flex-wrap gap-2">
      <Button disabled={blocked} onClick={onPlan}>Plan Arm</Button>
      <Button disabled={!leaseHeld || !plan.executable} onClick={onExecute}>Execute Arm</Button>
      <Button disabled={!leaseHeld} variant="outline" onClick={onCancel}>Cancel</Button>
      <Button disabled={!leaseHeld} variant="secondary" onClick={onExecuteGripper}>Execute gripper</Button>
      <Button disabled={!leaseHeld || !plan.executable} onClick={onExecuteAll}>Execute All</Button>
    </div>
  </Card>;
}
