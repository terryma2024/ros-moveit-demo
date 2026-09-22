import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

import {
  releaseAcquiredLeases,
  rememberLeaseAuthority,
  trackConsoleLeases,
} from "../pages/expert-validation-page";

/**
 * The teardown that hands the console's exclusive lease back.
 *
 * The unified service refuses a lease mutation that does not carry the console's own instance
 * authority (`X-SO101-Instance-ID`, `-Proof`, `-Channel-Revision`, `-Execution-Generation`) with
 * `409 CONTROLLER_INSTANCE_REQUIRED`, and a release refused that way leaves the controller binding
 * held: every following spec then fails on acquire with `CONTROLLER_ALREADY_BOUND`.  These tests
 * exercise the release path offline, with the console's response and the HTTP context injected, so
 * the cascade can never come back unnoticed.
 */

const AUTHORITY = {
  "x-so101-instance-id": "instance-1",
  "x-so101-instance-proof": "proof-1",
  "x-so101-channel-revision": "7",
  "x-so101-execution-generation": "3",
};

type Captured = { url: string; options: any };

/** A page whose only observable behaviour is the response stream the console emits. */
function fakeConsolePage(): { page: Page; emit: (response: unknown) => void } {
  const handlers: Array<(response: any) => void> = [];
  const page = {
    on: (event: string, handler: (response: any) => void) => {
      if (event === "response") handlers.push(handler);
    },
  } as unknown as Page;
  return {
    page,
    emit: (response) => {
      for (const handler of handlers) handler(response);
    },
  };
}

function consoleMutation(
  payload: Record<string, unknown>,
  headers: Record<string, string> = AUTHORITY,
  method = "POST",
  url = "http://127.0.0.1:8013/expert-validation/lease",
  status = 200,
) {
  return {
    url: () => url,
    request: () => ({ method: () => method, headers: () => headers }),
    status: () => status,
    json: async () => payload,
  };
}

function fakeRequest(
  status: number,
  body: Record<string, unknown> = { code: "CONTROLLER_INSTANCE_REQUIRED" },
): { request: APIRequestContext; captured: Captured[] } {
  const captured: Captured[] = [];
  const request = {
    delete: async (url: string, options: any) => {
      captured.push({ url, options });
      return {
        status: () => status,
        ok: () => status >= 200 && status < 300,
        text: async () => (status === 200 ? "" : JSON.stringify(body)),
      };
    },
  } as unknown as APIRequestContext;
  return { request, captured };
}

/** Let the tracker's own `response.json()` promise settle. */
const settle = () => new Promise((resolvePromise) => setTimeout(resolvePromise, 0));

test("a release carries the console's own instance authority headers", async () => {
  const console = fakeConsolePage();
  trackConsoleLeases(console.page);
  console.emit(consoleMutation({ lease_id: "lease-1", service_session_id: "session-1", generation: 4 }));
  await settle();

  const { request, captured } = fakeRequest(200);
  await releaseAcquiredLeases(request);

  expect(captured).toHaveLength(1);
  expect(captured[0].url).toBe("/expert-validation/lease/lease-1");
  expect(captured[0].options.headers).toMatchObject(AUTHORITY);
  // Nothing but the authority headers is forwarded, and the body still carries the generation.
  expect(Object.keys(captured[0].options.headers)).toHaveLength(4);
  expect(captured[0].options.data).toEqual({ service_session_id: "session-1", generation: 4 });
});

test("a deliberate spec failure still releases the binding in the teardown", async () => {
  const console = fakeConsolePage();
  trackConsoleLeases(console.page);
  console.emit(consoleMutation({ lease_id: "lease-2", service_session_id: "session-2", generation: 9 }));
  await settle();

  const { request, captured } = fakeRequest(200);
  let bodyThrew = false;
  try {
    throw new Error("deliberate spec failure");
  } catch {
    bodyThrew = true;
  } finally {
    // The shape every spec's afterEach has: the release runs whatever the body did.
    await releaseAcquiredLeases(request);
  }

  expect(bodyThrew).toBe(true);
  expect(captured).toHaveLength(1);
  expect(captured[0].options.headers["x-so101-instance-proof"]).toBe("proof-1");
});

test("a release refused with controller authority is a failure, never a silent leak", async () => {
  const console = fakeConsolePage();
  trackConsoleLeases(console.page);
  console.emit(consoleMutation({ lease_id: "lease-3", service_session_id: "session-3", generation: 1 }));
  await settle();

  const refused = fakeRequest(409);
  await expect(releaseAcquiredLeases(refused.request)).rejects.toThrow(/release lease failed: 409/);

  // The lease stays recorded, so a later teardown retries it instead of forgetting it.
  const accepted = fakeRequest(200);
  await releaseAcquiredLeases(accepted.request);
  expect(accepted.captured).toHaveLength(1);
  // ...and once released it is not sent again.
  const afterwards = fakeRequest(200);
  await releaseAcquiredLeases(afterwards.request);
  expect(afterwards.captured).toHaveLength(0);
});

