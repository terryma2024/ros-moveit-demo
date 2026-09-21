// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { CampaignProgress } from "./campaign-progress";
import {
  CampaignSetup,
  START_GUARD_NOT_A_QUALIFICATION,
  executionClaim,
} from "./campaign-setup";
import { PointEvidence } from "./point-evidence";
import { RetryPanel } from "./retry-panel";

const campaign = {
  campaign_id: "campaign-1", sequence: 9, execution_mode: "PARALLEL" as const,
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
    state: { pointCount: 4, executionMode: "PARALLEL" as const, workerCount: 4 },
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

describe("CampaignSetup exact-N qualification", () => {
  const base = {
    state: { pointCount: 4, executionMode: "PARALLEL" as const, workerCount: 4 },
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
    execution_modes: ["SEQUENTIAL", "PARALLEL"] as const,
    default_execution_mode: "PARALLEL" as const,
    minimum_points: 4,
    maximum_points: 20,
    fixed_worker_counts: [1, 2, 3, 4, 5, 6, 7, 8],
    worker_count_availability: [
      { worker_count: 4, selectable: true, status: "APPROVED", reason_codes: [] },
    ],
    adaptive_default_ladder: [2, 4, 8],
  } as never;

  test("an unknown exact N is disabled and shows the provider reason", () => {
    render(
      <CampaignSetup
        {...base}
        capabilities={capabilities}
        qualifications={[
          {
            selected_n: 4,
            status: "UNKNOWN",
            reasons: ["BUDGET_PROVIDER_NOT_READY"],
            runtime_identity: "R",
            contract_version: 2,
            profile_sha256: null,
            approval_sha256: null,
          },
        ]}
      />,
    );
    const select = screen.getByLabelText("Worker count") as HTMLSelectElement;
    const four = Array.from(select.options).find((option) => option.value === "4");
    expect(four?.disabled).toBe(true);
    expect(screen.getByText(/BUDGET_PROVIDER_NOT_READY/)).toBeTruthy();
  });

  test("an available promoted N stays selectable and there is no K input", () => {
    render(
      <CampaignSetup
        {...base}
        capabilities={capabilities}
        qualifications={[
          {
            selected_n: 4,
            status: "AVAILABLE",
            reasons: [],
            runtime_identity: "R",
            contract_version: 2,
            profile_sha256: "profile",
            approval_sha256: "approval",
          },
        ]}
      />,
    );
    const select = screen.getByLabelText("Worker count") as HTMLSelectElement;
    const four = Array.from(select.options).find((option) => option.value === "4");
    expect(four?.disabled).toBe(false);
    expect(screen.queryByLabelText(/max points per worker/i)).toBeNull();
  });
});

/**
 * The macOS platform document. Every value is the published service shape
 * (`expert_validation/production.py::_macos_capabilities`): three matrix rows, fixed W1/W2, and a
 * start guard that protects a start rather than qualifying a host.
 */
const MACOS_START_GUARD_NOTE =
  "The StartGuard policy and status describe one bounded startup check only; they are not a "
  + "resource qualification proof and they do not certify macOS capacity.";

function matrixRow(
  profile: string,
  schema_version: number,
  execution_mode: "SEQUENTIAL" | "PARALLEL",
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
  execution_modes: ["SEQUENTIAL", "PARALLEL"],
  default_execution_mode: "PARALLEL",
  minimum_points: 4,
  maximum_points: 20,
  fixed_worker_counts: [1, 2, 3, 4, 5, 6, 7, 8],
  worker_count_availability: [
    { worker_count: 1, selectable: true, status: "SUPPORTED", reason_codes: [], profile_sha256: null, qualification_sha256: null },
    { worker_count: 2, selectable: true, status: "SUPPORTED", reason_codes: [], profile_sha256: null, qualification_sha256: null },
    ...[3, 4, 5, 6, 7, 8].map((worker_count) => ({
      worker_count,
      selectable: false,
      status: "UNSUPPORTED_ON_MACOS",
      reason_codes: ["UNSUPPORTED_ON_MACOS"],
      profile_sha256: null,
      qualification_sha256: null,
    })),
  ],
  support_matrix: [
    matrixRow("MPS_W2_FIRST_PASS", 4, "PARALLEL", 2, "FIRST_PASS"),
    matrixRow("MPS_W1_FULL_RESTART_RETRY", 5, "SEQUENTIAL", 1, "FULL_RESTART_RETRY"),
    matrixRow("MPS_W1_FIRST_PASS", 6, "SEQUENTIAL", 1, "FIRST_PASS"),
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
  state: { pointCount: 4, executionMode: "SEQUENTIAL" as const, workerCount: 1 },
  leaseHeld: true,
  manifestReady: true,
  onChange: () => undefined,
  onAcquireLease: () => undefined,
  onGenerate: () => undefined,
  onPreflight: () => undefined,
  onStart: () => undefined,
};

function workerOptionByValue(count: number): HTMLOptionElement {
  const select = screen.getByLabelText("Worker count") as HTMLSelectElement;
  const option = Array.from(select.options).find((entry) => entry.value === String(count));
  if (!option) throw new Error(`worker option N${count} is missing`);
  return option;
}

describe("macOS W1/W2 support matrix", () => {
  test("only the matrix profiles are offered as execution modes", () => {
    render(<CampaignSetup {...macosBase} />);
    const modes = screen.getByLabelText("Execution mode") as HTMLSelectElement;
    expect(Array.from(modes.options).map((option) => option.value))
      .toEqual(["SEQUENTIAL", "PARALLEL"]);
    expect(Array.from(modes.options).map((option) => option.value)).not.toContain("ADAPTIVE");
    expect(screen.getByLabelText("Execution profile").textContent).toContain("MPS_W1_FIRST_PASS");
  });

  test("N3 to N8 are unavailable with the macOS reason and no profile or qualification hash", () => {
    render(<CampaignSetup {...macosBase} state={{ ...macosBase.state, executionMode: "PARALLEL", workerCount: 2 }} />);
    expect(workerOptionByValue(2).disabled).toBe(false);
    for (const count of [3, 4, 5, 6, 7, 8]) {
      const option = workerOptionByValue(count);
      expect(option.disabled, `N${count} must be disabled`).toBe(true);
      expect(option.text, `N${count} reason`).toContain("UNSUPPORTED_ON_MACOS");
      expect(screen.getByText(`N${count} unavailable · UNSUPPORTED_ON_MACOS`)).toBeTruthy();
    }
    // The matrix carries no budget profile and no qualification hash, so none may be rendered.
    expect(document.body.textContent ?? "").not.toMatch(/[0-9a-f]{64}/);
  });

  test("a qualification view can neither enable nor disable the macOS selection", () => {
    render(
      <CampaignSetup
        {...macosBase}
        state={{ ...macosBase.state, executionMode: "PARALLEL", workerCount: 2 }}
        qualifications={[
          {
            selected_n: 2,
            status: "UNKNOWN",
            reasons: ["BUDGET_PROVIDER_NOT_READY"],
            runtime_identity: "test-runtime",
            contract_version: 2,
            profile_sha256: null,
            approval_sha256: null,
          },
          {
            selected_n: 8,
            status: "AVAILABLE",
            reasons: [],
            runtime_identity: "test-runtime",
            contract_version: 2,
            profile_sha256: "f".repeat(64),
            approval_sha256: "e".repeat(64),
          },
        ]}
      />,
    );
    // N2 stays selectable because the matrix supports it, not because a provider approved it.
    expect(workerOptionByValue(2).disabled).toBe(false);
    // And a promoted N8 stays unselectable: on macOS the matrix, not a qualification, decides.
    expect(workerOptionByValue(8).disabled).toBe(true);
    expect(workerOptionByValue(8).text).toContain("UNSUPPORTED_ON_MACOS");
    expect(screen.queryByText(/BUDGET_PROVIDER_NOT_READY/)).toBeNull();
    expect(document.body.textContent ?? "").not.toContain("f".repeat(64));
    expect(document.body.textContent ?? "").not.toContain("e".repeat(64));
  });

  test("the selected point count never selects the profile and W2 is the exact-W2 path", () => {
    const { rerender } = render(<CampaignSetup {...macosBase} />);
    expect(screen.getByLabelText("Execution profile").textContent).toContain("MPS_W1_FIRST_PASS");
    rerender(<CampaignSetup {...macosBase} state={{ ...macosBase.state, pointCount: 20 }} />);
    expect(screen.getByLabelText("Execution profile").textContent).toContain("MPS_W1_FIRST_PASS");
    rerender(
      <CampaignSetup
        {...macosBase}
        state={{ ...macosBase.state, pointCount: 20, executionMode: "PARALLEL", workerCount: 2 }}
      />,
    );
    expect(screen.getByLabelText("Execution profile").textContent).toContain("MPS_W2_FIRST_PASS");
    rerender(
      <CampaignSetup
        {...macosBase}
        state={{ ...macosBase.state, pointCount: 4, executionMode: "PARALLEL", workerCount: 2 }}
      />,
    );
    expect(screen.getByLabelText("Execution profile").textContent).toContain("MPS_W2_FIRST_PASS");

    // The claim is a pure function of the matrix row and the selection: no point count is an input.
    expect(executionClaim(macosCapabilities, { executionMode: "SEQUENTIAL", workerCount: 1 }))
      .toEqual({ execution_profile: "MPS_W1_FIRST_PASS", batch_kind: "FIRST_PASS" });
    expect(executionClaim(macosCapabilities, { executionMode: "PARALLEL", workerCount: 2 }))
      .toEqual({ execution_profile: "MPS_W2_FIRST_PASS", batch_kind: "FIRST_PASS" });
    expect(executionClaim(macosCapabilities, { executionMode: "PARALLEL", workerCount: 8 })).toBeNull();
    expect(executionClaim(macosCapabilities, { executionMode: "SEQUENTIAL", workerCount: 3 })).toBeNull();
  });

  test("an N outside the matrix cannot preflight or start", () => {
    render(
      <CampaignSetup
        {...macosBase}
        state={{ ...macosBase.state, executionMode: "PARALLEL", workerCount: 3 }}
      />,
    );
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
