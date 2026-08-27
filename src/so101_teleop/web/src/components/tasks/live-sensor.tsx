import { useState, type ComponentType } from "react";

import type { CommandResult } from "@/api/types";
import type {
  CaptureResponse,
  RenderedPointCloudMetadata,
} from "@/api/task-types";
import { isCommandFailure } from "@/api/task-types";
import { artifactLabel } from "@/components/tasks/evidence-browser";
import { PointCloudViewer, type PointCloudViewerApi } from "@/components/tasks/point-cloud-viewer";
import { Button } from "@/components/ui/button";

type LiveSensorApi = {
  capture(sessionId: string, leaseId: string): Promise<CaptureResponse | CommandResult>;
  artifactUrl(artifactId: string): string;
  fetchArtifact?(artifactId: string): Promise<ArrayBuffer>;
  uploadRenderedImage?(
    captureId: string,
    png: Blob,
    metadata: RenderedPointCloudMetadata,
    sessionId: string,
    leaseId: string,
  ): Promise<unknown>;
};

type ViewerProps = { capture: CaptureResponse; api: PointCloudViewerApi };

export function LiveSensor({
  api,
  lease,
  sessionId,
  viewerComponent: Viewer = PointCloudViewer,
}: {
  api: LiveSensorApi;
  lease: string;
  sessionId: string;
  viewerComponent?: ComponentType<ViewerProps>;
}) {
  const [capture, setCapture] = useState<CaptureResponse>();
  const [status, setStatus] = useState("Capture RGB-D only when the current simulation lease is held.");
  const [busy, setBusy] = useState(false);
  const rgb = capture?.artifacts.find((artifact) => artifact.name === "rgb.png");
  const viewerApi: PointCloudViewerApi | undefined = api.fetchArtifact && api.uploadRenderedImage ? {
    fetchArtifact: (artifactId) => api.fetchArtifact!(artifactId),
    artifactUrl: (artifactId) => api.artifactUrl(artifactId),
    uploadRenderedImage: (captureId, png, metadata) => api.uploadRenderedImage!(
      captureId, png, metadata, sessionId, lease,
    ),
  } : undefined;

  const captureNow = async () => {
    if (!lease || !sessionId) return;
    setBusy(true);
    setStatus("Capturing synchronized RGB-D and point clouds…");
    try {
      const result = await api.capture(sessionId, lease);
      if (isCommandFailure(result)) {
        setStatus(`${result.code}: ${result.message ?? "capture failed"}`);
      } else {
        setCapture(result);
        setStatus(`Capture ${result.capture_id}: ${result.status}`);
      }
    } catch (error) {
      setStatus(`Capture failed: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  };

  return <div className="space-y-4">
    <div className="flex flex-wrap items-center gap-3">
      <Button type="button" disabled={!lease || !sessionId || busy} onClick={captureNow}>Capture now</Button>
      <p aria-live="polite" className="text-sm text-slate-400">{status}</p>
    </div>
    {capture && <>
      <div className="grid gap-3 lg:grid-cols-[minmax(280px,0.75fr)_1fr]">
        <div className="space-y-2">
          {rgb && <img className="w-full rounded border border-slate-700" src={api.artifactUrl(rgb.artifact_id)} alt="Current RGB camera frame" />}
          <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded bg-slate-950 p-3 text-xs">
            <dt className="text-slate-500">Timestamp</dt><dd>source stamp {capture.source_stamp_ns ?? "unavailable"}</dd>
            <dt className="text-slate-500">Source frame</dt><dd>{String(capture.summary.source_frame_id ?? "unavailable")}</dd>
            <dt className="text-slate-500">Output frame</dt><dd>{String(capture.summary.output_frame_id ?? "unavailable")}</dd>
            <dt className="text-slate-500">Full points</dt><dd>{String(capture.summary.full_point_count ?? "unavailable")}</dd>
            <dt className="text-slate-500">Cup points</dt><dd>{String(capture.summary.cup_point_count ?? "unavailable")}</dd>
          </dl>
        </div>
        <section aria-label="Capture artifacts" className="rounded border border-slate-700 p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <strong className="text-sm text-slate-200">Capture artifacts</strong>
            <span className="text-xs text-slate-400">{capture.artifacts.length} registered artifacts</span>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            Manifest-registered files from capture <strong className="text-slate-300">{capture.capture_id}</strong>.
          </p>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2">
            {capture.artifacts.map((artifact) => <li key={artifact.artifact_id} className="min-w-0 rounded bg-slate-950 p-2 text-xs">
              <a className="font-medium text-cyan-400 underline" href={api.artifactUrl(artifact.artifact_id)} download>{artifactLabel(artifact)}</a>
              <div className="mt-1 truncate text-slate-500" title={`${artifact.name} · ${artifact.byte_size.toLocaleString()} B`}>
                {artifact.name} · {artifact.byte_size.toLocaleString()} B
              </div>
              <div className="truncate text-slate-600" title={artifact.sha256}>sha256 {artifact.sha256}</div>
            </li>)}
          </ul>
        </section>
      </div>
      {viewerApi && <Viewer capture={capture} api={viewerApi} />}
    </>}
  </div>;
}
