import { createCommandId } from "@/lib/command-id";
import type { CommandResult } from "./types";

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

  async executeAll(planId: string, gripperTarget: number, leaseId: string, sessionId: string) {
    const arm = await this.post(`/plans/${planId}/execute`, {}, leaseId, sessionId);
    if (!arm.succeeded) return { arm };
    const gripper = await this.post("/gripper/execute", { target_position_rad: gripperTarget }, leaseId, sessionId);
    return { arm, gripper };
  }
}
