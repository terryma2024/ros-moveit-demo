import type { TelemetrySnapshot } from "./types";

export function isTelemetrySnapshot(value: unknown): value is TelemetrySnapshot {
  if (value === null || typeof value !== "object") return false;
  const candidate = value as Partial<TelemetrySnapshot>;
  return Number.isFinite(candidate.sequence)
    && Number.isFinite(candidate.revision)
    && typeof candidate.simulation_session_id === "string"
    && candidate.simulation_session_id.length > 0
    && candidate.joints !== null
    && typeof candidate.joints === "object";
}
