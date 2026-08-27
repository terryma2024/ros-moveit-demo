// @vitest-environment jsdom
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { CaptureResponse } from "@/api/task-types";
import { PointCloudViewer } from "./point-cloud-viewer";

const capture: CaptureResponse = {
  capture_id: "capture-1",
  status: "SUCCEEDED",
  artifact_ids: ["rgb-png", "full-ply", "cup-ply"],
  source_stamp_ns: 123456789,
  summary: { cup_center_xyz: [0.01, 0.02, 0.03] },
  artifacts: [
    { artifact_id: "rgb-png", name: "rgb.png", media_type: "image/png", byte_size: 8, sha256: "a".repeat(64) },
    { artifact_id: "full-ply", name: "full-cloud.ply", media_type: "application/octet-stream", byte_size: 16, sha256: "b".repeat(64) },
    { artifact_id: "cup-ply", name: "cup-cloud.ply", media_type: "application/octet-stream", byte_size: 12, sha256: "c".repeat(64) },
  ],
};

function fixture() {
  const renderer = {
    load: vi.fn(async () => ({
      original_point_count: 500001,
      displayed_point_count: 250001,
      sampling_rule: "fixed-stride" as const,
      sampling_stride: 2,
    })),
    setPointSize: vi.fn(),
    setColorMode: vi.fn(),
    resetView: vi.fn(),
    snapshot: vi.fn(async () => ({
      blob: new Blob(["png"], { type: "image/png" }),
      view_matrix: Array(16).fill(1),
      projection_matrix: Array(16).fill(2),
      viewport_px: [640, 480] as [number, number],
    })),
    dispose: vi.fn(),
  };
  const api = {
    fetchArtifact: vi.fn(async () => new ArrayBuffer(8)),
    uploadRenderedImage: vi.fn(async () => ({ artifact_id: "view-png" })),
  };
  return { renderer, api };
}

describe("PointCloudViewer", () => {
  it("loads full and cup PLY and saves the current rendered view", async () => {
    const { renderer, api } = fixture();
    const user = userEvent.setup();
    render(<PointCloudViewer capture={capture} api={api} rendererFactory={() => renderer} />);
    await waitFor(() => expect(api.fetchArtifact).toHaveBeenCalledWith("full-ply"));
    await user.selectOptions(screen.getByLabelText("Point cloud"), "cup");
    await waitFor(() => expect(api.fetchArtifact).toHaveBeenCalledWith("cup-ply"));
    await user.click(screen.getByRole("button", { name: "Save point-cloud screenshot" }));
    expect(api.uploadRenderedImage).toHaveBeenCalledWith(
      "capture-1",
      expect.any(Blob),
      expect.objectContaining({
        source_artifact_id: "cup-ply",
        source_sha256: "c".repeat(64),
        color_mode: "rgb",
        sampling_rule: "fixed-stride",
        sampling_stride: 2,
      }),
    );
  });

  it("disposes renderer resources on unmount", async () => {
    const { renderer, api } = fixture();
    const view = render(<PointCloudViewer capture={capture} api={api} rendererFactory={() => renderer} />);
    await waitFor(() => expect(renderer.load).toHaveBeenCalled());
    view.unmount();
    expect(renderer.dispose).toHaveBeenCalledOnce();
  });
});
