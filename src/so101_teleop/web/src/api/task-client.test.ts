// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskApiClient } from "./task-client";

class FakeSocket {
  static instances: FakeSocket[] = [];
  listeners = new Map<string, Array<(event: any) => void>>();
  closed = false;
  constructor(readonly url: string) { FakeSocket.instances.push(this); }
  addEventListener(kind: string, listener: (event: any) => void) {
    this.listeners.set(kind, [...(this.listeners.get(kind) ?? []), listener]);
  }
  emit(kind: string, event: any = {}) {
    this.listeners.get(kind)?.forEach((listener) => listener(event));
  }
  close() { this.closed = true; }
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  FakeSocket.instances = [];
});

describe("TaskApiClient event reconnect", () => {
  it("refetches on open, reconnects with bounded delay, and stops cleanly", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
    const onEvent = vi.fn();
    const onReconnect = vi.fn();
    const stop = new TaskApiClient().watchEvents(onEvent, onReconnect);
    expect(FakeSocket.instances[0].url).toContain("/tasks/events");
    FakeSocket.instances[0].emit("open");
    FakeSocket.instances[0].emit("message", { data: JSON.stringify({ sequence: 1, kind: "POINT_FINISHED", status: "FAILED" }) });
    expect(onReconnect).toHaveBeenCalledOnce();
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({ sequence: 1 }));
    FakeSocket.instances[0].emit("close");
    expect(onReconnect).toHaveBeenCalledTimes(2);
    await vi.advanceTimersByTimeAsync(250);
    expect(FakeSocket.instances).toHaveLength(2);
    stop();
    FakeSocket.instances[1].emit("close");
    await vi.advanceTimersByTimeAsync(4000);
    expect(FakeSocket.instances).toHaveLength(2);
    expect(FakeSocket.instances[1].closed).toBe(true);
  });
});
