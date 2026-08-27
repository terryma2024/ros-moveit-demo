import { createCommandId } from "@/lib/command-id";
import type { CommandResult, TelemetrySnapshot } from "./types";
import type {
  CaptureResponse,
  RenderedPointCloudMetadata,
  ReachabilityResponse,
  TaskPoint,
  TaskEvent,
  TaskPresetResponse,
  TaskRunSummary,
} from "./task-types";

type Fetcher = typeof fetch;
const browserFetch: Fetcher = (input, init) => fetch(input, init);

export class TaskApiClient {
  constructor(
    private readonly fetcher: Fetcher = browserFetch,
    private readonly commandId = createCommandId,
  ) {}

  private async json<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.fetcher(path, init);
    const payload = await response.json();
    if (!response.ok && !(payload && typeof payload === "object" && "code" in payload)) {
      throw new Error(`HTTP_${response.status}`);
    }
    return payload as T;
  }

  private body(sessionId: string, leaseId: string, extra: Record<string, unknown> = {}) {
    return JSON.stringify({
      ...extra,
      session_id: sessionId,
      lease_id: leaseId,
      command_id: this.commandId(),
    });
  }

  snapshot(): Promise<TelemetrySnapshot> {
    return this.json("/snapshot");
  }

  presets(): Promise<TaskPresetResponse> {
    return this.json("/tasks/presets");
  }

  runs(): Promise<TaskRunSummary[]> {
    return this.json("/tasks/runs");
  }

  status(runId: string): Promise<TaskRunSummary> {
    return this.json(`/tasks/runs/${encodeURIComponent(runId)}`);
  }

  acquireLease(): Promise<CommandResult> {
    return this.json("/control/lease", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ command_id: this.commandId() }),
    });
  }

  validate(points: TaskPoint[], sessionId: string, leaseId: string): Promise<ReachabilityResponse | CommandResult> {
    return this.json("/tasks/reachability", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: this.body(sessionId, leaseId, { schema_version: 1, points }),
    });
  }

  start(points: TaskPoint[], sessionId: string, leaseId: string): Promise<TaskRunSummary | CommandResult> {
    return this.json("/tasks/runs", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: this.body(sessionId, leaseId, { schema_version: 1, points }),
    });
  }

  cancel(runId: string, sessionId: string, leaseId: string): Promise<TaskRunSummary | CommandResult> {
    return this.json(`/tasks/runs/${encodeURIComponent(runId)}/cancel`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: this.body(sessionId, leaseId),
    });
  }

  recovery(runId: string, action: "stop" | "reset-and-continue", sessionId: string, leaseId: string): Promise<TaskRunSummary | CommandResult> {
    return this.json(`/tasks/runs/${encodeURIComponent(runId)}/recovery`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: this.body(sessionId, leaseId, {
        action,
        confirmation: "CONFIRM TASK RECOVERY",
      }),
    });
  }

  capture(sessionId: string, leaseId: string): Promise<CaptureResponse | CommandResult> {
    return this.json("/tasks/captures", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: this.body(sessionId, leaseId),
    });
  }

  artifactUrl(artifactId: string): string {
    return `/tasks/artifacts/${encodeURIComponent(artifactId)}`;
  }

  async fetchArtifact(artifactId: string): Promise<ArrayBuffer> {
    const response = await this.fetcher(this.artifactUrl(artifactId));
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    return response.arrayBuffer();
  }

  async uploadRenderedImage(
    captureId: string,
    png: Blob,
    metadata: RenderedPointCloudMetadata,
    sessionId: string,
    leaseId: string,
  ): Promise<{ artifact_id: string } | CommandResult> {
    const bytes = new Uint8Array(await png.arrayBuffer());
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    }
    return this.json(`/tasks/captures/${encodeURIComponent(captureId)}/rendered-image`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: this.body(sessionId, leaseId, { ...metadata, png_base64: btoa(binary) }),
    });
  }

  shutdown(sessionId: string, leaseId: string): Promise<TaskRunSummary | CommandResult> {
    return this.json("/tasks/environment/shutdown", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: this.body(sessionId, leaseId, {
        confirmation: "CONFIRM TASK ENVIRONMENT SHUTDOWN",
      }),
    });
  }

  watchEvents(
    onEvent: (event: TaskEvent) => void,
    onReconnect: () => void | Promise<void>,
  ): () => void {
    let stopped = false;
    let socket: WebSocket | undefined;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempts = 0;
    const refreshAuthoritativeState = () => {
      void Promise.resolve(onReconnect()).catch(() => undefined);
    };
    const connect = () => {
      if (stopped) return;
      const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
      socket = new WebSocket(`${scheme}//${window.location.host}/tasks/events`);
      socket.addEventListener("open", () => {
        attempts = 0;
        refreshAuthoritativeState();
      });
      socket.addEventListener("message", (message) => {
        try {
          const event = JSON.parse(String(message.data)) as TaskEvent;
          if (typeof event.sequence === "number" && typeof event.kind === "string") onEvent(event);
        } catch {
          // Ignore malformed event frames; status refresh remains authoritative.
        }
      });
      socket.addEventListener("close", () => {
        if (stopped) return;
        refreshAuthoritativeState();
        const delay = Math.min(250 * 2 ** attempts, 4000);
        attempts = Math.min(attempts + 1, 5);
        timer = setTimeout(connect, delay);
      });
    };
    connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }
}
