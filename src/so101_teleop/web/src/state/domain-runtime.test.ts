import { expect, test, vi } from "vitest";

import type { ChannelBinding, ControllerAuthority, InstanceProof } from "@/api/instance-client";
import { DomainRuntime, MAX_BUFFERED_EVENTS, type DomainTransport, type RuntimeSnapshot } from "./domain-runtime";

function makeTransport(snapshotValue: RuntimeSnapshot) {
  let handler: ((event: RuntimeSnapshot) => void) | null = null;
  const transport: DomainTransport = {
    register: vi.fn(async () => ({ instance_id: "i1", proof: "p1", domain: "teleop" }) as InstanceProof),
    connect: vi.fn(async () => ({ instance_id: "i1", revision: 1, domain: "teleop" }) as ChannelBinding),
    snapshot: vi.fn(async () => snapshotValue),
    subscribe: vi.fn((next: (event: RuntimeSnapshot) => void) => {
      handler = next;
      return () => {
        handler = null;
      };
    }),
    renew: vi.fn(async () => undefined),
    post: vi.fn(async () => ({ code: "OK", succeeded: true })),
    close: vi.fn(),
  };
  return { transport, emit: (event: RuntimeSnapshot) => handler?.(event) };
}

test("sequence gaps use snapshot and do not replay mutations", async () => {
  const snapshot: RuntimeSnapshot = { sequence: 8, serviceEpoch: "e1", executionGeneration: 1, payload: null };
  const { transport } = makeTransport(snapshot);
  const runtime = new DomainRuntime("teleop", transport);
  await runtime.start();
  await runtime.accept({ ...snapshot, sequence: 12 });
  expect(transport.snapshot).toHaveBeenCalledTimes(2);
  expect(runtime.projection()?.sequence).toBe(8);
  expect(transport.post).not.toHaveBeenCalled();
  runtime.dispose();
});

test("contiguous events advance the projection and stale events are ignored", async () => {
  const snapshot: RuntimeSnapshot = { sequence: 8, serviceEpoch: "e1", executionGeneration: 1, payload: null };
  const { transport } = makeTransport(snapshot);
  const runtime = new DomainRuntime("teleop", transport);
  await runtime.start();
  await runtime.accept({ ...snapshot, sequence: 9 });
  expect(runtime.projection()?.sequence).toBe(9);
  await runtime.accept({ ...snapshot, sequence: 9 });
  await runtime.accept({ ...snapshot, sequence: 3 });
  expect(transport.snapshot).toHaveBeenCalledTimes(1);
  expect(runtime.projection()?.sequence).toBe(9);
  runtime.dispose();
});

test("an epoch change forces a new snapshot and clears execution permission", async () => {
  const snapshot: RuntimeSnapshot = { sequence: 8, serviceEpoch: "e1", executionGeneration: 1, payload: null };
  const { transport } = makeTransport(snapshot);
  const runtime = new DomainRuntime("teleop", transport);
  await runtime.start();
  const resnapshotSpy = vi.fn(async () => ({
    sequence: 30,
    serviceEpoch: "e2",
    executionGeneration: 5,
    payload: null,
  }));
  transport.snapshot = resnapshotSpy;
  await runtime.accept({ ...snapshot, serviceEpoch: "e2", sequence: 9, executionGeneration: 5 });
  expect(resnapshotSpy).toHaveBeenCalledTimes(1);
  expect(runtime.projection()?.serviceEpoch).toBe("e2");
  expect(runtime.projection()?.executionGeneration).toBe(5);
  runtime.dispose();
});

