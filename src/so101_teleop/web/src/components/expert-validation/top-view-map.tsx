import { Fragment, type KeyboardEvent } from "react";

import { projectBounds, projectXY, type Projection } from "./projection";

export type MapPointState =
  | "ELIGIBLE_UNRUN"
  | "LEASED"
  | "EXECUTING"
  | "INFRA_INTERRUPTED_REQUEUEABLE"
  | "PASSED"
  | "FAILED"
  | "INDETERMINATE"
  | "TERMINAL_UNRUN"
  | "INVALID_BLOCKED"
  | "INFRA_FAILED_REMAINDER";

type ManifestPoint = {
  id: string;
  display_id: string;
  position_world_m: readonly number[];
  projected_px: readonly number[];
};

type PaletteStyle = { stroke: string; fill: string; icon: string };

export type TopViewManifest = {
  projection: Projection;
  geometry: {
    table_bounds: readonly number[];
    base_bounds: readonly number[];
    target_center: readonly number[];
    target_bounds: readonly number[];
    candidate_bounds?: readonly number[];
    cup_radius_m: number;
    target_tolerance_radius_m: number;
  };
  cup_footprint_radius_px: number;
  target_tolerance_radius_px: number;
  marker_radius_px: number;
  points: readonly ManifestPoint[];
  palette: Record<"blue" | "green" | "red", PaletteStyle>;
};

type CampaignPoint = {
  point_id: string;
  status: MapPointState;
  active_worker_id?: string;
  phase?: string;
  reason?: string;
};

type Props = {
  manifest: TopViewManifest;
  campaign: { points: readonly CampaignPoint[] };
  selectedPointId?: string;
  onSelect: (pointId: string) => void;
};

const BLUE = new Set<MapPointState>([
  "ELIGIBLE_UNRUN",
  "LEASED",
  "EXECUTING",
  "INFRA_INTERRUPTED_REQUEUEABLE",
]);

function semanticColor(state: MapPointState): "blue" | "green" | "red" {
  if (BLUE.has(state)) return "blue";
  if (state === "PASSED") return "green";
  return "red";
}

function PointIcon({ icon }: { icon: string }) {
  if (icon === "passed") {
    return <path d="M -4 0 L -1 3 L 5 -4" fill="none" stroke="currentColor" strokeWidth="2" />;
  }
  if (icon === "failed") {
    return <path d="M -4 -4 L 4 4 M 4 -4 L -4 4" fill="none" stroke="currentColor" strokeWidth="2" />;
  }
  return <circle r="2.5" fill="currentColor" />;
}

function worldGridTicks(lower: number, upper: number): number[] {
  const step = Math.max(0.05, (upper - lower) / 100);
  const first = Math.ceil(lower / step - 1e-9);
  const last = Math.floor(upper / step + 1e-9);
  return Array.from({ length: Math.max(0, last - first + 1) }, (_, index) =>
    Number(((first + index) * step).toFixed(12)));
}

