// @vitest-environment jsdom
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CaptureResponse } from "@/api/task-types";
import { LiveSensor } from "./live-sensor";

const capture: CaptureResponse = {
  capture_id: "capture-1",
  status: "SUCCEEDED",
  artifact_ids: ["rgb-png", "full-ply", "cup-ply", "preview-png", "summary-json"],
  source_stamp_ns: 123456789,
  summary: { source_frame_id: "task_camera_frame" },
  artifacts: [
    { artifact_id: "rgb-png", name: "rgb.png", media_type: "image/png", byte_size: 8, sha256: "a".repeat(64) },
    { artifact_id: "full-ply", name: "full-cloud.ply", media_type: "application/octet-stream", byte_size: 16, sha256: "b".repeat(64) },
    { artifact_id: "cup-ply", name: "cup-cloud.ply", media_type: "application/octet-stream", byte_size: 12, sha256: "c".repeat(64) },
    { artifact_id: "preview-png", name: "point-cloud-preview.png", media_type: "image/png", byte_size: 24, sha256: "d".repeat(64) },
    { artifact_id: "summary-json", name: "summary.json", media_type: "application/json", byte_size: 32, sha256: "e".repeat(64) },
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

  it("shows every manifest-registered capture artifact with integrity metadata", async () => {
    const api = {
      capture: vi.fn(async () => capture),
      artifactUrl: vi.fn((id: string) => `/tasks/artifacts/${id}`),
    };
    const user = userEvent.setup();
    render(<LiveSensor api={api} lease="lease-a" sessionId="sim-a" viewerComponent={() => null} />);
    await user.click(screen.getByRole("button", { name: "Capture now" }));

    const panel = await screen.findByRole("region", { name: "Capture artifacts" });
    expect(within(panel).getByText("5 registered artifacts")).toBeTruthy();
    expect(within(panel).getByRole("link", { name: "RGB PNG" }).getAttribute("href")).toBe("/tasks/artifacts/rgb-png");
    expect(within(panel).getByRole("link", { name: "Full PLY" }).getAttribute("href")).toBe("/tasks/artifacts/full-ply");
    expect(within(panel).getByRole("link", { name: "Cup PLY" }).getAttribute("href")).toBe("/tasks/artifacts/cup-ply");
    expect(within(panel).getByRole("link", { name: "Point-cloud screenshot" }).getAttribute("href")).toBe("/tasks/artifacts/preview-png");
    expect(within(panel).getByRole("link", { name: "JSON evidence" }).getAttribute("href")).toBe("/tasks/artifacts/summary-json");
    expect(within(panel).getByText("full-cloud.ply · 16 B")).toBeTruthy();
    expect(within(panel).getByTitle("b".repeat(64)).textContent).toBe(`sha256 ${"b".repeat(64)}`);
  });

  it("requires both lease and session before capture", () => {
    const api = { capture: vi.fn(), artifactUrl: vi.fn() };
    render(<LiveSensor api={api} lease="" sessionId="sim-a" viewerComponent={() => null} />);
    expect((screen.getByRole("button", { name: "Capture now" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
