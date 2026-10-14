// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { CampaignProgress } from "./campaign-progress";
import {
  CampaignSetup,
  SINGLE_WORKER,
  START_GUARD_NOT_A_QUALIFICATION,
  executionClaim,
} from "./campaign-setup";
import { PointEvidence } from "./point-evidence";
import { RetryPanel } from "./retry-panel";

const campaign = {
  campaign_id: "campaign-1", sequence: 9, execution_mode: "SEQUENTIAL" as const,
  status: "COMPLETED_WITH_FAILURES", batch_cleanup_complete: true,
  points: [
    { point_id: "p1", display_id: "P01", status: "PASSED", retry_eligible: false, attempts: [], artifact_ids: [], artifacts: [] },
    { point_id: "p2", display_id: "P02", status: "FAILED", retry_eligible: true, attempts: [], artifact_ids: [], artifacts: [] },
    { point_id: "p3", display_id: "P03", status: "INDETERMINATE", retry_eligible: false, attempts: [], artifact_ids: [], artifacts: [] },
    { point_id: "p4", display_id: "P04", status: "UNRUN", retry_eligible: false, attempts: [], artifact_ids: [], artifacts: [] },
  ],
  workers: [
    { worker_id: "worker-1", generation: 2, state: "STOPPED", lease_count: 2 },
    { worker_id: "worker-2", generation: 1, state: "QUARANTINED", lease_count: 1, quarantine_reason: "RECOVERY_FAILED" },
  ],
  broker: { available: false, reason: "BROKER_RECOVERING" },
  requested: 4, evaluated: 3, execution_started: 3, valid_succeeded: 1,
  valid_failed: 1, indeterminate: 1, not_executed: 1,
  evaluation_coverage: 0.75, execution_coverage: 0.75,
  coverage_complete: false, execution_complete: true, qualification_passed: false,
  levels_used: [], fallback_history: [], infra_attempts: 1, resource_observations: {},
};

