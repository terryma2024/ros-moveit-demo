// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import type { DomainTransport, RuntimeSnapshot } from "./domain-runtime";
import { DomainRuntime } from "./domain-runtime";
import { RuntimeProvider, pageFromPath, useDomainRuntime, usePageRouting } from "./runtime-provider";

const SNAPSHOT: RuntimeSnapshot = { sequence: 1, serviceEpoch: "e1", executionGeneration: 1, payload: null };

function transport() {
  const value: DomainTransport = {
    register: vi.fn(async (domain) => ({ instance_id: `i-${domain}`, proof: `p-${domain}`, domain })),
    connect: vi.fn(async (proof) => ({ instance_id: proof.instance_id, revision: 1, domain: proof.domain })),
    snapshot: vi.fn(async () => SNAPSHOT),
    subscribe: vi.fn(() => () => undefined),
    renew: vi.fn(async () => undefined),
    post: vi.fn(async () => ({ code: "OK" })),
    close: vi.fn(),
  };
  return value;
}

function Page({ name }: { name: string }) {
  const runtime = useDomainRuntime("teleop");
  const { page, navigate } = usePageRouting();
  return (
    <div>
      <span data-testid="page">{page}</span>
      <span data-testid="runtime">{runtime.domain}</span>
      <span data-testid="name">{name}</span>
      <button type="button" onClick={() => navigate("/expert-validation")}>
        go
      </button>
      <button type="button" onClick={() => navigate("/tasks")}>
        tasks
      </button>
    </div>
  );
}

test("page paths map to the three page names", () => {
  expect(pageFromPath("/")).toBe("teleop");
  expect(pageFromPath("/tasks")).toBe("tasks");
  expect(pageFromPath("/expert-validation")).toBe("validation");
  expect(pageFromPath("/anything-else")).toBe("teleop");
});

test("navigation inside one provider keeps the same runtime and never re-registers", async () => {
  const teleopTransport = transport();
  const runtime = new DomainRuntime("teleop", teleopTransport);
  render(
    <RuntimeProvider teleop={runtime}>
      <Page name="one" />
    </RuntimeProvider>,
  );
  expect(screen.getByTestId("runtime").textContent).toBe("teleop");
  expect(teleopTransport.register).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByRole("button", { name: "go" }));
  expect(screen.getByTestId("page").textContent).toBe("validation");
  // Same provider, same runtime: a page switch is not a new document.
  expect(screen.getByTestId("runtime").textContent).toBe("teleop");
  expect(teleopTransport.register).toHaveBeenCalledTimes(1);
  expect(teleopTransport.close).not.toHaveBeenCalled();
});

test("a failing domain is reported and does not break the shell", async () => {
  const teleopTransport = transport();
  teleopTransport.snapshot = vi.fn(async () => {
    throw new Error("IPC_CONNECT_FAILED");
  });
  const runtime = new DomainRuntime("teleop", teleopTransport);
  render(
    <RuntimeProvider teleop={runtime}>
      <Page name="one" />
    </RuntimeProvider>,
  );
  expect(screen.getByTestId("name").textContent).toBe("one");
  expect(await screen.findByTestId("runtime")).toBeTruthy();
});

test("missing provider and missing domain are explicit errors", () => {
  const Broken = () => {
    useDomainRuntime("teleop");
    return null;
  };
  expect(() => render(<Broken />)).toThrow("RUNTIME_PROVIDER_MISSING");
  const Missing = () => {
    useDomainRuntime("validation");
    return null;
  };
  expect(() =>
    render(
      <RuntimeProvider teleop={new DomainRuntime("teleop", transport())}>
        <Missing />
      </RuntimeProvider>,
    ),
  ).toThrow("DOMAIN_RUNTIME_MISSING: validation");
});

test("browser back and forward update the page without remounting the provider", async () => {
  const teleopTransport = transport();
  const runtime = new DomainRuntime("teleop", teleopTransport);
  render(
    <RuntimeProvider teleop={runtime}>
      <Page name="one" />
    </RuntimeProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "tasks" }));
  expect(screen.getByTestId("page").textContent).toBe("tasks");

  // The browser changes the URL outside React and fires popstate; the shell must follow it
  // without re-registering the document or dropping the runtime.
  globalThis.history.pushState({}, "", "/expert-validation");
  globalThis.dispatchEvent(new PopStateEvent("popstate"));
  expect(await screen.findByText("validation")).toBeTruthy();
  expect(teleopTransport.register).toHaveBeenCalledTimes(1);
  expect(teleopTransport.close).not.toHaveBeenCalled();

  globalThis.history.pushState({}, "", "/");
  globalThis.dispatchEvent(new PopStateEvent("popstate"));
  expect(await screen.findByText("teleop")).toBeTruthy();
  expect(teleopTransport.register).toHaveBeenCalledTimes(1);
});

test("the provider starts the runtime heartbeat once and a page switch does not restart it", async () => {
  vi.useFakeTimers();
  try {
    const teleopTransport = transport();
    const runtime = new DomainRuntime("teleop", teleopTransport);
    const { rerender } = render(
      <RuntimeProvider teleop={runtime} heartbeatMs={1000}>
        <Page name="one" />
      </RuntimeProvider>,
    );
    await vi.runOnlyPendingTimersAsync();
    await vi.advanceTimersByTimeAsync(2000);
    const renewals = (teleopTransport.renew as ReturnType<typeof vi.fn>).mock.calls.length;
    expect(renewals).toBeGreaterThanOrEqual(2);
    // Switching pages re-renders the provider's children only; the heartbeat keeps its cadence.
    rerender(
      <RuntimeProvider teleop={runtime} heartbeatMs={1000}>
        <Page name="two" />
      </RuntimeProvider>,
    );
    await vi.advanceTimersByTimeAsync(1000);
    expect((teleopTransport.renew as ReturnType<typeof vi.fn>).mock.calls.length).toBe(renewals + 1);
    expect(teleopTransport.close).not.toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});
