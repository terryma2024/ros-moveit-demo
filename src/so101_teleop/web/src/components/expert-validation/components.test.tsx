// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { CampaignProgress } from "./campaign-progress";
import { CampaignSetup } from "./campaign-setup";
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
