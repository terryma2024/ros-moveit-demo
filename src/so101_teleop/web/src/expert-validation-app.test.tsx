// @vitest-environment jsdom
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { ExpertValidationApp, type ExpertValidationApi } from "./expert-validation-app";
import type { Lease } from "@/api/expert-validation-types";

function fakeApi(overrides: Partial<ExpertValidationApi> = {}): ExpertValidationApi {
  return {
    async capabilities() {
      return {
        available: true,
        execution_modes: ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"],
        default_execution_mode: "SEQUENTIAL",
        minimum_points: 4,
        maximum_points: 20,
        fixed_worker_counts: [1, 2, 3],
        fixed_max_points_per_worker: 20,
        adaptive_default_ladder: [8, 6, 4, 2, 1],
        lease_duration_s: 30,
        lease_renewal_margin_s: 10,
      };
    },
    async acquireLease(serviceSessionId) {
      return {
        lease_id: "lease-a",
        service_session_id: serviceSessionId,
        generation: 1,
        expires_monotonic_ns: 10_000,
      };
    },
    async renewLease(current) {
      return { ...current, generation: current.generation + 1, expires_monotonic_ns: current.expires_monotonic_ns + 30_000_000_000 };
    },
    async createManifest(totalPoints) {
      return {
        manifest_id: `manifest-${totalPoints}`,
        point_count: totalPoints,
        stale: false,
        points: [],
      };
    },
    async preflight(input) {
      return {
        receipt_id: "receipt-1",
        admitted: true,
        manifest_id: input.manifest_id,
        execution_mode: input.execution_mode,
        execution_config: input,
        resource_observations: { memory_pressure: "LOW" },
        reason_codes: [],
      };
    },
    async startCampaign() {
      return {
        campaign_id: "campaign-1",
        sequence: 1,
        execution_mode: "SEQUENTIAL",
        batch_cleanup_complete: false,
        points: [], workers: [], requested: 4, evaluated: 0, execution_started: 0,
        valid_succeeded: 0, valid_failed: 0, indeterminate: 0, not_executed: 4,
        evaluation_coverage: 0, execution_coverage: 0, levels_used: [],
        fallback_history: [], infra_attempts: 0, resource_observations: {},
      };
    },
    async retry() { throw new Error("not expected"); },
    ...overrides,
  };
}

