import { describe, expect, it } from "vitest";

import { initialTeleopState, reduceTeleop } from "./teleop-store";

describe("teleop state", () => {
  it("keeps an edited target when newer actual telemetry arrives", () => {
    const edited = reduceTeleop(initialTeleopState(), { type: "edit-joint", joint: "2", value: 0.5 });
    const next = reduceTeleop(edited, {
      type: "telemetry",
      snapshot: { sequence: 2, revision: 9, simulation_session_id: "sim-a", joints: { "2": { position_rad: 0.1, velocity_rad_s: 0 } } },
    });

    expect(next.actual.joints["2"].position_rad).toBe(0.1);
    expect(next.target.joints["2"]).toBe(0.5);
  });

  it("rejects non-increasing telemetry sequences", () => {
    const current = reduceTeleop(initialTeleopState(), {
      type: "telemetry",
      snapshot: { sequence: 4, revision: 8, simulation_session_id: "sim-a", joints: {} },
    });

    const stale = reduceTeleop(current, {
      type: "telemetry",
      snapshot: { sequence: 4, revision: 99, simulation_session_id: "sim-a", joints: {} },
    });

    expect(stale.actual.revision).toBe(8);
  });

  it("marks a server plan stale after its target changes", () => {
    const planned = reduceTeleop(initialTeleopState(), { type: "plan-created", planId: "p1" });
    const edited = reduceTeleop(planned, { type: "edit-joint", joint: "1", value: 0.25 });

    expect(edited.plan.staleCode).toBe("PLAN_STALE_TARGET");
    expect(edited.plan.executable).toBe(false);
  });
});
