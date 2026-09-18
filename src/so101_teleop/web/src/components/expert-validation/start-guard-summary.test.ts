import { describe, expect, it } from "vitest";

import { describeStartGuard } from "./start-guard-summary";

const policy = {
  timeout_s: 2.0,
  cpu_busy_warn_fraction: 0.9,
  ram_minimum_bytes: 1073741824,
  ram_minimum_fraction: 0.05,
  gpu_minimum_bytes: 1073741824,
};

const guard = (status: "PASS" | "WARN" | "FAIL") => ({
  status,
  cleanup_state: "CLEAR" as const,
  gpu_uuid: "GPU-00000000-0000-0000-0000-000000000000",
  observed_monotonic_s: 1000.25,
  checks: {
    cpu_capacity: { status: "PASS" as const, reason: "CPU_CAPACITY_OK", observed: 24.0, cutoff: null, unit: "cores" },
    cpu_busy: { status, reason: status === "WARN" ? "CPU_BUSY" : "CPU_BUSY_OK", observed: 0.95, cutoff: 0.9, unit: "fraction" },
    ram: { status: "PASS" as const, reason: "RAM_OK", observed: 32212254720, cutoff: 1073741824, unit: "bytes" },
    gpu: { status: "PASS" as const, reason: "GPU_OK", observed: 16000000000, cutoff: 1073741824, unit: "bytes" },
  },
});

describe("describeStartGuard", () => {
  it("renders a pass with units, floors and the observation time", () => {
    const text = describeStartGuard(guard("PASS"), policy);
    expect(text).toContain("Start guard: PASS");
    expect(text).toContain("CPU 24.0 cores");
    expect(text).toContain("RAM free 30.0 GiB vs floor 1.0 GiB");
    expect(text).toContain("checked at 1000.3 s");
    expect(text).toContain("timeout 2.0 s");
  });

  it("shows a warning as a warning and never as a qualification", () => {
    const text = describeStartGuard(guard("WARN"), policy);
    expect(text).toContain("Start guard: WARN");
    expect(text).toContain("CPU busy 95.0% vs 90.0%");
    expect(text).not.toContain("qualified");
  });

  it("keeps the failing reasons for a failure", () => {
    const failed = guard("FAIL");
    failed.checks.ram = { status: "FAIL" as never, reason: "RAM_BELOW_MINIMUM", observed: 1024, cutoff: 1073741824, unit: "bytes" };
    const text = describeStartGuard(failed, policy);
    expect(text).toContain("Start guard: FAIL");
    expect(text).toContain("RAM_BELOW_MINIMUM");
  });

  it("reads as unknown when the server has not checked yet", () => {
    expect(describeStartGuard(undefined, policy)).toBe("Start guard: unknown (not checked yet)");
  });

  it("reports a blocked cleanup instead of pretending everything is clear", () => {
    const blocked = { ...guard("WARN"), cleanup_state: "PROBE_CLEANUP_BLOCKED" as const };
    expect(describeStartGuard(blocked, policy)).toContain("cleanup PROBE_CLEANUP_BLOCKED");
  });
});
