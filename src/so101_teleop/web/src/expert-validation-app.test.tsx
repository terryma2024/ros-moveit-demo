// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

import { ExpertValidationApp, type ExpertValidationApi } from "./expert-validation-app";

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
