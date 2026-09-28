import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export const ACT_PANEL_PHASES = [
  "SEARCH", "LOCK", "STABLE", "RECORD", "TEACHER_INFERENCE",
  "EXPERT", "RELEASE", "RETREAT", "FINAL_CHECK", "QC",
] as const;

export type ActStatus = {
  phase: string;
  remaining_s: number;
  cameras: { head: boolean; wrist: boolean };
  outcome?: string | null;
  last_command?: string | null;
};

function cameraLabel(available: boolean) {
  return available ? "streaming" : "unavailable";
}

export function ActPanel({ status }: { status?: ActStatus | null }) {
  if (!status) {
    return <Card aria-label="ACT panel">
      <CardHeader>
        <CardTitle>ACT session</CardTitle>
        <CardDescription>No session has been started from this browser.</CardDescription>
      </CardHeader>
    </Card>;
  }
  const index = ACT_PANEL_PHASES.indexOf(status.phase as (typeof ACT_PANEL_PHASES)[number]);
  return <Card aria-label="ACT panel">
    <CardHeader>
      <CardTitle>ACT session</CardTitle>
      <CardDescription>
        Phase <span className="font-mono" data-testid="act-phase">{status.phase}</span>
        {index >= 0 ? <> ({index + 1} of {ACT_PANEL_PHASES.length})</> : <> (not a planned phase)</>}
      </CardDescription>
    </CardHeader>
    <CardContent className="mt-4">
      <Table aria-label="ACT session detail">
        <TableHeader><TableRow><TableHead>Field</TableHead><TableHead>Value</TableHead></TableRow></TableHeader>
        <TableBody>
          <TableRow>
            <TableCell>Remaining</TableCell>
            <TableCell className="font-mono" data-testid="act-remaining">
              {status.remaining_s >= 0 ? `${status.remaining_s.toFixed(1)} s` : "unknown"}
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell>Head camera</TableCell>
            <TableCell className="font-mono" data-testid="act-camera-head">
              {cameraLabel(status.cameras.head)}
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell>Wrist camera</TableCell>
            <TableCell className="font-mono" data-testid="act-camera-wrist">
              {cameraLabel(status.cameras.wrist)}
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell>Last command</TableCell>
            <TableCell className="font-mono" data-testid="act-last-command">
              {status.last_command || "none"}
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell>Outcome</TableCell>
            <TableCell className="font-mono" data-testid="act-outcome">
              {status.outcome || "in progress"}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </CardContent>
  </Card>;
}
