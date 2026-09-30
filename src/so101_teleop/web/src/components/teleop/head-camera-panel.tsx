import { useEffect, useState } from "react";

import type { HeadCameraClient } from "@/api/head-camera-client";

export interface HeadCameraDetection {
  class_id: number;
  class_name: string;
  confidence: number;
  track_id: string;
  xyxy: [number, number, number, number];
  mask_sha256: string;
}

export interface HeadCameraFrame {
  sequence: number;
  jpeg_sha256: string;
  detections: HeadCameraDetection[];
  model_id: string;
  bundle_sha256: string;
}

export interface HeadCameraStatus {
  available: boolean;
  operation: string;
  runtime_id: string;
  model_id: string;
  state: string;
  detector_constructed: number;
  qualified: boolean;
  authority: boolean;
  safe_interval_rad: [number, number];
}

export interface HeadCameraPanelProps {
  status: HeadCameraStatus | null;
  frame?: HeadCameraFrame | null;
  lockProgress?: number;
  lockRequired?: number;
  onExecute?: (targetRad: number) => void;
  onStop?: () => void;
  onCapture?: () => void;
}

const LOCK_REQUIRED = 3;

function stateLabel(state: string): string {
  if (state === "STOPPING") return "Stopping";
  if (state === "STOPPED") return "Stopped";
  return "Ready";
}

/**
 * The Teleop Head Camera view. It reads the composed domain's status and frames and can only ask the
 * backend for a bounded target, a stop or a capture: it holds no threshold, switches no model, and reports
 * the detector count it was told rather than implying one of its own.
 */
export function HeadCameraPanel({
  status,
  frame = null,
  lockProgress = 1,
  lockRequired = LOCK_REQUIRED,
  onExecute,
  onStop,
  onCapture,
}: HeadCameraPanelProps) {
  const [target, setTarget] = useState(0);

  if (status === null || !status.available) {
    return (
      <section aria-label="Head camera">
        <h2>Head Camera</h2>
        <p>Head camera unavailable</p>
      </section>
    );
  }

  const [low, high] = status.safe_interval_rad;
  const controllable = status.qualified && status.authority;
  const detection = frame?.detections?.[0] ?? null;
  // the interval is the sealed one, and a value from anywhere is clamped into it
  const bounded = Math.min(Math.max(target, low), high);
  const deadbandPx = (status as HeadCameraStatus & { center_deadband_px?: number }).center_deadband_px ?? 18;
  const verticalBounds = (status as HeadCameraStatus & { vertical_bounds_px?: [number, number] })
    .vertical_bounds_px ?? [110, 370];

  return (
    <section aria-label="Head camera">
      <header className="head-camera-readout">
        <h2>Head Camera</h2>
        {controllable ? null : <span>View only</span>}
        <span data-testid="head-camera-state">{stateLabel(status.state)}</span>
        <span data-testid="detector-constructed">{String(status.detector_constructed)}</span>
        <span>{status.model_id}</span>
        <span>{status.runtime_id}</span>
      </header>

      {frame ? (
        <figure className="head-camera-frame" aria-label="Head camera frame">
          <svg className="head-camera-overlay" viewBox="0 0 640 480" preserveAspectRatio="none">
            <line data-testid="optical-axis" x1="320" y1="0" x2="320" y2="480" />
            <rect data-testid="deadband" x={320 - deadbandPx} y={verticalBounds[0]} width={deadbandPx * 2} height={verticalBounds[1] - verticalBounds[0]} />
            <line data-testid="vertical-bounds-low" x1="0" y1={verticalBounds[0]} x2="640" y2={verticalBounds[0]} />
            <line data-testid="vertical-bounds-high" x1="0" y1={verticalBounds[1]} x2="640" y2={verticalBounds[1]} />
            <rect data-testid="vertical-bounds" x="0" y={verticalBounds[0]} width="640" height={verticalBounds[1] - verticalBounds[0]} />
            {detection ? (
              <>
                <rect data-testid="overlay-bbox" x={detection.xyxy[0]} y={detection.xyxy[1]} width={detection.xyxy[2] - detection.xyxy[0]} height={detection.xyxy[3] - detection.xyxy[1]} />
                <image data-testid="overlay-mask" href={`data:image/png;base64,${detection.mask_sha256.slice(0, 0)}`} x={detection.xyxy[0]} y={detection.xyxy[1]} width={detection.xyxy[2] - detection.xyxy[0]} height={detection.xyxy[3] - detection.xyxy[1]} />
                <circle data-testid="candidate-center" cx={(detection.xyxy[0] + detection.xyxy[2]) / 2} cy={(detection.xyxy[1] + detection.xyxy[3]) / 2} r="4" />
              </>
            ) : null}
          </svg>
          <div data-testid="lock-progress">{`${lockProgress} of ${lockRequired}`}</div>
          {detection ? (
            <figcaption>
              <span>{`${detection.class_name} ${detection.confidence.toFixed(2)}`}</span>
              <span>{detection.track_id}</span>
            </figcaption>
          ) : null}
        </figure>
      ) : null}

      <label>
        Target angle
        <input
          type="range"
          aria-label="Target angle"
          min={String(low)}
          max={String(high)}
          step="0.05"
          value={bounded}
          disabled={!controllable}
          onChange={(event) => {
            const next = Number(event.target.value);
            setTarget(Number.isFinite(next) ? Math.min(Math.max(next, low), high) : 0);
          }}
        />
      </label>

      <button type="button" disabled={!controllable} onClick={() => onExecute?.(bounded)}>
        Execute
      </button>
      <button type="button" disabled={!controllable} onClick={() => onStop?.()}>
        Stop
      </button>
      <button type="button" disabled={!controllable} onClick={() => onCapture?.()}>
        Capture
      </button>
    </section>
  );
}

/**
 * The tab body: it owns the status it shows, reads it from the Head Camera API, and renders the panel. A
 * failed read is shown as an unavailable domain rather than as a stale frame.
 */
export function HeadCameraTab({ client }: { client: Pick<HeadCameraClient, "status"> }) {
  const [status, setStatus] = useState<HeadCameraStatus | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    client
      .status()
      .then((next) => {
        if (live) setStatus(next);
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [client]);

  if (failed) return <HeadCameraPanel status={null} />;
  return <HeadCameraPanel status={status} />;
}
