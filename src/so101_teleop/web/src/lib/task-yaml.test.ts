import { describe, expect, it } from "vitest";

import type { TaskPoint } from "@/api/task-types";
import { dumpTaskYaml, parseTaskYaml } from "./task-yaml";

const points: TaskPoint[] = [
  { id: "task_start", label: "Task start", cup_position_world_m: [0.02, -0.28, 0.165] },
  { id: "free_a", label: "Free A", cup_position_world_m: [0.01, -0.31, 0.165] },
];

describe("task point YAML", () => {
  it("round trips schema version 1 and preserves point order", () => {
    const text = dumpTaskYaml(points);
    expect(text).toContain("schema_version: 1");
    expect(parseTaskYaml(text)).toEqual(points);
  });

  it.each([
    "schema_version: 1\npoints:\n- id: p\n  label: P\n  cup_position_world_m: [.nan, 0, 0]\n",
    "schema_version: 1\npoints:\n- id: p\n  label: P\n  cup_position_world_m: [0, 0]\n",
    "schema_version: 1\npoints:\n- id: p\n  label: P\n  cup_position_world_m: [0, 0, 0]\n- id: p\n  label: Duplicate\n  cup_position_world_m: [0, 0, 0]\n",
    "schema_version: 1\npoints: []\nextra: forbidden\n",
  ])("rejects unsafe or ambiguous documents", (text) => {
    expect(() => parseTaskYaml(text)).toThrow("TASK_POINT_INVALID");
  });
});