describe("expert validation campaign components", () => {
  test("point results preserve order, status, keyboard selection and selected indication", async () => {
    const select = vi.fn();
    const user = userEvent.setup();
    render(<CampaignProgress campaign={campaign} selectedPointId="p2" onSelect={select} />);
    const results = screen.getByRole("group", { name: "Point execution results" });
    const buttons = within(results).getAllByRole("button");
    expect(buttons.map(button => button.getAttribute("aria-label")))
      .toEqual(["Point P01", "Point P02", "Point P03", "Point P04"]);
    expect(buttons[1].getAttribute("aria-pressed")).toBe("true");
    expect(buttons[0].getAttribute("aria-pressed")).toBe("false");
    expect(buttons[1].textContent).toContain("FAILED");
    expect(buttons[3].textContent).toContain("UNRUN");
    await user.click(buttons[1]);
    expect(select).toHaveBeenLastCalledWith("p2");
    buttons[0].focus();
    await user.keyboard(" ");
    expect(select).toHaveBeenLastCalledWith("p1");
  });

  test("only valid failures are retry eligible and confirmation is exact", async () => {
    const user = userEvent.setup();
    const retry = vi.fn();
    render(<RetryPanel campaign={campaign} onRetry={retry} />);
    expect((screen.getByLabelText("Retry P02") as HTMLInputElement).disabled).toBe(false);
    expect((screen.getByLabelText("Retry P01") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Retry P03") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("Retry P04") as HTMLInputElement).disabled).toBe(true);
    await user.click(screen.getByLabelText("Retry P02"));
    await user.click(screen.getByRole("button", { name: "Retry selected with FULL_RESTART" }));
    const confirm = screen.getByRole("button", { name: "Confirm retry" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(true);
    await user.type(screen.getByLabelText("Confirmation"), "CONFIRM FULL_RESTART RETRIES");
    await user.click(confirm);
    expect(retry).toHaveBeenCalledWith(["p2"], "CONFIRM FULL_RESTART RETRIES");
  });

  test("progress separates worker and broker health from product counts", () => {
    render(<CampaignProgress campaign={campaign} />);
    expect(screen.getByLabelText("Worker worker-1")).toBeTruthy();
    expect(screen.getByText("Broker degraded: BROKER_RECOVERING")).toBeTruthy();
    expect(screen.getByText("First pass 1 / 3 valid")).toBeTruthy();
  });

  test("evidence previews inline images and uses opaque download URLs", () => {
    render(<PointEvidence point={campaign.points[1]} artifacts={[
      { artifact_id: "image-1", role: "task-rgb", media_type: "image/png" },
      { artifact_id: "log-1", role: "controller-log", media_type: "text/plain" },
    ]} />);
    expect((screen.getByAltText("task-rgb") as HTMLImageElement).src).toContain(
      "/expert-validation/artifacts/image-1",
    );
    expect((screen.getByRole("link", { name: "Download controller-log" }) as HTMLAnchorElement).href)
      .toContain("/expert-validation/artifacts/log-1");
  });

  test("first-pass attempt evidence is not labelled as a FULL_RESTART retry", () => {
    render(<PointEvidence point={{ ...campaign.points[0], attempts: [{
      generation: 1, status: "PASSED", kind: "FIRST_PASS", attempt_id: "attempt-a",
    }] }} artifacts={[]} />);
    expect(screen.getByText("First-pass attempt 1: PASSED")).toBeTruthy();
    expect(screen.queryByText(/FULL_RESTART attempt/)).toBeNull();
  });



});

describe("campaign setup start guard", () => {
  const props = {
    state: { pointCount: 4 },
    leaseHeld: true,
    manifestReady: true,
    onChange: vi.fn(),
    onAcquireLease: vi.fn(),
    onGenerate: vi.fn(),
    onPreflight: vi.fn(),
    onStart: vi.fn(),
  };

  test("renders the server start-guard line, including an unknown state", () => {
    const { rerender } = render(
      <CampaignSetup {...props} startGuardSummary="Start guard: WARN (CPU busy 95.0% vs 90.0%)" />,
    );
    expect(screen.getByLabelText("Start guard").textContent).toContain("Start guard: WARN");

    rerender(<CampaignSetup {...props} startGuardSummary="Start guard: unknown (not checked yet)" />);
    expect(screen.getByLabelText("Start guard").textContent).toContain("unknown");
  });

  test("shows nothing rather than a green state before the server checks", () => {
    render(<CampaignSetup {...props} />);
    expect(screen.queryByLabelText("Start guard")).toBeNull();
  });
});

describe("CampaignSetup single native worker", () => {
  const base = {
    state: { pointCount: 4 },
    leaseHeld: true,
    manifestReady: true,
    onChange: () => undefined,
    onAcquireLease: () => undefined,
    onGenerate: () => undefined,
    onPreflight: () => undefined,
    onStart: () => undefined,
  };
  const capabilities = {
    available: true,
    execution_modes: ["SEQUENTIAL"] as const,
    default_execution_mode: "SEQUENTIAL" as const,
    minimum_points: 4,
    maximum_points: 20,
    fixed_worker_counts: [1],
    worker_count_availability: [],
    adaptive_default_ladder: [],
  } as never;

  test("there is no mode selector, no worker-count control and no adaptive panel", () => {
    render(<CampaignSetup {...base} capabilities={capabilities} />);
    expect(screen.queryByLabelText("Execution mode")).toBeNull();
    expect(screen.queryByLabelText("Worker count")).toBeNull();
    expect(screen.queryByLabelText(/max points per worker/i)).toBeNull();
    expect(document.body.textContent ?? "").not.toMatch(/ADAPTIVE|PARALLEL|W8|W6|fallback/i);
    expect(screen.getByLabelText("Execution").textContent).toContain("SEQUENTIAL");
  });

  test("a service that publishes its one worker count can preflight and start", () => {
    render(<CampaignSetup {...base} capabilities={capabilities} />);
    expect(screen.getByRole("button", { name: "Check resources" }).hasAttribute("disabled")).toBe(false);
    expect(screen.getByRole("button", { name: "Start validation" }).hasAttribute("disabled")).toBe(false);
  });

  test("nothing starts before the service has published its capabilities", () => {
    render(<CampaignSetup {...base} />);
    expect(screen.getByRole("button", { name: "Check resources" }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: "Start validation" }).hasAttribute("disabled")).toBe(true);
  });

  test("the point count is the only setup choice and it reports through onChange", async () => {
    const onChange = vi.fn();
    render(<CampaignSetup {...base} capabilities={capabilities} onChange={onChange} />);
    await userEvent.setup().type(screen.getByLabelText("Final point count"), "0");
    expect(onChange).toHaveBeenCalled();
    expect(onChange.mock.calls.at(-1)?.[1]).toBe("pointCount");
    expect(Object.keys(onChange.mock.calls.at(-1)?.[0] ?? {})).toEqual(["pointCount"]);
  });
});

/**
 * The macOS platform document. Every value is the published service shape
 * (`expert_validation/production_service/capabilities.py::_macos_capabilities`): the single-worker matrix rows
 * (the two-worker row is no longer startable, so it is not advertised), and a start guard that protects a start
 * rather than qualifying a host.
 */
const MACOS_START_GUARD_NOTE =
  "The StartGuard policy and status describe one bounded startup check only; they are not a "
  + "resource qualification proof and they do not certify macOS capacity.";

function matrixRow(
  profile: string,
  schema_version: number,
  execution_mode: "SEQUENTIAL",
  worker_count: number,
  batch_kind: "FIRST_PASS" | "FULL_RESTART_RETRY",
) {
  return {
    profile,
    schema_version,
    execution_mode,
    worker_count,
    batch_kind,
    accelerator: "mps",
    selector: "MPS:default",
    platform: "macos",
    selectable: true,
    status: "SUPPORTED",
    reason_codes: [] as string[],
    profile_sha256: null,
    qualification_sha256: null,
  };
}

const macosCapabilities = {
  available: true,
  platform: "macos",
  execution_modes: ["SEQUENTIAL"],
  default_execution_mode: "SEQUENTIAL",
  minimum_points: 4,
  maximum_points: 20,
  fixed_worker_counts: [1],
  worker_count_availability: [],
  support_matrix: [
    matrixRow("MPS_SINGLE_WORKER_FULL_RESTART_RETRY", 5, "SEQUENTIAL", 1, "FULL_RESTART_RETRY"),
    matrixRow("MPS_SINGLE_WORKER_FIRST_PASS", 6, "SEQUENTIAL", 1, "FIRST_PASS"),
  ],
  adaptive_default_ladder: [],
  worker_qualifications: [],
  lease_duration_s: 30,
  lease_renewal_margin_s: 10,
  start_guard_policy: {
    timeout_s: 2,
    cpu_busy_warn_fraction: 0.9,
    ram_minimum_bytes: 1 << 30,
    ram_minimum_fraction: 0.05,
    gpu_minimum_bytes: 1 << 30,
    mps_minimum_headroom_bytes: 1 << 30,
  },
  start_guard_note: MACOS_START_GUARD_NOTE,
} as never;

const macosBase = {
  capabilities: macosCapabilities,
  state: { pointCount: 4 },
  leaseHeld: true,
  manifestReady: true,
  onChange: () => undefined,
  onAcquireLease: () => undefined,
  onGenerate: () => undefined,
  onPreflight: () => undefined,
  onStart: () => undefined,
};

describe("macOS single-worker support matrix", () => {
  test("no mode or worker control is offered; the matrix single-worker row is the profile", () => {
    render(<CampaignSetup {...macosBase} />);
    expect(screen.queryByLabelText("Execution mode")).toBeNull();
    expect(screen.queryByLabelText("Worker count")).toBeNull();
    expect(screen.queryByLabelText("Unavailable worker counts")).toBeNull();
    expect(screen.getByLabelText("Execution profile").textContent).toContain("MPS_SINGLE_WORKER_FIRST_PASS");
    // The matrix carries no budget profile and no qualification hash, so none may be rendered.
    expect(document.body.textContent ?? "").not.toMatch(/[0-9a-f]{64}/);
  });

  test("the selected point count never selects the profile", () => {
    const { rerender } = render(<CampaignSetup {...macosBase} />);
    expect(screen.getByLabelText("Execution profile").textContent).toContain("MPS_SINGLE_WORKER_FIRST_PASS");
    rerender(<CampaignSetup {...macosBase} state={{ pointCount: 20 }} />);
    expect(screen.getByLabelText("Execution profile").textContent).toContain("MPS_SINGLE_WORKER_FIRST_PASS");

    // The claim is a pure function of the matrix row and the selection: no point count is an input.
    expect(executionClaim(macosCapabilities, SINGLE_WORKER))
      .toEqual({ execution_profile: "MPS_SINGLE_WORKER_FIRST_PASS", batch_kind: "FIRST_PASS" });
    expect(executionClaim(macosCapabilities, SINGLE_WORKER, "FULL_RESTART_RETRY"))
      .toEqual({ execution_profile: "MPS_SINGLE_WORKER_FULL_RESTART_RETRY", batch_kind: "FULL_RESTART_RETRY" });
    expect(executionClaim(macosCapabilities, { executionMode: "SEQUENTIAL", workerCount: 2 })).toBeNull();
    expect(executionClaim(macosCapabilities, { executionMode: "SEQUENTIAL", workerCount: 3 })).toBeNull();
  });

  test("a matrix without a first-pass single-worker row cannot preflight or start", () => {
    const retryOnly = {
      ...(macosCapabilities as object),
      support_matrix: [
        matrixRow("MPS_SINGLE_WORKER_FULL_RESTART_RETRY", 5, "SEQUENTIAL", 1, "FULL_RESTART_RETRY"),
      ],
    } as never;
    render(<CampaignSetup {...macosBase} capabilities={retryOnly} />);
    expect((screen.getByRole("button", { name: "Check resources" }) as HTMLButtonElement).disabled)
      .toBe(true);
    expect((screen.getByRole("button", { name: "Start validation" }) as HTMLButtonElement).disabled)
      .toBe(true);
    expect(screen.getByLabelText("Execution profile").textContent).toContain("UNSUPPORTED_ON_MACOS");
  });
});

describe("macOS start guard copy", () => {
  const ramFail = {
    status: "FAIL",
    checks: {
      cpu_busy: { status: "PASS", reason: "CPU_BUSY_OK", observed: 0.1, cutoff: 0.9, unit: "fraction" },
      ram: { status: "FAIL", reason: "RAM_BELOW_MINIMUM", observed: 0, cutoff: 1 << 30, unit: "bytes" },
      mps_headroom: { status: "FAIL", reason: "MPS_HEADROOM_BELOW_MINIMUM", observed: 0, cutoff: 1 << 30, unit: "bytes" },
    },
  } as never;
  const cpuWarn = {
    status: "WARN",
    checks: {
      cpu_busy: { status: "WARN", reason: "CPU_BUSY", observed: 0.95, cutoff: 0.9, unit: "fraction" },
      ram: { status: "PASS", reason: "RAM_OK", observed: 8 << 30, cutoff: 1 << 30, unit: "bytes" },
    },
  } as never;

  test("a RAM/MPS FAIL reads as a hard refusal and CPU busy reads as a warning", () => {
    const { rerender } = render(<CampaignSetup {...macosBase} startGuard={ramFail} />);
    const refusal = screen.getByLabelText("Start guard admission").textContent ?? "";
    expect(refusal).toContain("hard refusal");
    expect(refusal).toMatch(/RAM|MPS/);

    rerender(<CampaignSetup {...macosBase} startGuard={cpuWarn} />);
    const warning = screen.getByLabelText("Start guard admission").textContent ?? "";
    expect(warning).toContain("CPU busy");
    expect(warning).toContain("does not block");
    expect(warning).not.toContain("hard refusal");
  });

  test("the guard is shown as start protection, never as a qualification", () => {
    const { rerender } = render(<CampaignSetup {...macosBase} startGuard={cpuWarn} />);
    const scope = screen.getByLabelText("Start guard scope").textContent ?? "";
    expect(scope).toBe(MACOS_START_GUARD_NOTE);
    expect(scope).toContain("not a resource qualification proof");
    expect(START_GUARD_NOT_A_QUALIFICATION).toBe(MACOS_START_GUARD_NOTE);

    // A server that publishes no note still gets the same statement, never a green qualification.
    rerender(<CampaignSetup {...macosBase} capabilities={undefined} startGuard={cpuWarn} />);
    expect(screen.getByLabelText("Start guard scope").textContent)
      .toBe(START_GUARD_NOT_A_QUALIFICATION);
  });
});
