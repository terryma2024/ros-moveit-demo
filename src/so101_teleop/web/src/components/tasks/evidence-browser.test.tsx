// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { TaskRunSummary } from "@/api/task-types";
import { EvidenceBrowser } from "./evidence-browser";

const run: TaskRunSummary = {
  run_id: "run-1",
  status: "FAILED",
  simulation_session_id: "sim-a",
  points: [{
    id: "first",
    status: "FAILED",
    artifact_ids: ["rgb-id", "ply-id", "log-id"],
    artifacts: [
      { artifact_id: "rgb-id", name: "rgb.png", media_type: "image/png", byte_size: 8, sha256: "a".repeat(64) },
      { artifact_id: "ply-id", name: "full-cloud.ply", media_type: "application/octet-stream", byte_size: 16, sha256: "b".repeat(64) },
      { artifact_id: "log-id", name: "workflow.log", media_type: "text/plain", byte_size: 12, sha256: "c".repeat(64) },
    ],
  }],
};

describe("EvidenceBrowser", () => {
  it("renders registered artifact URLs without filesystem paths", () => {
    render(<EvidenceBrowser run={run} artifactUrl={(id) => `/tasks/artifacts/${id}`} />);
    expect(screen.getByRole("link", { name: "RGB PNG" }).getAttribute("href")).toBe("/tasks/artifacts/rgb-id");
    expect(screen.getByRole("link", { name: "Full PLY" }).getAttribute("href")).toBe("/tasks/artifacts/ply-id");
    expect(screen.queryByText(/\/tmp\//)).toBeNull();
  });
});
