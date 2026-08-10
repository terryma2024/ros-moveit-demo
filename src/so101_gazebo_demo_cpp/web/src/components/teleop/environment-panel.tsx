import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export const TELEOP_ENVIRONMENT_KEYS = [
  "ROS_DOMAIN_ID", "ROS_DISTRO", "ROS_VERSION", "ROS_PYTHON_VERSION",
  "ROS_AUTOMATIC_DISCOVERY_RANGE", "AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH",
  "GZ_PARTITION", "GZ_CONFIG_PATH", "GZ_SIM_RESOURCE_PATH",
  "GZ_SIM_SYSTEM_PLUGIN_PATH", "PYTHONPATH", "LD_LIBRARY_PATH",
] as const;

export function EnvironmentPanel({ environment }: { environment: Record<string, string> }) {
  return <Card aria-label="Environment panel" className="min-w-0 overflow-hidden">
    <CardHeader>
      <CardTitle>ROS and Gazebo environment</CardTitle>
      <CardDescription>Read-only allowlisted runtime metadata from the Teleop process.</CardDescription>
    </CardHeader>
    <CardContent className="mt-4 min-w-0 overflow-hidden">
      <Table aria-label="Runtime environment" className="table-fixed">
        <TableHeader><TableRow><TableHead className="w-[32%]">Variable</TableHead><TableHead>Value</TableHead><TableHead className="w-20">Action</TableHead></TableRow></TableHeader>
        <TableBody>{TELEOP_ENVIRONMENT_KEYS.map((key) => {
          const value = environment[key];
          const display = value || "—";
          const title = value ? `${key}=${value}` : `${key} unavailable`;
          return <TableRow key={key}>
            <TableCell data-testid="environment-key" className="break-all font-mono text-xs font-medium">{key}</TableCell>
            <TableCell className="max-w-0 whitespace-normal">
              <Tooltip><TooltipTrigger asChild><span className="block max-h-20 overflow-y-auto break-all font-mono text-xs" title={title}>{display}</span></TooltipTrigger><TooltipContent className="max-w-xl break-all">{title}</TooltipContent></Tooltip>
            </TableCell>
            <TableCell><Button aria-label={`Copy ${key}`} disabled={!value} size="sm" variant="outline" onClick={() => navigator.clipboard.writeText(value)}>Copy</Button></TableCell>
          </TableRow>;
        })}</TableBody>
      </Table>
    </CardContent>
  </Card>;
}
