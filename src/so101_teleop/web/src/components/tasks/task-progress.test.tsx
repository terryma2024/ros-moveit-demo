// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TaskRunSummary } from "@/api/task-types";
import { TaskProgress } from "./task-progress";

const run: TaskRunSummary = {
  run_id: "run-1",
  status: "FAILED",
  simulation_session_id: "sim-a",
  first_shared_failure: null,
  points: [
    { id: "first", status: "FAILED", failure_code: "PERCEPTION_TIMEOUT", reachability_status: "REACHABLE", reset_epoch: 8, artifact_ids: [], artifacts: [] },
    { id: "second", status: "SUCCEEDED", failure_code: null, reachability_status: "REACHABLE", reset_epoch: 9, artifact_ids: [], artifacts: [] },
  ],
};

describe("TaskProgress", () => {
  it("restores terminal point ordering including failure followed by success", () => {
    render(<TaskProgress run={run} currentPhase="POINT_FINISHED" />);
    expect(screen.getByText("first — FAILED")).toBeTruthy();
    expect(screen.getByText("second — SUCCEEDED")).toBeTruthy();
    expect(screen.getByText("PERCEPTION_TIMEOUT")).toBeTruthy();
    expect(screen.getByText("reset epoch 9")).toBeTruthy();
  });
});