export function TopViewMap({ manifest, campaign, selectedPointId, onSelect }: Props) {
  const { projection, geometry } = manifest;
  const table = projectBounds(projection, geometry.table_bounds);
  const base = projectBounds(projection, geometry.base_bounds);
  const target = projectBounds(projection, geometry.target_bounds);
  const candidates = geometry.candidate_bounds ? projectBounds(projection, geometry.candidate_bounds) : undefined;
  const [targetX, targetY] = projectXY(
    projection,
    geometry.target_center[0],
    geometry.target_center[1],
  );
  const [originX, originY] = projectXY(projection, 0, 0);
  const campaignById = new Map(campaign.points.map((point) => [point.point_id, point]));
  const selectOnKey = (event: KeyboardEvent<SVGGElement>, pointId: string) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onSelect(pointId);
    }
  };

  return (
    <svg
      viewBox={`0 0 ${projection.width_px} ${projection.height_px}`}
      role="img"
      aria-label="Expert validation top view"
      className="h-auto w-full"
    >
      <rect
        data-geometry="table"
        x={table.x}
        y={table.y}
        width={table.width}
        height={table.height}
        fill="#f8fafc"
        stroke="#64748b"
        strokeWidth="2"
      />
      {worldGridTicks(geometry.table_bounds[0], geometry.table_bounds[1]).map((x) => {
        const [projectedX] = projectXY(projection, x, 0);
        return <line key={`x-${x}`} x1={projectedX} y1={table.y} x2={projectedX} y2={table.y + table.height} stroke="#e2e8f0" />;
      })}
      {worldGridTicks(geometry.table_bounds[2], geometry.table_bounds[3]).map((y) => {
        const [, projectedY] = projectXY(projection, 0, y);
        return <line key={`y-${y}`} x1={table.x} y1={projectedY} x2={table.x + table.width} y2={projectedY} stroke="#e2e8f0" />;
      })}
      {candidates ? <rect data-geometry="candidate-region" x={candidates.x} y={candidates.y} width={candidates.width} height={candidates.height} fill="none" stroke="#64748b" strokeDasharray="5 4" /> : null}
      <rect data-geometry="base" x={base.x} y={base.y} width={base.width} height={base.height} fill="#cbd5e1" stroke="#334155" strokeWidth="3" />
      <rect x={originX - 5} y={originY - 5} width="10" height="10" fill="#0f172a" aria-label="Robot base origin" />
      <rect data-geometry="target-region" x={target.x} y={target.y} width={target.width} height={target.height} fill="#fef3c7" stroke="#d97706" />
      <circle data-geometry="target-center" cx={targetX} cy={targetY} r="4" fill="#d97706" />
      <circle data-geometry="target-tolerance" cx={targetX} cy={targetY} r={manifest.target_tolerance_radius_px} fill="none" stroke="#d97706" strokeDasharray="7 5" />
      <circle data-geometry="cup-footprint" cx={manifest.points[0].projected_px[0]} cy={manifest.points[0].projected_px[1]} r={manifest.cup_footprint_radius_px} fill="none" stroke="#475569" strokeDasharray="9 6" />

      {manifest.points.map((manifestPoint) => {
        const point = campaignById.get(manifestPoint.id) ?? {
          point_id: manifestPoint.id,
          status: "ELIGIBLE_UNRUN" as const,
        };
        const color = semanticColor(point.status);
        const style = manifest.palette[color];
        const selected = manifestPoint.id === selectedPointId;
        const label = [
          manifestPoint.display_id,
          point.status,
          point.active_worker_id ? `Worker ${point.active_worker_id}` : null,
          point.phase,
          point.reason,
        ].filter(Boolean).join(" ");
        return (
          <Fragment key={manifestPoint.id}>
          <g
            role="button"
            tabIndex={0}
            aria-label={label}
            data-point-id={manifestPoint.id}
            data-radius={manifest.marker_radius_px}
            data-color={color}
            data-active-worker={point.active_worker_id}
            data-selected={selected ? "true" : "false"}
            transform={`translate(${manifestPoint.projected_px[0]} ${manifestPoint.projected_px[1]})`}
            onClick={() => onSelect(manifestPoint.id)}
            onKeyDown={(event) => selectOnKey(event, manifestPoint.id)}
            style={{ color: style.stroke, cursor: "pointer" }}
          >
            {selected ? (
              <circle
                data-focus-ring={manifestPoint.id}
                r={manifest.marker_radius_px + 7}
                fill="none"
                stroke="#0f172a"
                strokeWidth="2"
              />
            ) : null}
            <circle
              r={manifest.marker_radius_px}
              fill={style.fill}
              stroke={style.stroke}
              strokeWidth={point.active_worker_id ? 5 : 2}
            />
            <PointIcon icon={style.icon} />
          </g>
          <text x={manifestPoint.projected_px[0] + 15} y={manifestPoint.projected_px[1] + 4}
            fontSize="12" fill="#334155" pointerEvents="none" aria-hidden="true">{manifestPoint.display_id}</text>
          </Fragment>
        );
      })}
    </svg>
  );
}
