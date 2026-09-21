import { describe, expect, test } from "vitest";

import { ExpertValidationStore } from "./expert-validation-store";
import type { CampaignProjection } from "@/api/expert-validation-types";

function campaignProjection(sequence: number): CampaignProjection {
  return {
    campaign_id: "campaign-1",
    sequence,
    batch_cleanup_complete: false,
    points: [],
    workers: [],
    requested: 0,
    evaluated: 0,
    execution_started: 0,
    valid_succeeded: 0,
    valid_failed: 0,
    indeterminate: 0,
    not_executed: 0,
    evaluation_coverage: 0,
    execution_coverage: 0,
    levels_used: [],
    fallback_history: [],
    retry_history: [],
    infra_attempts: 0,
    resource_observations: {},
  };
}

function fakeClient(options: { campaignSequence: number; websocketSequences: number[] }) {
  const calls: string[] = [];
  return {
    calls,
    async campaign(campaignId: string) {
      calls.push(`GET ${campaignId}`);
      return { ...campaignProjection(options.campaignSequence), campaign_id: campaignId };
    },
    openEvents(after: number, apply: (event: { campaign_id: string; sequence: number }) => void) {
      calls.push(`OPEN events after=${after}`);
      for (const sequence of options.websocketSequences) {
        apply({ campaign_id: "campaign-1", sequence });
      }
      return () => calls.push("CLOSE events");
    },
  };
}

describe("ExpertValidationStore", () => {
  test("reconnect fetches campaign before applying later events", async () => {
    const client = fakeClient({ campaignSequence: 8, websocketSequences: [9, 10] });
    const store = new ExpertValidationStore(client);
    await store.reconnect("campaign-1");
    expect(client.calls).toEqual(["GET campaign-1", "OPEN events after=8"]);
    expect(store.state?.sequence).toBe(10);
  });

  test("stale hints are discarded without changing authority", async () => {
    const client = fakeClient({ campaignSequence: 8, websocketSequences: [7, 8, 9] });
    const store = new ExpertValidationStore(client);
    await store.reconnect("campaign-1");
    expect(store.state?.sequence).toBe(9);
  });

  test("a sequence gap refreshes HTTP before accepting later hints", async () => {
    const client = fakeClient({ campaignSequence: 3, websocketSequences: [6] });
    const store = new ExpertValidationStore(client);
    await store.reconnect("campaign-1");
    await store.settled();
    expect(client.calls).toEqual([
      "GET campaign-1",
      "OPEN events after=3",
      "GET campaign-1",
    ]);
  });
});