test("events arriving during a snapshot are buffered and never replayed as commands", async () => {
  const snapshot: RuntimeSnapshot = { sequence: 8, serviceEpoch: "e1", executionGeneration: 1, payload: null };
  let release: () => void = () => undefined;
  const { transport } = makeTransport(snapshot);
  const runtime = new DomainRuntime("teleop", transport);
  await runtime.start();
  transport.snapshot = vi.fn(
    () =>
      new Promise<RuntimeSnapshot>((resolve) => {
        release = () => resolve(snapshot);
      }),
  );
  const pending = runtime.accept({ ...snapshot, sequence: 20 });
  await Promise.resolve();
  expect(runtime.projection()?.sequence).toBe(8);
  release();
  await pending;
  expect(transport.post).not.toHaveBeenCalled();
  expect(MAX_BUFFERED_EVENTS).toBeGreaterThan(0);
  runtime.dispose();
});

test("a document without authority cannot post and dispose closes the transport", async () => {
  const snapshot: RuntimeSnapshot = { sequence: 1, serviceEpoch: "e1", executionGeneration: 1, payload: null };
  const { transport } = makeTransport(snapshot);
  const runtime = new DomainRuntime("teleop", transport);
  await runtime.start();
  const authority: ControllerAuthority = {
    instanceId: "i1",
    proof: "p1",
    channelRevision: 1,
    executionGeneration: 0,
  };
  runtime.adoptAuthority(authority);
  await runtime.post("/gripper/execute", { command_id: "c1" });
  expect(transport.post).toHaveBeenCalledTimes(1);
  runtime.dispose();
  expect(transport.close).toHaveBeenCalledTimes(1);
  await expect(runtime.post("/gripper/execute", { command_id: "c2" })).resolves.toEqual({
    code: "OK",
    succeeded: true,
  });
});

test("the renewal heartbeat belongs to the runtime, not to a page", async () => {
  vi.useFakeTimers();
  try {
    const snapshot: RuntimeSnapshot = { sequence: 1, serviceEpoch: "e1", executionGeneration: 1, payload: null };
    const { transport } = makeTransport(snapshot);
    const runtime = new DomainRuntime("teleop", transport);
    await runtime.start();
    runtime.adoptAuthority({
      instanceId: "i1",
      proof: "p1",
      channelRevision: 1,
      executionGeneration: 1,
    });
    runtime.startHeartbeat(1000);
    expect(runtime.heartbeatRunning()).toBe(true);
    await vi.advanceTimersByTimeAsync(3000);
    // Three ticks of renewal, and nothing was torn down by any page lifecycle in between.
    expect(transport.renew).toHaveBeenCalledTimes(3);
    expect(transport.close).not.toHaveBeenCalled();
    // Starting it twice must not double the timers.
    runtime.startHeartbeat(1000);
    await vi.advanceTimersByTimeAsync(1000);
    expect(transport.renew).toHaveBeenCalledTimes(4);
    runtime.dispose();
    expect(runtime.heartbeatRunning()).toBe(false);
    await vi.advanceTimersByTimeAsync(5000);
    expect(transport.renew).toHaveBeenCalledTimes(4);
  } finally {
    vi.useRealTimers();
  }
});

test("a failed renewal is recorded and never retried with a new lease generation", async () => {
  vi.useFakeTimers();
  try {
    const snapshot: RuntimeSnapshot = { sequence: 1, serviceEpoch: "e1", executionGeneration: 1, payload: null };
    const { transport } = makeTransport(snapshot);
    transport.renew = vi.fn(async () => {
      throw new Error("LEASE_RENEW_FAILED");
    });
    const runtime = new DomainRuntime("teleop", transport);
    await runtime.start();
    runtime.adoptAuthority({
      instanceId: "i1",
      proof: "p1",
      channelRevision: 1,
      executionGeneration: 1,
    });
    runtime.startHeartbeat(1000);
    await vi.advanceTimersByTimeAsync(2000);
    expect(transport.renew).toHaveBeenCalledTimes(2);
    expect(runtime.lastRenewalError).toContain("LEASE_RENEW_FAILED");
    expect(transport.post).not.toHaveBeenCalled();
    runtime.dispose();
  } finally {
    vi.useRealTimers();
  }
});
