import { createCommandId } from "@/lib/command-id";
import { authorityHeaders, type ControllerAuthority } from "./instance-client";
import type { BackendCapabilities, CommandResult } from "./types";

/** The parent projection returned by the composite Execute All operation. */
export type ParentChildProjection = {
  child_id: string;
  goal_uuid: string;
  succeeded: boolean;
  stopped_confirmed: boolean;
  cleanup_confirmed: boolean;
};

export type ParentProjection = {
  operation_id: string;
  phase: string;
  blocked_reason: string | null;
  children: ParentChildProjection[];
};

type Fetcher = typeof fetch;
const browserFetch: Fetcher = (input, init) => fetch(input, init);

export class TeleopApiClient {
  constructor(private readonly fetcher: Fetcher = browserFetch, private readonly commandId = createCommandId) {}

  async post(path: string, body: Record<string, unknown>, leaseId = "", sessionId = ""): Promise<CommandResult> {
    const response = await this.fetcher(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...body, command_id: this.commandId(), lease_id: leaseId, session_id: sessionId }),
    });
    return response.json() as Promise<CommandResult>;
  }

  async capabilities(): Promise<BackendCapabilities> {
    const response = await this.fetcher("/capabilities", { method: "GET" });
    if (!response.ok) throw new Error(`HTTP_${response.status}`);
    return response.json() as Promise<BackendCapabilities>;
  }

  /**
   * One server-side composite operation.
   *
   * The plan, the gripper target, the runtime identity and the execution generation are frozen
   * once, and the server keeps a single parent reservation across the arm and gripper steps. A
   * timeout must never be retried with a second POST; the recorded parent is queried instead.
   */
  async executeAll(
    planId: string,
    gripperTarget: number,
    leaseId: string,
    sessionId: string,
    authority?: ControllerAuthority,
  ): Promise<ParentProjection> {
    const response = await this.fetcher(`/plans/${planId}/execute-all`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        ...(authority ? authorityHeaders(authority) : {}),
      },
      body: JSON.stringify({
        command_id: this.commandId(),
        lease_id: leaseId,
        session_id: sessionId,
        gripper_target: gripperTarget,
      }),
    });
    return (await response.json()) as ParentProjection;
  }
}
