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
