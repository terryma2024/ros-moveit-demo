import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { ConfirmAction } from "./confirm-action";

type GazeboCapabilities = { physical_observation: boolean; scene_operations: boolean; manual_joint_execute: boolean; reset_world: boolean; camera_presets: boolean };
type Props = { leaseHeld: boolean; capabilities?: GazeboCapabilities; gazeboAttached?: boolean; moveitAttached?: boolean; shot?: string; cameraPresets: string[]; onCameraPreset: (preset: string) => void; onScreenshot: () => void; onAttach: () => void; onDetach: () => void; onRepair: () => void; onHome: () => void; onReset: () => void };

const supported: GazeboCapabilities = { physical_observation: true, scene_operations: true, manual_joint_execute: true, reset_world: true, camera_presets: true };

const presetLabel = (name: string) => name.charAt(0).toUpperCase() + name.slice(1).replaceAll("_", " ");

export function GazeboPanel(props: Props) {
  const capabilities = props.capabilities ?? supported;
  return <Card><CardTitle>Gazebo evidence and convergence</CardTitle><p className="mt-3 text-sm text-slate-400">Camera view</p><div className="mt-2 flex flex-wrap gap-2">{props.cameraPresets.map((preset) => <Button key={preset} size="sm" variant="outline" disabled={!props.leaseHeld || !capabilities.camera_presets} onClick={() => props.onCameraPreset(preset)}>{presetLabel(preset)}</Button>)}</div><div className="mt-3 flex flex-wrap gap-2"><Button disabled={!props.leaseHeld || !capabilities.physical_observation} onClick={props.onScreenshot}>Capture Gazebo window</Button><ConfirmAction label="Attach" disabled={!props.leaseHeld || !capabilities.scene_operations} onConfirm={props.onAttach}/><ConfirmAction label="Detach" disabled={!props.leaseHeld || !capabilities.scene_operations} onConfirm={props.onDetach}/><ConfirmAction label="Repair scene" disabled={!props.leaseHeld || !capabilities.scene_operations} onConfirm={props.onRepair}/><ConfirmAction label="Home" disabled={!props.leaseHeld || !capabilities.manual_joint_execute} onConfirm={props.onHome}/><ConfirmAction label="Reset world / robot" disabled={!props.leaseHeld || !capabilities.reset_world} onConfirm={props.onReset}/></div><p className="mt-3">Convergence: Gazebo {String(props.gazeboAttached)} · MoveIt {String(props.moveitAttached)}</p>{props.shot && <a className="text-sky-300 underline" href={props.shot} download>Download latest Gazebo PNG</a>}</Card>;
}
