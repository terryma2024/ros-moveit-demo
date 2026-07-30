import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { ConfirmAction } from "./confirm-action";

type Props = { leaseHeld: boolean; gazeboAttached?: boolean; moveitAttached?: boolean; shot?: string; cameraPresets: string[]; onCameraPreset: (preset: string) => void; onScreenshot: () => void; onAttach: () => void; onDetach: () => void; onRepair: () => void; onHome: () => void; onReset: () => void };

const presetLabel = (name: string) => name.charAt(0).toUpperCase() + name.slice(1).replaceAll("_", " ");

export function GazeboPanel(props: Props) {
  return <Card><CardTitle>Gazebo evidence and convergence</CardTitle><p className="mt-3 text-sm text-slate-400">Camera view</p><div className="mt-2 flex flex-wrap gap-2">{props.cameraPresets.map((preset) => <Button key={preset} size="sm" variant="outline" disabled={!props.leaseHeld} onClick={() => props.onCameraPreset(preset)}>{presetLabel(preset)}</Button>)}</div><div className="mt-3 flex flex-wrap gap-2"><Button disabled={!props.leaseHeld} onClick={props.onScreenshot}>Capture Gazebo window</Button><ConfirmAction label="Attach" disabled={!props.leaseHeld} onConfirm={props.onAttach}/><ConfirmAction label="Detach" disabled={!props.leaseHeld} onConfirm={props.onDetach}/><ConfirmAction label="Repair scene" disabled={!props.leaseHeld} onConfirm={props.onRepair}/><ConfirmAction label="Home" disabled={!props.leaseHeld} onConfirm={props.onHome}/><ConfirmAction label="Reset world / robot" disabled={!props.leaseHeld} onConfirm={props.onReset}/></div><p className="mt-3">Convergence: Gazebo {String(props.gazeboAttached)} · MoveIt {String(props.moveitAttached)}</p>{props.shot && <a className="text-sky-300 underline" href={props.shot} download>Download latest Gazebo PNG</a>}</Card>;
}