describe("ExpertValidationApp", () => {
  test("selecting a committed point renders its typed sealed evidence rather than empty placeholders", async () => {
    const user = userEvent.setup();
    const image = {
      artifact_id: "opaque-rgb-a", campaign_id: "campaign-1", batch_id: "batch-1",
      worker_id: "worker-01", worker_generation: 2, attempt_id: "attempt-a",
      role: "task-rgb-before", media_type: "image/png", size_bytes: 68, sha256: "a".repeat(64),
    };
    const numeric = { ...image, artifact_id: "opaque-physical-a", role: "physical-evidence", media_type: "application/json" };
    render(<ExpertValidationApp api={fakeApi({ restoreCampaign: async () => ({
      campaign_id: "campaign-1", sequence: 9, status: "COMPLETED",
      points: [{ point_id: "task_start", display_id: "P01", status: "PASSED",
        retry_eligible: false, attempts: [], artifact_ids: [image.artifact_id, numeric.artifact_id],
        artifacts: [image, numeric] }],
    }) })} />);
    await user.click(await screen.findByRole("button", { name: "P01 PASSED" }));
    expect((screen.getByAltText("task-rgb-before") as HTMLImageElement).src)
      .toContain("/expert-validation/artifacts/opaque-rgb-a");
    expect((screen.getByRole("link", { name: "Download physical-evidence" }) as HTMLAnchorElement).href)
      .toContain("/expert-validation/artifacts/opaque-physical-a");
    expect(screen.queryByText(/No committed evidence/)).toBeNull();
  });

  test("renewal at the server margin replaces stale preflight authority before start", async () => {
    vi.useFakeTimers();
    try {
      const base = fakeApi();
      const preflight = vi.fn(base.preflight);
      const startCampaign = vi.fn(base.startCampaign);
      const renewLease = vi.fn(async (current: Lease) => ({ ...current, generation: current.generation + 1, expires_monotonic_ns: current.expires_monotonic_ns + 30_000_000_000 }));
      const api = { ...base, preflight, startCampaign, renewLease };
      const { unmount } = render(<ExpertValidationApp api={api} />);
      await act(async () => {});
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Acquire lease" })); });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Generate points" })); });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Check resources" })); });
      expect(preflight.mock.calls[0][1]).toMatchObject({ lease_generation: 1 });

      await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Start validation" })); });

      expect(startCampaign.mock.calls[0][1]).toMatchObject({ lease_generation: 2 });
      expect(preflight.mock.calls).toHaveLength(2);
      expect(preflight.mock.calls[1][1]).toMatchObject({ lease_generation: 2 });
      unmount();
      await vi.advanceTimersByTimeAsync(60_000);
      expect(renewLease).toHaveBeenCalledOnce();
    } finally {
      vi.useRealTimers();
    }
  });

  test("failed renewal disables execution and allows a fresh lease request", async () => {
    vi.useFakeTimers();
    try {
      const api = { ...fakeApi(), renewLease: async () => { throw new Error("LEASE_EXPIRED"); } };
      render(<ExpertValidationApp api={api} />);
      await act(async () => {});
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Acquire lease" })); });
      await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Generate points" })); });
      await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });

      expect((screen.getByRole("button", { name: "Start validation" }) as HTMLButtonElement).disabled).toBe(true);
      expect((screen.getByRole("button", { name: "Acquire lease" }) as HTMLButtonElement).disabled).toBe(false);
      expect(screen.getByText(/LEASE_EXPIRED/)).toBeTruthy();
    } finally {
      vi.useRealTimers();
    }
  });

  test("newly started campaign begins watching and unmount stops it", async () => {
    const user = userEvent.setup();
    const stop = vi.fn();
    const watchCampaign = vi.fn(() => stop);
    const { unmount } = render(
      <ExpertValidationApp api={fakeApi({ watchCampaign })} />,
    );
    await user.click(await screen.findByRole("button", { name: "Acquire lease" }));
    await user.click(screen.getByRole("button", { name: "Generate points" }));
    await user.click(screen.getByRole("button", { name: "Start validation" }));

    expect(watchCampaign).toHaveBeenCalledWith("campaign-1", 1, expect.any(Function));
    unmount();
    expect(stop).toHaveBeenCalledOnce();
  });

  test("changing count invalidates generated preview", async () => {
    const user = userEvent.setup();
    render(<ExpertValidationApp api={fakeApi()} />);
    await user.click(await screen.findByRole("button", { name: "Acquire lease" }));
    await user.click(screen.getByRole("button", { name: "Generate points" }));
    const start = screen.getByRole("button", { name: "Start validation" }) as HTMLButtonElement;
    expect(start.disabled).toBe(false);
    const count = screen.getByLabelText("Final point count");
    await user.clear(count);
    await user.type(count, "12");
    expect(start.disabled).toBe(true);
  });

  test("parallel setup shows capacity admission and worker lanes", async () => {
    const user = userEvent.setup();
    const campaign = {
      campaign_id: "campaign-1", sequence: 3, execution_mode: "PARALLEL" as const,
      batch_cleanup_complete: false, points: [],
      workers: [
        { worker_id: "worker-1", generation: 1, state: "EXECUTING", lease_count: 1 },
        { worker_id: "worker-2", generation: 1, state: "EXECUTING", lease_count: 1 },
      ],
      requested: 20, evaluated: 2, execution_started: 2, valid_succeeded: 0,
      valid_failed: 0, indeterminate: 0, not_executed: 18,
      evaluation_coverage: 0.1, execution_coverage: 0.1, levels_used: [],
      fallback_history: [], infra_attempts: 0, resource_observations: {},
    };
    render(<ExpertValidationApp api={fakeApi({ restoreCampaign: async () => campaign })} />);
    await user.selectOptions(await screen.findByLabelText("Execution mode"), "PARALLEL");
    await user.selectOptions(screen.getByLabelText("Worker count"), "2");
    expect(screen.getByText("Capacity 20 / 20")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Acquire lease" }));
    await user.click(screen.getByRole("button", { name: "Generate points" }));
    await user.click(screen.getByRole("button", { name: "Check resources" }));
    expect(await screen.findByText("Parallel admission passed")).toBeTruthy();
    expect(screen.getByLabelText("Worker worker-1")).toBeTruthy();
    expect(screen.getByLabelText("Worker worker-2")).toBeTruthy();
  });

  test("adaptive setup shows fallback timeline and observational resources", async () => {
    const user = userEvent.setup();
    const campaign = {
      campaign_id: "campaign-1", sequence: 8, execution_mode: "ADAPTIVE" as const,
      status: "RUNNING", batch_cleanup_complete: false, points: [], workers: [],
      requested: 20, evaluated: 5, execution_started: 5, valid_succeeded: 4,
      valid_failed: 0, indeterminate: 1, not_executed: 15,
      evaluation_coverage: 0.25, execution_coverage: 0.25,
      levels_used: [8, 6],
      fallback_history: [{ from_count: 8, to_count: 6, reason: "WORKER_START_FAILED" }],
      infra_attempts: 1, resource_observations: { memory_pressure: "HIGH" },
    };
    render(<ExpertValidationApp api={fakeApi({ restoreCampaign: async () => campaign })} />);
    await user.selectOptions(await screen.findByLabelText("Execution mode"), "ADAPTIVE");
    expect(screen.queryByLabelText("Max points per worker")).toBeNull();
    expect(screen.getByText("W8 -> W6 -> W4 -> W2 -> W1")).toBeTruthy();
    expect(screen.getByText("Resource observations only")).toBeTruthy();
    expect(await screen.findByText("W8 -> W6: WORKER_START_FAILED")).toBeTruthy();
  });
});
