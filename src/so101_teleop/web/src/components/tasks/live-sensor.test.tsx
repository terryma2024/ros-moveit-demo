// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CaptureResponse } from "@/api/task-types";
import { LiveSensor } from "./live-sensor";

const capture: CaptureResponse = {
  capture_id: "capture-1",
  status: "SUCCEEDED",
  artifact_ids: ["rgb-png", "full-ply"],
  source_stamp_ns: 123456789,
  summary: { source_frame_id: "task_camera_frame" },
  artifacts: [
    { artifact_id: "rgb-png", name: "rgb.png", media_type: "image/png", byte_size: 8, sha256: "a".repeat(64) },
    { artifact_id: "full-ply", name: "full-cloud.ply", media_type: "application/octet-stream", byte_size: 16, sha256: "b".repeat(64) },
  ],
};

describe("LiveSensor", () => {
  it("Capture now displays artifacts sharing one source stamp", async () => {
    const api = {
      capture: vi.fn(async () => capture),
      artifactUrl: vi.fn((id: string) => `/tasks/artifacts/${id}`),
    };
    const user = userEvent.setup();
    render(<LiveSensor api={api} lease="lease-a" sessionId="sim-a" viewerComponent={() => <div>viewer</div>} />);
    await user.click(screen.getByRole("button", { name: "Capture now" }));
    expect(await screen.findByAltText("Current RGB camera frame")).toBeTruthy();
    expect(screen.getByText("source stamp 123456789")).toBeTruthy();
    expect(api.artifactUrl).toHaveBeenCalledWith("rgb-png");
  });

  it("requires both lease and session before capture", () => {
    const api = { capture: vi.fn(), artifactUrl: vi.fn() };
    render(<LiveSensor api={api} lease="" sessionId="sim-a" viewerComponent={() => null} />);
    expect((screen.getByRole("button", { name: "Capture now" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