test("a lease the service already dropped is not a leak", async () => {
  const console = fakeConsolePage();
  trackConsoleLeases(console.page);
  console.emit(consoleMutation({ lease_id: "lease-4", service_session_id: "session-4", generation: 2 }));
  await settle();

  const dropped = fakeRequest(404);
  await releaseAcquiredLeases(dropped.request);
  const afterwards = fakeRequest(200);
  await releaseAcquiredLeases(afterwards.request);
  expect(afterwards.captured).toHaveLength(0);
});

test("a lease the product holds for an unresolved campaign is recorded, not failed", async () => {
  // `lease.py` raises LeaseConflict("ACTIVE_CAMPAIGN") while a campaign may still be retried
  // (test_expert_validation_lease.py::test_active_campaign_rejects_release): a held-by-design lease
  // must not fail a spec whose body passed, and it cannot leak because every window stops its own
  // service at the end of the case.
  const consolePage = fakeConsolePage();
  trackConsoleLeases(consolePage.page);
  consolePage.emit(consoleMutation({ lease_id: "lease-7", service_session_id: "session-7", generation: 3 }));
  await settle();

  const held = fakeRequest(409, { code: "ACTIVE_CAMPAIGN" });
  const warnings: string[] = [];
  const originalWarn = console.warn;
  console.warn = (...args: unknown[]) => {
    warnings.push(args.join(" "));
  };
  try {
    await expect(releaseAcquiredLeases(held.request)).resolves.toBeUndefined();
  } finally {
    console.warn = originalWarn;
  }
  expect(warnings.join("\n")).toContain("LEASE_HELD_BY_DESIGN: ACTIVE_CAMPAIGN lease-7");
  // Recorded once: the held lease is not sent again by a later teardown.
  const afterwards = fakeRequest(200);
  await releaseAcquiredLeases(afterwards.request);
  expect(afterwards.captured).toHaveLength(0);
});

test("only ACTIVE_CAMPAIGN is tolerated; every other refusal still bites", async () => {
  const cases: Array<[number, Record<string, unknown>, RegExp]> = [
    [409, { code: "CONTROLLER_INSTANCE_REQUIRED" }, /CONTROLLER_INSTANCE_REQUIRED/],
    [409, { code: "CONTROLLER_ALREADY_BOUND" }, /CONTROLLER_ALREADY_BOUND/],
    [409, { code: "LEASE_IDENTITY_MISMATCH" }, /LEASE_IDENTITY_MISMATCH/],
    [409, { code: "STALE_LEASE_GENERATION" }, /STALE_LEASE_GENERATION/],
    [500, { code: "INTERNAL_ERROR" }, /release lease failed: 500/],
    // The nested `detail.code` shape is read too, and a message that merely mentions the tolerated
    // word is not accepted as the code.
    [409, { detail: { code: "ACTIVE_CAMPAIGN" } }, /^$/],
    [409, { code: "LEASE_CONFLICT", message: "ACTIVE_CAMPAIGN is not the code here" }, /LEASE_CONFLICT/],
  ];
  for (const [status, body, expected] of cases) {
    const console = fakeConsolePage();
    trackConsoleLeases(console.page);
    const leaseId = `lease-refusal-${status}-${String(body.code ?? "detail")}`;
    console.emit(consoleMutation({ lease_id: leaseId, service_session_id: "s", generation: 1 }));
    await settle();
    const response = fakeRequest(status, body);
    const release = releaseAcquiredLeases(response.request);
    if (body.code === "ACTIVE_CAMPAIGN" || (body.detail as any)?.code === "ACTIVE_CAMPAIGN") {
      await expect(release).resolves.toBeUndefined();
    } else {
      await expect(release).rejects.toThrow(expected);
    }
    // Drain so one case cannot affect the next.
    await releaseAcquiredLeases(fakeRequest(200).request);
  }
});

test("an acquire records the authority even when the tracker saw no response yet", async () => {
  // The direct acquire path records what the POST response itself carried.
  rememberLeaseAuthority("lease-5", { service_session_id: "session-5", generation: 5 }, AUTHORITY);
  const { request, captured } = fakeRequest(200);
  await releaseAcquiredLeases(request);
  expect(captured[0].options.headers).toEqual(AUTHORITY);
});

test("a refused mutation never becomes a recorded lease", async () => {
  const console = fakeConsolePage();
  trackConsoleLeases(console.page);
  console.emit(consoleMutation({ lease_id: "lease-6" }, AUTHORITY, "POST", undefined, 409));
  await settle();
  const { request, captured } = fakeRequest(200);
  await releaseAcquiredLeases(request);
  expect(captured).toHaveLength(0);
});
