// @vitest-environment jsdom
/**
 * A code-bearing refusal is not a campaign projection.
 *
 * Recorded production defect: the retry POST answered `409 {"code": "..."}` and the page adopted
 * that document as its campaign. The campaign then had no `campaign_id`, so the watcher asked for
 * `GET /expert-validation/campaigns/undefined` (ninety-seven times in the recorded leg), the socket
 * reconnected with `after=undefined`, and the panel rendered "Campaign UNKNOWN".
 *
 * The refusal arrives resolved, not thrown: the page's mutating calls go through the domain
 * runtime transport, which treats a status the service answered with as a value. This test drives
 * the real page against that transport - no injected api - and pins that the refusal reaches the
 * operator as a notice while the authoritative campaign survives.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { DomainRuntime, type DomainTransport } from "@/state/domain-runtime";
import { RuntimeProvider } from "@/state/runtime-provider";

import { ExpertValidationApp } from "./expert-validation-app";

const CAMPAIGN_ID = "campaign-e15544c0506e47b198bc907433d3ae37";
const POINT_ID = "sample_05_near_center";
const RETRY_PATH = `/expert-validation/campaigns/${CAMPAIGN_ID}/full-restart-retries`;
const REFUSAL_CODE = "RETRY_ORIGINAL_CLEANUP_INCOMPLETE";

const CAMPAIGN = {
  campaign_id: CAMPAIGN_ID,
  manifest_id: "manifest-1",
  sequence: 24,
  execution_mode: "SEQUENTIAL",
  status: "COMPLETED_WITH_FAILURES",
  requested: 20,
  evaluated: 20,
  execution_started: 20,
  valid_succeeded: 19,
  batch_cleanup_complete: true,
  points: [
    {
      point_id: POINT_ID,
      display_id: "P09",
      status: "FAILED",
      retry_eligible: true,
      attempts: [],
      artifact_ids: [],
      artifacts: [],
    },
  ],
};

const CAPABILITIES = {
  available: true,
  worker_qualifications: [2, 3, 4, 5, 6, 7, 8].map((selected_n) => ({
    selected_n,
    status: "UNKNOWN",
    reasons: ["BUDGET_PROVIDER_NOT_READY"],
    runtime_identity: "test-runtime",
    contract_version: 2,
    profile_sha256: null,
    approval_sha256: null,
  })),
  execution_modes: ["SEQUENTIAL", "PARALLEL", "ADAPTIVE"],
  default_execution_mode: "SEQUENTIAL",
  minimum_points: 4,
  maximum_points: 20,
  fixed_worker_counts: [1, 2, 3],
  worker_count_availability: [2, 3, 4].map((worker_count) => ({
    worker_count,
    selectable: worker_count === 2,
    status: worker_count === 2 ? "APPROVED" : "NOT_MEASURED",
    reason_codes: worker_count === 2 ? [] : ["BUDGET_PROFILE_UNAVAILABLE"],
  })),
  adaptive_default_ladder: [8, 6, 4, 2, 1],
  support_matrix: [],
  lease_duration_s: 30,
  lease_renewal_margin_s: 10,
};

/** jsdom would try to open a real socket for the event stream; the page only needs a handle. */
class SilentSocket {
  static readonly urls: string[] = [];

  constructor(readonly url: string) {
    SilentSocket.urls.push(url);
  }

  addEventListener(): void {}

  close(): void {}
}

const fetched: string[] = [];
const posted: string[] = [];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/** The page's own client reads over HTTP; every mutating call goes through the runtime transport. */
function stubReads(): void {
  fetched.length = 0;
  const fetchImpl = (async (input: RequestInfo | URL) => {
    const url = String(input);
    fetched.push(url);
    if (url.endsWith("/expert-validation/capabilities")) return jsonResponse(CAPABILITIES);
    if (url.endsWith("/expert-validation/campaigns")) return jsonResponse([CAMPAIGN]);
    if (url.includes("/expert-validation/manifests/")) {
      return jsonResponse({ manifest_id: "manifest-1", point_count: 20, stale: false, points: [] });
    }
    if (url.includes("/expert-validation/campaigns/")) return jsonResponse(CAMPAIGN);
    return jsonResponse({ code: "UNEXPECTED_READ" }, 404);
  }) as unknown as typeof fetch;
  vi.stubGlobal("fetch", fetchImpl);
}

function runtimeTransport(): DomainTransport {
  posted.length = 0;
  return {
    register: async (domain) => ({ instance_id: `i-${domain}`, proof: `p-${domain}`, domain }),
    connect: async (proof) => ({ instance_id: proof.instance_id, revision: 1, domain: proof.domain }),
    snapshot: async () => ({ sequence: 0, serviceEpoch: "e1", executionGeneration: 1, payload: null }),
    subscribe: () => () => undefined,
    renew: async () => undefined,
    setAuthority: () => undefined,
    post: async (path) => {
      posted.push(path);
      if (path === "/expert-validation/lease") {
        return {
          lease_id: "L1",
          service_session_id: "s1",
          generation: 1,
          expires_monotonic_ns: 10 ** 15,
          execution_generation: 1,
        };
      }
      // The service answered the retry with a typed 409 body, and this transport resolves it: that
      // is the exact shape the recorded console adopted as its campaign.
      return { code: REFUSAL_CODE };
    },
    close: () => undefined,
  };
}

async function driveRetry(): Promise<void> {
  const runtime = new DomainRuntime("validation", runtimeTransport());
  render(
    <RuntimeProvider validation={runtime}>
      <ExpertValidationApp />
    </RuntimeProvider>,
  );
  await act(async () => {
    runtime.adoptAuthority({
      instanceId: "i-validation",
      proof: "p",
      channelRevision: 1,
      executionGeneration: 1,
    });
  });
  await userEvent.click(await screen.findByRole("button", { name: /acquire lease/i }));
  // The campaign under retry, restored through the page's own client.
  await screen.findByText(`Campaign ${CAMPAIGN_ID}`);
  await userEvent.click(await screen.findByLabelText("Retry P09"));
  await userEvent.click(screen.getByRole("button", { name: /retry selected with full_restart/i }));
  await userEvent.type(screen.getByLabelText("Confirmation"), "CONFIRM FULL_RESTART RETRIES");
  await userEvent.click(screen.getByRole("button", { name: /confirm retry/i }));
  await waitFor(() => expect(posted).toContain(RETRY_PATH));
}

beforeEach(() => {
  sessionStorage.clear();
  SilentSocket.urls.length = 0;
  vi.stubGlobal("WebSocket", SilentSocket);
  stubReads();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("a refused retry", () => {
  test("is reported to the operator instead of replacing the campaign", async () => {
    await driveRetry();

    // The refusal is a refusal: it is shown, not silently adopted as the campaign state.
    expect(await screen.findByText(REFUSAL_CODE)).toBeTruthy();
    // The authoritative projection survives, so the panel and the selection stay bound to it.
    expect(screen.getByText(`Campaign ${CAMPAIGN_ID}`)).toBeTruthy();
    expect(screen.getByLabelText("Retry P09")).toBeTruthy();
  });

  test("never leaves the page asking for an undefined campaign", async () => {
    await driveRetry();
    await screen.findByText(REFUSAL_CODE);

    expect(fetched.filter((url) => url.includes("/campaigns/undefined"))).toEqual([]);
    expect(SilentSocket.urls.filter((url) => url.includes("undefined"))).toEqual([]);
  });
});
