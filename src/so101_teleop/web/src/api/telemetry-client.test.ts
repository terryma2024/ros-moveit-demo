import { describe, expect, it } from "vitest";

import { isTelemetrySnapshot } from "./telemetry-client";

describe("telemetry WebSocket schema gate", () => {
  it("rejects Vite HMR or malformed messages before they can invalidate a lease", () => {
    expect(isTelemetrySnapshot({ type: "connected" })).toBe(false);
    expect(isTelemetrySnapshot({ sequence: 1, simulation_session_id: "sim-a" })).toBe(false);
  });

  it("accepts a minimally complete increasing snapshot envelope", () => {
    expect(isTelemetrySnapshot({ sequence: 1, revision: 2, simulation_session_id: "sim-a", joints: {} })).toBe(true);
  });
});
