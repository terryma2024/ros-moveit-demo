import { authorityHeaders, type ControllerAuthority } from "./instance-client";

/** The composed Head Camera domain's status, as the backend reports it. */
export type HeadCameraStatus = {
  available: boolean;
  operation: string;
  runtime_id: string;
  model_id: string;
  state: string;
  detector_constructed: number;
  qualified: boolean;
  authority: boolean;
  safe_interval_rad: [number, number];
};

export type HeadCameraCommandResult = {
  ok: boolean;
  code: string | null;
  detail: unknown;
};

type Fetcher = typeof fetch;
const browserFetch: Fetcher = (input, init) => fetch(input, init);
const BASE = "/teleop/head-camera";

/**
 * The Head Camera API. It sends only what the backend accepts: a target angle, a stop and a capture. The
 * sealed interval belongs to the promoted configuration and is never sent from here, and a refusal from the
 * backend is reported by its code rather than retried.
 */
export class HeadCameraClient {
  constructor(private readonly fetcher: Fetcher = browserFetch) {}

  async status(): Promise<HeadCameraStatus> {
    const response = await this.fetcher(`${BASE}/status`, { method: "GET" });
    if (!response.ok) throw new Error(`HEAD_CAMERA_STATUS_${response.status}`);
    return (await response.json()) as HeadCameraStatus;
  }

  streamUrl(): string {
    const scheme = typeof location !== "undefined" && location.protocol === "https:" ? "wss" : "ws";
    const host = typeof location !== "undefined" ? location.host : "127.0.0.1:8000";
    return `${scheme}://${host}${BASE}/stream`;
  }

  async submitTarget(targetRad: number, authority: ControllerAuthority): Promise<HeadCameraCommandResult> {
    return this.post(`${BASE}/target`, { target_rad: targetRad }, authority);
  }

  async stop(authority: ControllerAuthority, rawSample?: Record<string, unknown>): Promise<HeadCameraCommandResult> {
    return this.post(`${BASE}/stop`, rawSample ?? {}, authority);
  }

  async capture(authority: ControllerAuthority): Promise<HeadCameraCommandResult> {
    return this.post(`${BASE}/capture`, {}, authority);
  }

  private async post(
    path: string,
    body: Record<string, unknown>,
    authority: ControllerAuthority,
  ): Promise<HeadCameraCommandResult> {
    const response = await this.fetcher(path, {
      method: "POST",
      headers: { "content-type": "application/json", ...authorityHeaders(authority) },
      body: JSON.stringify(body),
    });
    const detail = await response.json().catch(() => null);
    if (response.ok) return { ok: true, code: null, detail };
    const code = (detail as { detail?: { code?: string } } | null)?.detail?.code ?? `HTTP_${response.status}`;
    return { ok: false, code, detail };
  }
}
