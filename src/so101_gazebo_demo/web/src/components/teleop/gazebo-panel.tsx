import { Button } from "@/components/ui/button";
import { Card, CardTitle } from "@/components/ui/card";
import { ConfirmAction } from "./confirm-action";

type Props = { leaseHeld: boolean; gazeboAttached?: boolean; moveitAttached?: boolean; shot?: string; onScreenshot: () => void; onAttach: () => void; onDetach: () => void; onRepair: () => void; onHome: () => void; onReset: () => void };

export function GazeboPanel(props: Props) {
  return <Card><CardTitle>Gazebo evidence and convergence</CardTitle><div className="mt-3 flex flex-wrap gap-2"><Button disabled={!props.leaseHeld} onClick={props.onScreenshot}>Capture Gazebo window</Button><ConfirmAction label="Attach" disabled={!props.leaseHeld} onConfirm={props.onAttach}/><ConfirmAction label="Detach" disabled={!props.leaseHeld} onConfirm={props.onDetach}/><ConfirmAction label="Repair scene" disabled={!props.leaseHeld} onConfirm={props.onRepair}/><ConfirmAction label="Home" disabled={!props.leaseHeld} onConfirm={props.onHome}/><ConfirmAction label="Reset world / robot" disabled={!props.leaseHeld} onConfirm={props.onReset}/></div><p className="mt-3">Convergence: Gazebo {String(props.gazeboAttached)} · MoveIt {String(props.moveitAttached)}</p>{props.shot && <a className="text-sky-300 underline" href={props.shot} download>Download latest Gazebo PNG</a>}</Card>;
}
