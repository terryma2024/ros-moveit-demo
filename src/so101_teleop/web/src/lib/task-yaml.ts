import { parse, stringify } from "yaml";

import type { TaskPoint } from "@/api/task-types";

const safeId = /^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$/;

function exactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  const actual = Object.keys(value).sort();
  return actual.length === keys.length && actual.every((key, index) => key === [...keys].sort()[index]);
}

export function validateTaskPoints(points: unknown): TaskPoint[] {
  if (!Array.isArray(points) || points.length === 0 || points.length > 100) throw new Error("TASK_POINT_INVALID");
  const result: TaskPoint[] = points.map((candidate) => {
    if (!candidate || typeof candidate !== "object") throw new Error("TASK_POINT_INVALID");
    const point = candidate as Record<string, unknown>;
    if (!exactKeys(point, ["id", "label", "cup_position_world_m"])) throw new Error("TASK_POINT_INVALID");
    if (typeof point.id !== "string" || !safeId.test(point.id) || typeof point.label !== "string" || point.label.length === 0 || point.label.length > 120) {
      throw new Error("TASK_POINT_INVALID");
    }
    const xyz = point.cup_position_world_m;
    if (!Array.isArray(xyz) || xyz.length !== 3 || !xyz.every((value) => typeof value === "number" && Number.isFinite(value))) {
      throw new Error("TASK_POINT_INVALID");
    }
    return { id: point.id, label: point.label, cup_position_world_m: [xyz[0], xyz[1], xyz[2]] };
  });
  if (new Set(result.map((point) => point.id)).size !== result.length) throw new Error("TASK_POINT_INVALID");
  return result;
}

export function parseTaskYaml(text: string): TaskPoint[] {
  let document: unknown;
  try {
    document = parse(text);
  } catch {
    throw new Error("TASK_POINT_INVALID");
  }
  if (!document || typeof document !== "object") throw new Error("TASK_POINT_INVALID");
  const record = document as Record<string, unknown>;
  if (!exactKeys(record, ["schema_version", "points"]) || record.schema_version !== 1) throw new Error("TASK_POINT_INVALID");
  return validateTaskPoints(record.points);
}

export function dumpTaskYaml(points: TaskPoint[]): string {
  return stringify({ schema_version: 1, points: validateTaskPoints(points) });
}
