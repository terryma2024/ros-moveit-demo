import type { Pose6D, StepFrame } from "@/api/types";
import { Button } from "@/components/ui/button";
import { ButtonGroup } from "@/components/ui/button-group";
import { Card, CardTitle } from "@/components/ui/card";
import { degreesToRadians, radiansToDegrees } from "@/lib/units";

type Axis = "x_m" | "y_m" | "z_m" | "roll_rad" | "pitch_rad" | "yaw_rad";
type Props = { pose: Pose6D; frame: StepFrame; leaseHeld: boolean; planning?: boolean; plan: { executable: boolean; staleCode?: string }; onFrame: (frame: StepFrame) => void; onEdit: (pose: Pose6D) => void; onStep: (axis: Axis, direction: -1 | 1) => void; onPlan: () => void; onExecute: () => void; onCancel: () => void };

export function TcpPanel({ pose, frame, leaseHeld, planning = false, plan, onFrame, onEdit, onStep, onPlan, onExecute, onCancel }: Props) {
  const axes: Axis[] = ["x_m", "y_m", "z_m", "roll_rad", "pitch_rad", "yaw_rad"];
  const label = (axis: Axis, direction: number) => `${axis[0].toUpperCase()} ${direction > 0 ? "+" : "−"}1 ${axis.endsWith("rad") ? "°" : "mm"}`;
  return <Card><CardTitle>TCP Pose6D actual / target</CardTitle>
    <ButtonGroup aria-label="TCP step frame" className="my-3"><Button aria-pressed={frame === "WORLD"} variant={frame === "WORLD" ? "default" : "secondary"} onClick={() => onFrame("WORLD")}>World frame</Button><Button aria-pressed={frame === "TOOL"} variant={frame === "TOOL" ? "default" : "secondary"} onClick={() => onFrame("TOOL")}>Tool frame</Button></ButtonGroup>
    <p className="mb-3 text-sm text-slate-400">Fixed steps are composed in the selected {frame} frame.</p>
    <div className="grid gap-3 md:grid-cols-3">{axes.map((axis) => <label key={axis} className="grid gap-1 text-sm">{axis}<input type="number" value={axis.endsWith("rad") ? radiansToDegrees(pose[axis]) : pose[axis]} onChange={(event) => onEdit({ ...pose, [axis]: axis.endsWith("rad") ? degreesToRadians(Number(event.target.value)) : Number(event.target.value) })}/><span><Button aria-label={label(axis, -1)} size="sm" variant="secondary" onClick={() => onStep(axis, -1)}>{label(axis, -1)}</Button> <Button aria-label={label(axis, 1)} size="sm" variant="secondary" onClick={() => onStep(axis, 1)}>{label(axis, 1)}</Button></span></label>)}</div>
    {plan.staleCode && <p className="mt-3 text-amber-300">{plan.staleCode}: Target changed after planning.</p>}
    <div className="mt-4 flex gap-2"><Button aria-busy={planning} disabled={!leaseHeld || planning} onClick={onPlan}>{planning ? "Planning TCP…" : "Plan TCP"}</Button><Button disabled={!leaseHeld || !plan.executable || planning} onClick={onExecute}>Execute planned TCP</Button><Button disabled={!leaseHeld} variant="outline" onClick={onCancel}>Cancel TCP</Button></div>
  </Card>;
}
