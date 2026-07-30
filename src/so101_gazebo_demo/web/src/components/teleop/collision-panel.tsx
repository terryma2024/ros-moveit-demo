import type { Pose6D } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export type Evidence = { object_a?: string; object_b?: string; depth_m?: number; source?: string };

const AGE_FIELDS = [
  ["joints", "joints"],
  ["tcp", "tcp"],
  ["object", "object"],
  ["gazebo_contacts", "gazebo contacts"],
  ["moveit_collisions", "MoveIt collisions"],
  ["scene", "scene"],
] as const;

export function formatPoseCoordinate(value: number | undefined) {
  return Number.isFinite(value) ? `${value!.toFixed(3)} m` : "—";
}

export function formatAge(value: number | undefined) {
  if (!Number.isFinite(value)) return "—";
  if (value! > 99.999) return ">99.999 s";
  return `${Math.max(0, value!).toFixed(3)} s`;
}

export function formatDepth(value: number | undefined) {
  if (!Number.isFinite(value)) return "—";
  const millimetres = value! * 1000;
  const normalized = Math.abs(millimetres) < 0.0005 ? 0 : millimetres;
  return `${normalized.toFixed(3)} mm`;
}

function ExactValue({ display, exact, className = "" }: { display: string; exact: string; className?: string }) {
  return <Tooltip><TooltipTrigger asChild><span className={className} title={exact}>{display}</span></TooltipTrigger><TooltipContent>{exact}</TooltipContent></Tooltip>;
}

function TelemetrySummary({ objectPose, controllers, sourceAges }: {
  objectPose?: Pose6D;
  controllers: Record<string, string>;
  sourceAges: Record<string, number>;
}) {
  return <section aria-label="Telemetry summary" className="grid min-w-0 gap-3 rounded-lg border border-slate-700 bg-slate-950/60 p-3 text-sm lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_minmax(0,2fr)]">
    <div className="grid grid-cols-3 gap-2">
      {([['X', objectPose?.x_m], ['Y', objectPose?.y_m], ['Z', objectPose?.z_m]] as const).map(([label, value]) => <div className="min-w-0" key={label}><div className="text-xs text-slate-400">{label}</div><ExactValue display={formatPoseCoordinate(value)} exact={value == null ? "unavailable" : `${label}: ${value}`} className="block truncate font-mono tabular-nums"/></div>)}
    </div>
    <div className="grid grid-cols-2 gap-2">
      {([['Arm', 'arm_controller'], ['Gripper', 'gripper_controller']] as const).map(([label, key]) => <div key={key}><div className="text-xs text-slate-400">{label}</div><Badge variant="outline" className="mt-1 max-w-full border-slate-600 bg-slate-800 text-slate-100">{controllers[key] ?? "—"}</Badge></div>)}
    </div>
    <div className="grid grid-cols-2 gap-x-3 gap-y-1 sm:grid-cols-3">
      {AGE_FIELDS.map(([key, label]) => <div className="flex min-w-0 justify-between gap-2" key={key}><span className="truncate text-slate-400">{label}</span><ExactValue display={formatAge(sourceAges[key])} exact={sourceAges[key] == null ? `${key}: unavailable` : `${key}: ${sourceAges[key]}`} className="shrink-0 font-mono tabular-nums"/></div>)}
    </div>
  </section>;
}

function EvidencePane({ layer, rows }: { layer: "MoveIt" | "Gazebo"; rows: Evidence[] }) {
  const label = `${layer} ${layer === "MoveIt" ? "collisions" : "contacts"}`;
  return <section aria-label={`${layer} evidence pane`} className="flex h-56 min-w-0 flex-col overflow-hidden rounded-lg border border-slate-700 bg-slate-950/60">
    <div className="shrink-0 border-b border-slate-700 px-3 py-2"><h3 className="font-medium">{label}</h3><p className="text-xs text-slate-400">{rows.length} evidence row{rows.length === 1 ? "" : "s"}</p></div>
    {rows.length === 0 ? <Empty className="min-h-0 border-0 p-3"><EmptyHeader><EmptyTitle>No evidence</EmptyTitle><EmptyDescription className="text-slate-400">No current {label.toLowerCase()}.</EmptyDescription></EmptyHeader></Empty> :
      <ScrollArea className="min-h-0 flex-1" tabIndex={0} aria-label={`${label} scroll area`}>
        <Table aria-label={label} className="table-fixed">
          <TableHeader><TableRow><TableHead className="w-[31%]">Object A</TableHead><TableHead className="w-[25%]">Object B</TableHead><TableHead className="w-[19%]">Depth</TableHead><TableHead className="w-[25%]">Source</TableHead></TableRow></TableHeader>
          <TableBody>{rows.map((row, index) => <TableRow key={`${row.object_a}-${row.object_b}-${index}`}>
            <TableCell className="max-w-0"><ExactValue display={row.object_a ?? "—"} exact={row.object_a ?? "unavailable"} className="block truncate"/></TableCell>
            <TableCell className="max-w-0"><ExactValue display={row.object_b ?? "—"} exact={row.object_b ?? "unavailable"} className="block truncate"/></TableCell>
            <TableCell className="font-mono tabular-nums"><ExactValue display={formatDepth(row.depth_m)} exact={row.depth_m == null ? "unavailable" : `${row.depth_m} m`}/></TableCell>
            <TableCell className="max-w-0"><ExactValue display={row.source ?? "—"} exact={row.source ?? "unavailable"} className="block truncate"/></TableCell>
          </TableRow>)}</TableBody>
        </Table>
      </ScrollArea>}
  </section>;
}

export function CollisionPanel({ moveit, gazebo, objectPose, controllers, sourceAges }: {
  moveit: Evidence[];
  gazebo: Evidence[];
  objectPose?: Pose6D;
  controllers: Record<string, string>;
  sourceAges: Record<string, number>;
}) {
  return <Card aria-label="Collision panel" className="min-w-0 overflow-hidden">
    <CardHeader><CardTitle>Collision, contact and physical-grasp validation</CardTitle><CardDescription>Structured telemetry and independently scrollable evidence.</CardDescription></CardHeader>
    <CardContent className="mt-4 grid min-w-0 gap-4"><TelemetrySummary objectPose={objectPose} controllers={controllers} sourceAges={sourceAges}/><div className="grid min-w-0 gap-4 lg:grid-cols-2"><EvidencePane layer="MoveIt" rows={moveit}/><EvidencePane layer="Gazebo" rows={gazebo}/></div></CardContent>
  </Card>;
}
