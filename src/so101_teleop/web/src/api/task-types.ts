import type { CommandResult } from "./types";

export type TaskPoint = {
  id: string;
  label: string;
  cup_position_world_m: [number, number, number];
};

export type TaskPointStatus = "PENDING" | "REACHABLE" | "UNREACHABLE" | "UNKNOWN";

export type TaskPresetResponse = {
  schema_version: 1;
  points: TaskPoint[];
};

export type TaskRunRequest = {
  schema_version: 1;
  points: TaskPoint[];
  session_id: string;
  lease_id: string;
  command_id: string;
};

export type TaskPointSummary = {
  id: string;
  status: string;
  failure_code?: string | null;
  reachability_status?: string | null;
  reset_epoch?: number | null;
  artifact_ids: string[];
};

export type TaskRunSummary = {
  run_id: string;
  status: string;
  simulation_session_id: string;
  points: TaskPointSummary[];
  first_shared_failure?: string | null;
};

export type ReachabilityReport = {
  point_id: string;
  status: "REACHABLE" | "UNREACHABLE" | "UNKNOWN";
  first_failure_code?: string | null;
  [key: string]: unknown;
};

export type ReachabilityResponse = {
  status: string;
  reports: ReachabilityReport[];
  simulation_session_id: string;
};

export type CaptureResponse = {
  capture_id: string;
  status: string;
  artifact_ids: string[];
  source_stamp_ns?: number | null;
  summary: Record<string, unknown>;
  artifacts: TaskArtifact[];
};

export type TaskArtifact = {
  artifact_id: string;
  name: string;
  media_type: string;
  byte_size: number;
  sha256: string;
};

export type RenderedPointCloudMetadata = {
  source_artifact_id: string;
  source_sha256: string;
  view_matrix: number[];
  projection_matrix: number[];
  point_size: number;
  color_mode: "rgb" | "uniform";
  background_rgb: [number, number, number];
  viewport_px: [number, number];
  original_point_count: number;
  displayed_point_count: number;
  sampling_rule: "all" | "fixed-stride";
  sampling_stride: number;
  captured_at: string;
};

export type TaskEvent = {
  sequence: number;
  kind: string;
  run_id?: string | null;
  point_id?: string | null;
  status: string;
  failure_code?: string | null;
};

export type TaskMutationResult = TaskRunSummary | ReachabilityResponse | CaptureResponse | CommandResult;

export function isCommandFailure(value: unknown): value is CommandResult {
  return typeof value === "object" && value !== null && "code" in value && "succeeded" in value;
}
