import { describe, expect, it } from "vitest";

import type { JointSample } from "@/api/types";
import { clampJointTarget, safeJointBounds } from "./joint-limits";

const limited: JointSample = {
  name: "3",
  position_rad: 0,
  velocity_rad_s: 0,
  lower_limit_rad: -1.74533,
  upper_limit_rad: 1.5708,
};

describe("joint safe target limits", () => {
  it("insets both hard limits by exactly half a degree", () => {
    expect(safeJointBounds(limited)).toEqual({
      lowerRad: -1.7366033537400285,
      upperRad: 1.5620733537400284,
    });
  });

  it("passes an in-range target through without a notice", () => {
    expect(clampJointTarget("3", 0.5, limited)).toEqual({ value: 0.5, clamped: false });
  });

  it("stops targets at either safe boundary and identifies the joint", () => {
    expect(clampJointTarget("3", -9, limited)).toEqual({
      value: -1.7366033537400285,
      clamped: true,
      message: "Joint 3 clamped to -99.50° (0.5° safety margin).",
    });
    expect(clampJointTarget("3", 9, limited)).toEqual({
      value: 1.5620733537400284,
      clamped: true,
      message: "Joint 3 clamped to 89.50° (0.5° safety margin).",
    });
  });

  it("fails closed when either hard limit is unavailable", () => {
    expect(safeJointBounds({ ...limited, upper_limit_rad: undefined })).toBeUndefined();
    expect(clampJointTarget("3", 0.5, { ...limited, lower_limit_rad: undefined })).toEqual({
      value: 0.5,
      clamped: false,
      unavailable: true,
    });
  });
});
