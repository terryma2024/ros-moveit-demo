import { describe, expect, it } from "vitest";

import { parseTargetYaml, serializeTargetYaml } from "./target-yaml";

const target = {
  step_frame: "TOOL" as const,
  joints_rad: { "1": 0.1, "6": -0.04 },
  tcp: { frame_id: "world", tcp_frame: "so101_tcp", x_m: 0.02, y_m: -0.28, z_m: 0.2, roll_rad: 0, pitch_rad: 0, yaw_rad: 0 },
};

describe("Target YAML", () => {
  it("round trips every target field without actual telemetry", () => {
    const text = serializeTargetYaml(target);
    expect(text).not.toContain("actual");
    expect(text).not.toContain("source_ages_s");
    expect(parseTargetYaml(text)).toEqual(target);
  });

  it("rejects YAML that does not describe a replayable target", () => {
    expect(() => parseTargetYaml("actual:\n  sequence: 3\n")).toThrow("TARGET_YAML_INVALID");
  });
});
